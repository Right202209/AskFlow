"""弱检索确定性拒答（plan-docs/honest-rag/01）。

覆盖目标：
- 弱/零命中时 `query_stream` / `query` 直接返回 REFUSAL_RESPONSE，LLM 一次都不能被调用；
- 拒答流经过 `harness.wrap_stream` 后原样送达（空流会被改写成通用兜底文案的回归位）；
- `AgentService.process` 在弱检索时把 `weak_retrieval_refusal` + `retrieval_confidence`
  写入 harness trace；强检索行为不变、无 flag。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import askflow.agent.service as agent_service_module
from askflow.agent.harness import CognitiveHarness
from askflow.agent.nodes import rag_node
from askflow.agent.service import AgentService, invalidate_route_map_cache
from askflow.agent.state import AgentState
from askflow.rag.grounding import (
    REFUSAL_MAX_SOURCES,
    REFUSAL_RESPONSE,
    WEAK_RETRIEVAL_REFUSAL_FLAG,
)
from askflow.rag.retriever import RetrievalResult
from askflow.rag.service import RAGService
from askflow.schemas.intent import IntentResult


async def collect_stream(stream):
    return [chunk async for chunk in stream]


def make_stream(chunks):
    async def _stream():
        for chunk in chunks:
            yield chunk

    return _stream()


def make_results(scores: list[float]) -> list[RetrievalResult]:
    return [
        RetrievalResult(
            id=f"c{i}",
            document=f"chunk {i}",
            metadata={"title": f"Doc {i}"},
            score=score,
            source="vector",
        )
        for i, score in enumerate(scores)
    ]


def build_rag_service(results: list[RetrievalResult]) -> tuple[RAGService, MagicMock]:
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=results)
    reranker = MagicMock()
    reranker.rerank = AsyncMock(side_effect=lambda q, r, top_k=5: r[:top_k])
    llm = MagicMock()
    llm.chat = AsyncMock(return_value="llm answer")
    llm.chat_stream = MagicMock(return_value=make_stream(["llm", " answer"]))
    return RAGService(retriever, reranker, llm), llm


WEAK_SCORES = [0.05, 0.04, 0.03, 0.02]
STRONG_SCORES = [0.92, 0.81]


@pytest.fixture(autouse=True)
def clear_route_cache():
    invalidate_route_map_cache()
    yield
    invalidate_route_map_cache()


class TestRAGServiceRefusal:
    @pytest.mark.asyncio
    async def test_weak_retrieval_stream_refuses_without_calling_llm(self):
        service, llm = build_rag_service(make_results(WEAK_SCORES))

        result = await service.query_stream("你们支持量子加密传输吗?")

        assert await collect_stream(result.token_stream) == [REFUSAL_RESPONSE]
        llm.chat_stream.assert_not_called()
        assert result.grounding.grounded is False
        # 弱证据仍要展示（封顶），让用户看到"为什么不答"。
        assert len(result.sources) == REFUSAL_MAX_SOURCES

    @pytest.mark.asyncio
    async def test_zero_hits_refuse_with_empty_sources(self):
        service, llm = build_rag_service([])

        result = await service.query_stream("完全无关的问题")

        assert await collect_stream(result.token_stream) == [REFUSAL_RESPONSE]
        assert result.sources == []
        assert result.grounding.channel == "empty"
        llm.chat_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_stream_query_refuses_for_rest_path(self):
        service, llm = build_rag_service(make_results(WEAK_SCORES))

        result = await service.query("你们支持量子加密传输吗?")

        assert result.answer == REFUSAL_RESPONSE
        assert result.grounding.grounded is False
        assert len(result.sources) == REFUSAL_MAX_SOURCES
        llm.chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refusal_stream_survives_harness_wrap_unchanged(self):
        # 回归位：拒答若实现成空流，wrap_stream 会把它改写成通用兜底文案。
        service, _llm = build_rag_service([])
        harness = CognitiveHarness()

        result = await service.query_stream("完全无关的问题")
        wrapped = harness.wrap_stream(result.token_stream)

        assert await collect_stream(wrapped) == [REFUSAL_RESPONSE]

    @pytest.mark.asyncio
    async def test_strong_retrieval_streams_llm_answer_unchanged(self):
        service, llm = build_rag_service(make_results(STRONG_SCORES))

        result = await service.query_stream("退款政策是什么?")

        assert await collect_stream(result.token_stream) == ["llm", " answer"]
        llm.chat_stream.assert_called_once()
        assert result.grounding.grounded is True
        assert len(result.sources) == len(STRONG_SCORES)


class TestAgentServiceGroundingTrace:
    def _build_agent(self, rag_service: RAGService, monkeypatch) -> AgentService:
        classifier = MagicMock()
        classifier.classify = AsyncMock(
            return_value=IntentResult(label="faq", confidence=0.95)
        )
        monkeypatch.setattr(
            agent_service_module, "_load_route_map", AsyncMock(return_value={})
        )
        return AgentService(classifier, rag_service)

    @pytest.mark.asyncio
    async def test_weak_retrieval_process_flags_trace_and_refuses(self, monkeypatch):
        rag_service, llm = build_rag_service(make_results(WEAK_SCORES))
        agent = self._build_agent(rag_service, monkeypatch)

        result = await agent.process("你们支持量子加密传输吗?")

        assert await collect_stream(result.token_stream) == [REFUSAL_RESPONSE]
        assert WEAK_RETRIEVAL_REFUSAL_FLAG in result.harness_trace["flags"]
        assert result.harness_trace["retrieval_confidence"] == pytest.approx(0.05)
        assert result.harness_trace["retrieval_channel"] == "vector"
        assert len(result.sources) == REFUSAL_MAX_SOURCES
        llm.chat_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_strong_retrieval_process_records_confidence_without_flag(
        self, monkeypatch
    ):
        rag_service, llm = build_rag_service(make_results(STRONG_SCORES))
        agent = self._build_agent(rag_service, monkeypatch)

        result = await agent.process("退款政策是什么?")

        assert await collect_stream(result.token_stream) == ["llm", " answer"]
        assert WEAK_RETRIEVAL_REFUSAL_FLAG not in result.harness_trace["flags"]
        assert result.harness_trace["retrieval_confidence"] == pytest.approx(0.92)
        assert result.harness_trace["retrieval_channel"] == "vector"
        llm.chat_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_graph_rag_node_records_trace_too(self):
        # AgentGraph 走的 rag_node 与流式路径共享同一套 grounding trace 记录。
        rag_service, _llm = build_rag_service(make_results(WEAK_SCORES))
        state = AgentState(question="你们支持量子加密传输吗?")

        state = await rag_node(state, rag_service)

        assert state.response_tokens == [REFUSAL_RESPONSE]
        assert WEAK_RETRIEVAL_REFUSAL_FLAG in state.harness_trace["flags"]
        assert state.harness_trace["retrieval_confidence"] == pytest.approx(0.05)
