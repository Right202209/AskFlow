import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status

from askflow.agent.handoff import HANDOFF_SWEEP_INTERVAL_S, sweep_expired_handoffs
from askflow.agent.harness import CognitiveHarnessPolicy
from askflow.agent.service import (
    build_agent_service,
    dispose_agent_service,
    init_agent_service,
    start_route_map_subscriber,
    stop_route_map_subscriber,
)
from askflow.agent.tools import close_http_client, init_http_client
from askflow.chat.push import start_chat_push_subscriber, stop_chat_push_subscriber
from askflow.config import settings
from askflow.core.database import engine
from askflow.core.exceptions import register_exception_handlers
from askflow.core.health import check_health
from askflow.core.logging import get_logger
from askflow.core.metrics import BUILD_INFO
from askflow.core.middleware import setup_middleware
from askflow.core.prompts import prompt_cache
from askflow.core.redis import redis_client
from askflow.embedding.index_worker import start_index_consumer, stop_index_consumer
from askflow.rag.bm25 import bm25_index
from askflow.rag.llm_client import llm_client
from askflow.rag.vector_store import get_vector_store
from askflow.version import APP_VERSION

DEFAULT_SECRET_KEY = "change-me-to-a-random-secret-key"

logger = get_logger(__name__)

_handoff_sweep_task: asyncio.Task | None = None


async def _handoff_sweep_loop() -> None:
    """周期清扫超时未认领的 handoff（升级工单 + 通知）；单轮失败不结束循环。"""
    while True:
        await asyncio.sleep(HANDOFF_SWEEP_INTERVAL_S)
        try:
            await sweep_expired_handoffs()
        except Exception as exc:
            logger.warning("handoff_sweep_failed", error=str(exc))


def _start_handoff_sweep() -> None:
    global _handoff_sweep_task
    if _handoff_sweep_task is None or _handoff_sweep_task.done():
        _handoff_sweep_task = asyncio.create_task(_handoff_sweep_loop())


async def _stop_handoff_sweep() -> None:
    global _handoff_sweep_task
    task = _handoff_sweep_task
    _handoff_sweep_task = None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def _assert_production_safe_settings() -> None:
    """fail-safe 启动校验：除非显式 APP_ENV=development，否则不允许默认 secret_key 启动。"""
    if settings.app_env == "development":
        return
    if settings.secret_key == DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is still the default placeholder while APP_ENV="
            f"{settings.app_env!r}. Set a strong random SECRET_KEY, or explicitly set "
            "APP_ENV=development for local development."
        )


def _warm_bm25_index() -> None:
    """启动期把 BM25 索引拉回内存——先吃 pickle，缺失/损坏时再从 Chroma 全量重建。"""
    loaded = False
    try:
        loaded = bm25_index.load_from_file(settings.bm25_index_path)
    except Exception as exc:
        logger.warning("bm25_warm_load_failed", error=str(exc))

    if loaded:
        logger.info("bm25_loaded_from_file", size=bm25_index.size)
        return

    try:
        vector_store = get_vector_store()
    except Exception as exc:
        logger.warning("bm25_warm_skipped_no_vector_store", error=str(exc))
        return

    count = bm25_index.rebuild_from_vector_store(vector_store)
    if count > 0:
        try:
            bm25_index.save_to_file(settings.bm25_index_path)
        except Exception as exc:
            logger.warning("bm25_warm_persist_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """在应用生命周期内初始化并释放共享基础设施。"""
    _assert_production_safe_settings()
    await redis_client.initialize()
    _warm_bm25_index()
    # 跨 worker 路由失效广播——subscriber 必须在 Redis 初始化之后启动。
    start_route_map_subscriber()
    # 提示词模板热更新广播（同一 ConfigCache 机制），随 Redis 一起拉起。
    prompt_cache.start_subscriber()
    # 跨 worker 用户推送桥（客服回复/接管状态）+ handoff 超时清扫。
    start_chat_push_subscriber()
    _start_handoff_sweep()
    # 业务工具 httpx 单例——search_order 等异步工具复用同一份连接池。
    init_http_client()
    # Redis 队列消费者：启动先重排 pending / stale indexing，再进入 BRPOP 循环。
    await start_index_consumer()

    # 应用启动期一次性装配 AgentService（embedder / vector_store / retriever /
    # reranker / RAG / IntentClassifier / AgentGraph），避免每条用户消息都重建整条栈。
    agent_service = build_agent_service()
    init_agent_service(agent_service)
    app.state.agent_service = agent_service

    # 单次写入构建信息指标——确认线上跑的版本与 harness 策略（Slice 04，§Design 2）。
    BUILD_INFO.labels(
        version=APP_VERSION, harness_policy=CognitiveHarnessPolicy().version
    ).set(1)

    try:
        yield
    finally:
        await stop_index_consumer()
        await _stop_handoff_sweep()
        await stop_chat_push_subscriber()
        await prompt_cache.stop_subscriber()
        await stop_route_map_subscriber()
        await close_http_client()
        dispose_agent_service()
        await llm_client.close()
        await engine.dispose()
        await redis_client.close()


def create_app() -> FastAPI:
    """创建 FastAPI 应用并挂载所有业务路由。"""
    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        lifespan=lifespan,
    )

    setup_middleware(app)
    register_exception_handlers(app)

    from askflow.rag.router import router as rag_router
    from askflow.embedding.router import router as embedding_router
    from askflow.chat.router import router as chat_router
    from askflow.agent.router import router as agent_router
    from askflow.ticket.router import router as ticket_router
    from askflow.admin.router import router as admin_router
    from askflow.admin.handoff_router import router as handoff_router
    from askflow.admin.prompt_router import router as prompt_router
    from askflow.admin.audit_router import router as audit_router
    from askflow.knowledge.router import router as knowledge_gaps_router
    from askflow.knowledge.router_drafts import router as knowledge_drafts_router
    from askflow.core.metrics import router as metrics_router

    # 业务接口统一挂在版本化前缀下，指标接口保持顶层，便于采集。
    app.include_router(rag_router, prefix="/api/v1/rag", tags=["RAG"])
    app.include_router(embedding_router, prefix="/api/v1/embedding", tags=["Embedding"])
    app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])
    app.include_router(agent_router, prefix="/api/v1/agent", tags=["Agent"])
    app.include_router(ticket_router, prefix="/api/v1/tickets", tags=["Tickets"])
    app.include_router(admin_router, prefix="/api/v1/admin", tags=["Admin"])
    app.include_router(handoff_router, prefix="/api/v1/admin/handoffs", tags=["Handoff"])
    app.include_router(prompt_router, prefix="/api/v1/admin/prompts", tags=["Prompts"])
    app.include_router(audit_router, prefix="/api/v1/admin/audit-logs", tags=["Audit"])
    app.include_router(knowledge_gaps_router, prefix="/api/v1/admin/gaps", tags=["Knowledge"])
    app.include_router(knowledge_drafts_router, prefix="/api/v1/admin/drafts", tags=["Knowledge"])
    app.include_router(metrics_router, tags=["Metrics"])

    @app.get("/", include_in_schema=False)
    async def index():
        return {
            "name": settings.app_name,
            "version": APP_VERSION,
            "docs": "/docs",
        }

    @app.get("/health")
    async def health(response: Response):
        """深度健康检查:并发探活 Postgres/Redis/Chroma/MinIO,任一失败返回 503。"""
        report = await check_health()
        if not report.ok:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": report.status, "checks": report.checks}

    return app
