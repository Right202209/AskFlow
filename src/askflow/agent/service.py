from __future__ import annotations

from collections.abc import AsyncIterator

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
from askflow.schemas.intent import IntentResult

logger = get_logger(__name__)


class AgentService:
    def __init__(self, classifier: IntentClassifier, rag_service: RAGService) -> None:
        self._classifier = classifier
        self._rag_service = rag_service
        self._graph = AgentGraph(classifier, rag_service)

    async def process(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        user_id: str = "",
        conversation_id: str = "",
    ) -> tuple[AsyncIterator[str], list[dict], IntentResult | None]:
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

        route = route_by_intent(state)
        logger.info("agent_route_decision", route=route)

        if route == "rag":
            try:
                token_stream, sources = await rag_stream_node(state, self._rag_service)
                return token_stream, sources, state.intent
            except Exception as e:
                logger.error("rag_failed", error=str(e))

                async def error_stream():
                    yield "Sorry, I'm having trouble finding information right now. Please try again later."

                return error_stream(), [], state.intent

        state = await self._graph.run(state)

        async def token_iter():
            for token in state.response_tokens:
                yield token

        return token_iter(), state.sources, state.intent


def get_agent_service() -> AgentService:
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
