from contextlib import asynccontextmanager

from fastapi import FastAPI

from askflow.agent.service import (
    build_agent_service,
    dispose_agent_service,
    init_agent_service,
    start_route_map_subscriber,
    stop_route_map_subscriber,
)
from askflow.config import settings
from askflow.core.database import engine
from askflow.core.exceptions import register_exception_handlers
from askflow.core.logging import get_logger
from askflow.core.middleware import setup_middleware
from askflow.core.redis import redis_client
from askflow.rag.bm25 import bm25_index
from askflow.rag.llm_client import llm_client
from askflow.rag.vector_store import get_vector_store

DEFAULT_SECRET_KEY = "change-me-to-a-random-secret-key"

logger = get_logger(__name__)


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

    # 应用启动期一次性装配 AgentService（embedder / vector_store / retriever /
    # reranker / RAG / IntentClassifier / AgentGraph），避免每条用户消息都重建整条栈。
    agent_service = build_agent_service()
    init_agent_service(agent_service)
    app.state.agent_service = agent_service

    try:
        yield
    finally:
        await stop_route_map_subscriber()
        dispose_agent_service()
        await llm_client.close()
        await engine.dispose()
        await redis_client.close()


def create_app() -> FastAPI:
    """创建 FastAPI 应用并挂载所有业务路由。"""
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
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
    from askflow.core.metrics import router as metrics_router

    # 业务接口统一挂在版本化前缀下，指标接口保持顶层，便于采集。
    app.include_router(rag_router, prefix="/api/v1/rag", tags=["RAG"])
    app.include_router(embedding_router, prefix="/api/v1/embedding", tags=["Embedding"])
    app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])
    app.include_router(agent_router, prefix="/api/v1/agent", tags=["Agent"])
    app.include_router(ticket_router, prefix="/api/v1/tickets", tags=["Tickets"])
    app.include_router(admin_router, prefix="/api/v1/admin", tags=["Admin"])
    app.include_router(metrics_router, tags=["Metrics"])

    @app.get("/", include_in_schema=False)
    async def index():
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "docs": "/docs",
        }

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
