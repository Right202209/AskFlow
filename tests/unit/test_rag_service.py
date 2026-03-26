from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from askflow.rag.retriever import RetrievalResult
from askflow.rag.service import RAGService


async def collect_stream(stream):
    return [chunk async for chunk in stream]


def make_stream(chunks):
    async def _stream():
        for chunk in chunks:
            yield chunk

    return _stream()


def make_results():
    return [
        RetrievalResult(
            id="doc-1",
            document="Reset your password from the account settings page.",
            metadata={"title": "Password Reset"},
            score=0.91,
            source="vector",
        ),
        RetrievalResult(
            id="doc-2",
            document="Contact support if you cannot access the email inbox.",
            metadata={"title": "Support"},
            score=0.75,
            source="bm25",
        ),
    ]


class TestRAGService:
    @pytest.mark.asyncio
    async def test_query_returns_answer_and_sources(self):
        results = make_results()
        retriever = MagicMock()
        retriever.retrieve = AsyncMock(return_value=results)
        reranker = MagicMock()
        reranker.rerank = AsyncMock(return_value=results[:1])
        llm = MagicMock()
        llm.chat = AsyncMock(return_value="Use the password reset page.")
        service = RAGService(retriever, reranker, llm)

        result = await service.query("How do I reset my password?")

        assert result.answer == "Use the password reset page."
        assert result.sources == [
            {
                "title": "Password Reset",
                "chunk": "Reset your password from the account settings page.",
                "score": 0.91,
            }
        ]

    @pytest.mark.asyncio
    async def test_query_falls_back_when_llm_is_unavailable(self):
        results = make_results()
        retriever = MagicMock()
        retriever.retrieve = AsyncMock(return_value=results)
        reranker = MagicMock()
        reranker.rerank = AsyncMock(return_value=results)
        llm = MagicMock()
        llm.chat = AsyncMock(side_effect=RuntimeError("llm down"))
        service = RAGService(retriever, reranker, llm)

        result = await service.query("How do I reset my password?")

        assert "AI generation is temporarily unavailable." in result.answer
        assert "Password Reset" in result.answer

    @pytest.mark.asyncio
    async def test_query_stream_yields_tokens(self):
        results = make_results()
        retriever = MagicMock()
        retriever.retrieve = AsyncMock(return_value=results)
        reranker = MagicMock()
        reranker.rerank = AsyncMock(return_value=results[:1])
        llm = MagicMock()
        llm.chat_stream = MagicMock(return_value=make_stream(["Use", " settings"]))
        service = RAGService(retriever, reranker, llm)

        stream, sources = await service.query_stream("How do I reset my password?")

        assert sources[0]["title"] == "Password Reset"
        assert await collect_stream(stream) == ["Use", " settings"]

    @pytest.mark.asyncio
    async def test_query_stream_falls_back_when_streaming_fails(self):
        results = make_results()
        retriever = MagicMock()
        retriever.retrieve = AsyncMock(return_value=results)
        reranker = MagicMock()
        reranker.rerank = AsyncMock(return_value=results)
        llm = MagicMock()

        async def failing_stream(messages):
            raise RuntimeError("stream failed")
            yield  # pragma: no cover

        llm.chat_stream = failing_stream
        service = RAGService(retriever, reranker, llm)

        stream, _sources = await service.query_stream("How do I reset my password?")

        chunks = await collect_stream(stream)
        assert len(chunks) == 1
        assert "AI generation is temporarily unavailable." in chunks[0]
