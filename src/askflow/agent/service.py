from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from askflow.agent.graph import AgentGraph
from askflow.agent.harness import CognitiveHarness
from askflow.agent.intent_classifier import DEFAULT_INTENT, IntentClassifier
from askflow.agent.nodes import rag_stream_node, route_by_intent
from askflow.agent.result import ProcessResult as ProcessResult  # 再导出：兼容既有导入路径
from askflow.agent.slots import resume_pending_route, settle_pending_after_classify
from askflow.agent.state import AgentState
from askflow.core.config_cache import CONFIG_CACHE_TTL_SECONDS, ConfigCache
from askflow.core.logging import get_logger
from askflow.embedding.embedder import create_embedder
from askflow.rag.llm_client import llm_client
from askflow.rag.reranker import Reranker
from askflow.rag.retriever import HybridRetriever
from askflow.rag.service import RAGService
from askflow.rag.vector_store import get_vector_store
from askflow.repositories.conversation_repo import ConversationRepo
from askflow.schemas.intent import IntentResult
from askflow.ticket.service import TicketService

logger = get_logger(__name__)

# Redis pub/sub channel——任何 worker 写完意图配置都向这里发"invalidate"。
ROUTE_MAP_INVALIDATE_CHANNEL = "askflow:route_map:invalidate"
# 本地缓存 TTL：即便 pub/sub 漏消息，60s 也能最终一致（常量随 ConfigCache 抽取共享）。
ROUTE_MAP_CACHE_TTL_SECONDS = CONFIG_CACHE_TTL_SECONDS


async def _route_map_loader() -> dict[str, str]:
    """从 DB 拉取生效中的意图路由映射；失败返回空表（走内置兜底路由）。"""
    try:
        # 函数内导入：单测通过 monkeypatch 源模块属性打桩，必须在调用时解析。
        from askflow.core.database import async_session_factory
        from askflow.repositories.intent_config_repo import IntentConfigRepo

        async with async_session_factory() as db:
            configs = await IntentConfigRepo(db).get_all_active()
            return {c.name: c.route_target for c in configs}
    except Exception as e:
        logger.warning("failed_to_load_route_map", error=str(e))
        return {}


# TTL + epoch + pub/sub 语义整体抽到 core/config_cache.py（ops-platform/01 D1），
# 这里只保留装配与兼容包装；提示词缓存（core/prompts.py）复用同一套机制。
route_map_cache: ConfigCache[dict[str, str]] = ConfigCache(
    name="route_map",
    channel=ROUTE_MAP_INVALIDATE_CHANNEL,
    loader=_route_map_loader,
)


async def _load_route_map() -> dict[str, str]:
    """缓存读取生效中的意图路由配置；本地 TTL + Redis 失效广播保持跨 worker 一致。"""
    return await route_map_cache.get()


def invalidate_route_map_cache() -> None:
    """清本地缓存——下一次 _load_route_map 会从 DB 重新拉。"""
    route_map_cache.invalidate()


async def publish_route_map_invalidation() -> None:
    """通过 Redis 通知其他 worker 也清缓存。Redis 不可用直接吞——TTL 60s 兜底。"""
    await route_map_cache.publish_invalidation()


def start_route_map_subscriber() -> asyncio.Task:
    """lifespan 启动期挂上后台订阅协程，已存在则复用。"""
    return route_map_cache.start_subscriber()


async def stop_route_map_subscriber() -> None:
    """lifespan 关停期取消后台订阅协程，避免悬挂连接。"""
    await route_map_cache.stop_subscriber()


def __getattr__(name: str):
    """PEP 562：保留 `_route_map_cache` / `_route_map_invalidate_seq` 只读别名。

    test_route_map_epoch.py 与诊断脚本读这两个旧模块属性观察缓存状态；
    抽取到 ConfigCache 后由实例属性投影，外部读法不变（只读，写入不再支持）。
    """
    if name == "_route_map_cache":
        return route_map_cache.snapshot
    if name == "_route_map_invalidate_seq":
        return route_map_cache.invalidate_seq
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class AgentService:
    """协调意图分类、路由决策和最终响应流的输出。

    依赖装配只在应用启动时做一次。需要 DB 的 ticket_service / conversation_repo
    每条请求通过 process() 的参数传入——它们与请求级 AsyncSession 绑定，不能跨请求复用。
    """

    def __init__(
        self,
        classifier: IntentClassifier,
        rag_service: RAGService,
        harness: CognitiveHarness | None = None,
    ) -> None:
        self._classifier = classifier
        self._rag_service = rag_service
        self._harness = harness or CognitiveHarness()
        self._graph = AgentGraph(classifier, rag_service)

    async def process(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        user_id: str = "",
        conversation_id: str = "",
        *,
        ticket_service: TicketService | None = None,
        conversation_repo: ConversationRepo | None = None,
        handoff_service=None,
        pending_tool: dict | None = None,
    ) -> ProcessResult:
        """返回 ProcessResult，包含响应 token 流、引用来源、意图及副作用元数据。"""
        prepared = self._harness.prepare(
            question=question,
            conversation_history=conversation_history or [],
            user_id=user_id,
            conversation_id=conversation_id,
        )
        state = prepared.state

        if prepared.action == "stop":
            return ProcessResult(
                token_stream=self._state_token_stream(state.response_tokens),
                sources=[],
                intent=state.intent,
                harness_trace=state.harness_trace,
            )

        # 挂起槽位续跑（agent-real-handoff/01）：正则先于分类，命中直接免分类续跑 tool。
        slot_route = resume_pending_route(state, pending_tool)
        if slot_route is None:
            state = await self._classify_state(state)
            slot_route = await settle_pending_after_classify(state, conversation_repo)

        route_map = await _load_route_map()
        candidate_route = slot_route or route_by_intent(state, route_map=route_map)
        route = self._harness.choose_route(state, candidate_route)
        logger.info("agent_route_decision", route=route)

        if route == "rag":
            return await self._run_rag_branch(state)

        state = await self._graph.run(
            state,
            ticket_service=ticket_service,
            conversation_repo=conversation_repo,
            handoff_service=handoff_service,
            route_map=route_map,
        )
        state = self._harness.finalize_state(state)

        return ProcessResult(
            token_stream=self._state_token_stream(state.response_tokens),
            sources=state.sources,
            intent=state.intent,
            ticket_data=state.ticket_data,
            should_handoff=state.should_handoff,
            tool_result=state.tool_result,
            harness_trace=state.harness_trace,
        )

    async def _classify_state(self, state: AgentState) -> AgentState:
        try:
            from askflow.agent.nodes import classify_node

            return await classify_node(state, self._classifier)
        except Exception as e:
            logger.warning("classification_failed_fallback_rag", error=str(e))
            state.intent = IntentResult(label=DEFAULT_INTENT, confidence=0.5)
            return state

    async def _run_rag_branch(self, state: AgentState) -> ProcessResult:
        try:
            rag_result = await rag_stream_node(state, self._rag_service)
            return ProcessResult(
                token_stream=self._harness.wrap_stream(rag_result.token_stream),
                sources=rag_result.sources,
                intent=state.intent,
                harness_trace=state.harness_trace,
            )
        except Exception as e:
            logger.error("rag_failed", error=str(e))

            async def error_stream():
                yield "抱歉，暂时无法检索信息，请稍后再试。"

            return ProcessResult(
                token_stream=error_stream(),
                sources=[],
                intent=state.intent,
                harness_trace=state.harness_trace,
            )

    async def _state_token_stream(self, response_tokens: list[str]) -> AsyncIterator[str]:
        import asyncio

        for token in response_tokens:
            yield token
            await asyncio.sleep(0.05)


# 模块级单例：lifespan 启动期通过 init_agent_service() 注入，调用方走 get_agent_service()。
_agent_service_singleton: AgentService | None = None


def init_agent_service(service: AgentService) -> None:
    """让应用启动期把组装好的 AgentService 挂到模块单例上。

    重复调用会覆盖现有单例——这只在测试里有意义；生产路径只在 lifespan 调一次。
    """
    global _agent_service_singleton
    _agent_service_singleton = service


def dispose_agent_service() -> None:
    global _agent_service_singleton
    _agent_service_singleton = None


def build_agent_service() -> AgentService:
    """构造一份默认 Agent 装配——给 lifespan 与测试共用。"""
    embedder = create_embedder()
    try:
        vector_store = get_vector_store()
    except Exception:
        vector_store = None

    retriever = HybridRetriever(embedder, vector_store) if vector_store else None
    reranker = Reranker()
    rag_service = RAGService(retriever, reranker, llm_client) if retriever else None
    classifier = IntentClassifier(llm_client)
    return AgentService(classifier, rag_service)


def get_agent_service() -> AgentService:
    """返回启动期注入的单例。未初始化时按需懒装配——给单元测试兜底。"""
    global _agent_service_singleton
    if _agent_service_singleton is None:
        # 兜底装配：让单测/管理路由（/agent/classify）即使在没有 lifespan 的场景下也能跑。
        # 真实部署路径会被 lifespan 的 init_agent_service() 提前覆盖掉。
        _agent_service_singleton = build_agent_service()
    return _agent_service_singleton
