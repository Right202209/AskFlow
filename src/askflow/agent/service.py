from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from askflow.agent.graph import AgentGraph
from askflow.agent.harness import CognitiveHarness
from askflow.agent.intent_classifier import DEFAULT_INTENT, IntentClassifier
from askflow.agent.nodes import rag_stream_node, route_by_intent
from askflow.core.logging import get_logger
from askflow.core.redis import redis_client
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
# 本地缓存 TTL：即便 pub/sub 漏消息，60s 也能最终一致。
ROUTE_MAP_CACHE_TTL_SECONDS = 60.0

_route_map_cache: dict[str, str] | None = None
_route_map_cache_at: float = 0.0
_route_map_subscriber_task: asyncio.Task | None = None


async def _load_route_map() -> dict[str, str]:
    """缓存读取生效中的意图路由配置；本地 TTL + Redis 失效广播保持跨 worker 一致。"""
    global _route_map_cache, _route_map_cache_at
    now = time.monotonic()
    if _route_map_cache is not None and now - _route_map_cache_at < ROUTE_MAP_CACHE_TTL_SECONDS:
        return _route_map_cache
    try:
        from askflow.core.database import async_session_factory
        from askflow.repositories.intent_config_repo import IntentConfigRepo

        async with async_session_factory() as db:
            repo = IntentConfigRepo(db)
            configs = await repo.get_all_active()
            _route_map_cache = {c.name: c.route_target for c in configs}
    except Exception as e:
        logger.warning("failed_to_load_route_map", error=str(e))
        _route_map_cache = {}
    _route_map_cache_at = now
    return _route_map_cache


def invalidate_route_map_cache() -> None:
    """清本地缓存——下一次 _load_route_map 会从 DB 重新拉。"""
    global _route_map_cache, _route_map_cache_at
    _route_map_cache = None
    _route_map_cache_at = 0.0


async def publish_route_map_invalidation() -> None:
    """通过 Redis 通知其他 worker 也清缓存。Redis 不可用直接吞——TTL 60s 兜底。"""
    try:
        await redis_client.pool.publish(ROUTE_MAP_INVALIDATE_CHANNEL, "invalidate")
    except Exception as e:
        logger.warning("route_map_invalidate_publish_failed", error=str(e))


async def _route_map_invalidate_listener() -> None:
    """订阅 invalidate 频道；任何消息进来都让本地缓存失效。"""
    try:
        pubsub = redis_client.pool.pubsub()
    except Exception as e:
        logger.warning("route_map_subscriber_init_failed", error=str(e))
        return

    try:
        await pubsub.subscribe(ROUTE_MAP_INVALIDATE_CHANNEL)
        async for message in pubsub.listen():
            if not message or message.get("type") != "message":
                continue
            invalidate_route_map_cache()
            logger.info("route_map_cache_invalidated_via_pubsub")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("route_map_subscriber_error", error=str(e))
    finally:
        try:
            await pubsub.unsubscribe(ROUTE_MAP_INVALIDATE_CHANNEL)
            await pubsub.aclose()
        except Exception:
            pass


def start_route_map_subscriber() -> asyncio.Task:
    """lifespan 启动期挂上后台订阅协程，已存在则复用。"""
    global _route_map_subscriber_task
    if _route_map_subscriber_task and not _route_map_subscriber_task.done():
        return _route_map_subscriber_task
    _route_map_subscriber_task = asyncio.create_task(_route_map_invalidate_listener())
    return _route_map_subscriber_task


async def stop_route_map_subscriber() -> None:
    """lifespan 关停期取消后台订阅协程，避免悬挂连接。"""
    global _route_map_subscriber_task
    task = _route_map_subscriber_task
    _route_map_subscriber_task = None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("route_map_subscriber_stop_error", error=str(e))


class ProcessResult:
    """AgentService.process 的返回值，包含流式 token、来源、意图以及副作用元数据。"""

    __slots__ = (
        "token_stream",
        "sources",
        "intent",
        "ticket_data",
        "should_handoff",
        "tool_result",
        "harness_trace",
    )

    def __init__(
        self,
        token_stream: AsyncIterator[str],
        sources: list[dict],
        intent: IntentResult | None,
        ticket_data: dict[str, Any] | None = None,
        should_handoff: bool = False,
        tool_result: dict[str, Any] | None = None,
        harness_trace: dict[str, Any] | None = None,
    ) -> None:
        self.token_stream = token_stream
        self.sources = sources
        self.intent = intent
        self.ticket_data = ticket_data
        self.should_handoff = should_handoff
        self.tool_result = tool_result
        self.harness_trace = harness_trace or {}


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

        try:
            from askflow.agent.nodes import classify_node

            state = await classify_node(state, self._classifier)
        except Exception as e:
            logger.warning("classification_failed_fallback_rag", error=str(e))
            state.intent = IntentResult(label=DEFAULT_INTENT, confidence=0.5)

        route_map = await _load_route_map()
        candidate_route = route_by_intent(state, route_map=route_map)
        route = self._harness.choose_route(state, candidate_route)
        logger.info("agent_route_decision", route=route)

        if route == "rag":
            try:
                token_stream, sources = await rag_stream_node(state, self._rag_service)
                return ProcessResult(
                    token_stream=self._harness.wrap_stream(token_stream),
                    sources=sources,
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

        state = await self._graph.run(
            state,
            ticket_service=ticket_service,
            conversation_repo=conversation_repo,
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
