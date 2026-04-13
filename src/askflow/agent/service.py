from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from askflow.agent.graph import AgentGraph
from askflow.agent.intent_classifier import IntentClassifier
from askflow.agent.nodes import rag_stream_node, route_by_intent
from askflow.agent.state import AgentState
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

_route_map_cache: dict[str, str] | None = None


async def _load_route_map() -> dict[str, str]:
    """缓存读取生效中的意图路由配置，减少每次请求都查库。"""
    global _route_map_cache
    if _route_map_cache is not None:
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
    return _route_map_cache


def invalidate_route_map_cache() -> None:
    global _route_map_cache
    _route_map_cache = None


class ProcessResult:
    """AgentService.process 的返回值，包含流式 token、来源、意图以及副作用元数据。"""

    __slots__ = (
        "token_stream",
        "sources",
        "intent",
        "ticket_data",
        "should_handoff",
        "tool_result",
    )

    def __init__(
        self,
        token_stream: AsyncIterator[str],
        sources: list[dict],
        intent: IntentResult | None,
        ticket_data: dict[str, Any] | None = None,
        should_handoff: bool = False,
        tool_result: dict[str, Any] | None = None,
    ) -> None:
        self.token_stream = token_stream
        self.sources = sources
        self.intent = intent
        self.ticket_data = ticket_data
        self.should_handoff = should_handoff
        self.tool_result = tool_result


class AgentService:
    """协调意图分类、路由决策和最终响应流的输出。"""

    def __init__(
        self,
        classifier: IntentClassifier,
        rag_service: RAGService,
        ticket_service: TicketService | None = None,
        conversation_repo: ConversationRepo | None = None,
    ) -> None:
        self._classifier = classifier
        self._rag_service = rag_service
        self._ticket_service = ticket_service
        self._conversation_repo = conversation_repo
        self._graph = AgentGraph(
            classifier,
            rag_service,
            ticket_service=ticket_service,
            conversation_repo=conversation_repo,
        )

    async def process(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        user_id: str = "",
        conversation_id: str = "",
    ) -> ProcessResult:
        """返回 ProcessResult，包含响应 token 流、引用来源、意图及副作用元数据。"""
        state = AgentState(
            question=question,
            conversation_history=conversation_history or [],
            user_id=user_id,
            conversation_id=conversation_id,
        )

        try:
            from askflow.agent.nodes import classify_node

            state = await classify_node(state, self._classifier)
        except Exception as e:
            logger.warning("classification_failed_fallback_rag", error=str(e))
            state.intent = IntentResult(label="faq", confidence=0.5)

        route_map = await _load_route_map()
        route = route_by_intent(state, route_map=route_map)
        logger.info("agent_route_decision", route=route)

        if route == "rag":
            try:
                token_stream, sources = await rag_stream_node(state, self._rag_service)
                return ProcessResult(
                    token_stream=token_stream,
                    sources=sources,
                    intent=state.intent,
                )
            except Exception as e:
                logger.error("rag_failed", error=str(e))

                async def error_stream():
                    yield "抱歉，暂时无法检索信息，请稍后再试。"

                return ProcessResult(
                    token_stream=error_stream(),
                    sources=[],
                    intent=state.intent,
                )

        state = await self._graph.run(state, route_map=route_map)

        import asyncio

        async def token_iter():
            for token in state.response_tokens:
                # 如果单个 token 是一整句话，按较小粒度（比如两三个字符）拆分，模拟打字机体验
                if len(token) > 3:
                    for i in range(0, len(token), 2):
                        yield token[i:i+2]
                        await asyncio.sleep(0.05)
                else:
                    yield token
                    await asyncio.sleep(0.05)
                # 每句话后面加一个空格或换行
                yield "\n"

        return ProcessResult(
            token_stream=token_iter(),
            sources=state.sources,
            intent=state.intent,
            ticket_data=state.ticket_data,
            should_handoff=state.should_handoff,
            tool_result=state.tool_result,
        )


def get_agent_service(
    ticket_service: TicketService | None = None,
    conversation_repo: ConversationRepo | None = None,
) -> AgentService:
    """构造默认的 Agent 依赖装配，供路由层复用。"""
    embedder = create_embedder()
    try:
        vector_store = get_vector_store()
    except Exception:
        vector_store = None

    retriever = HybridRetriever(embedder, vector_store) if vector_store else None
    reranker = Reranker()
    rag_service = RAGService(retriever, reranker, llm_client) if retriever else None
    classifier = IntentClassifier(llm_client)
    return AgentService(
        classifier,
        rag_service,
        ticket_service=ticket_service,
        conversation_repo=conversation_repo,
    )
