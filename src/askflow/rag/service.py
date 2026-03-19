from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from askflow.core.logging import get_logger
from askflow.core.metrics import RAG_QUERY_COUNT, RAG_QUERY_LATENCY
from askflow.embedding.embedder import Embedder
from askflow.rag.llm_client import LLMClient
from askflow.rag.prompt_builder import build_fallback_response, build_rag_prompt
from askflow.rag.reranker import Reranker
from askflow.rag.retriever import HybridRetriever, RetrievalResult
from askflow.rag.vector_store import VectorStore

logger = get_logger(__name__)


@dataclass
class RAGResult:
    answer: str
    sources: list[dict]
    intent: str | None = None
    confidence: float | None = None


class RAGService:
    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: Reranker,
        llm: LLMClient,
    ) -> None:
        self._retriever = retriever
        self._reranker = reranker
        self._llm = llm

    async def query(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        top_k: int = 5,
    ) -> RAGResult:
        RAG_QUERY_COUNT.inc()
        results = await self._retriever.retrieve(question, top_k=top_k * 2)
        results = await self._reranker.rerank(question, results, top_k=top_k)
        sources = [
            {"title": r.metadata.get("title", ""), "chunk": r.document[:200], "score": r.score}
            for r in results
        ]

        try:
            messages = build_rag_prompt(question, results, conversation_history)
            answer = await self._llm.chat(messages)
        except Exception as e:
            logger.warning("llm_unavailable_fallback", error=str(e))
            answer = build_fallback_response(results)

        return RAGResult(answer=answer, sources=sources)

    async def query_stream(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        top_k: int = 5,
    ) -> tuple[AsyncIterator[str], list[dict]]:
        RAG_QUERY_COUNT.inc()
        results = await self._retriever.retrieve(question, top_k=top_k * 2)
        results = await self._reranker.rerank(question, results, top_k=top_k)
        sources = [
            {"title": r.metadata.get("title", ""), "chunk": r.document[:200], "score": r.score}
            for r in results
        ]
        messages = build_rag_prompt(question, results, conversation_history)

        async def _generate():
            try:
                async for token in self._llm.chat_stream(messages):
                    yield token
            except Exception as e:
                logger.warning("llm_stream_failed", error=str(e))
                yield build_fallback_response(results)

        return _generate(), sources
