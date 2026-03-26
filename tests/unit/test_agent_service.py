from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import askflow.agent.nodes as agent_nodes
import askflow.agent.service as agent_service_module
from askflow.agent.service import AgentService, invalidate_route_map_cache
from askflow.agent.state import AgentState
from askflow.schemas.intent import IntentResult


async def collect_stream(stream):
    return [chunk async for chunk in stream]


def make_stream(chunks):
    async def _stream():
        for chunk in chunks:
            yield chunk

    return _stream()


@pytest.fixture(autouse=True)
def clear_route_cache():
    invalidate_route_map_cache()
    yield
    invalidate_route_map_cache()


class TestAgentService:
    @pytest.mark.asyncio
    async def test_process_returns_rag_stream_for_rag_route(self, monkeypatch):
        classifier = MagicMock()
        rag_service = MagicMock()
        service = AgentService(classifier, rag_service)

        async def fake_classify_node(state, _classifier):
            state.intent = IntentResult(label="faq", confidence=0.95)
            return state

        async def fake_rag_stream_node(state, _rag_service):
            return make_stream(["hello", " world"]), [{"title": "FAQ", "score": 0.9}]

        monkeypatch.setattr(agent_nodes, "classify_node", fake_classify_node)
        monkeypatch.setattr(agent_service_module, "_load_route_map", AsyncMock(return_value={}))
        monkeypatch.setattr(agent_service_module, "rag_stream_node", fake_rag_stream_node)

        result = await service.process("How do I reset my password?")

        assert result.intent.label == "faq"
        assert result.sources == [{"title": "FAQ", "score": 0.9}]
        assert await collect_stream(result.token_stream) == ["hello", " world"]

    @pytest.mark.asyncio
    async def test_process_uses_graph_for_non_rag_routes(self, monkeypatch):
        classifier = MagicMock()
        rag_service = MagicMock()
        service = AgentService(classifier, rag_service)

        async def fake_classify_node(state, _classifier):
            state.intent = IntentResult(label="handoff", confidence=0.9)
            return state

        next_state = AgentState(
            question="Need a human",
            intent=IntentResult(label="handoff", confidence=0.9),
            response_tokens=["transferring"],
            should_handoff=True,
        )

        monkeypatch.setattr(agent_nodes, "classify_node", fake_classify_node)
        monkeypatch.setattr(agent_service_module, "_load_route_map", AsyncMock(return_value={}))
        service._graph.run = AsyncMock(return_value=next_state)

        result = await service.process("Need a human")

        service._graph.run.assert_awaited_once()
        assert result.should_handoff is True
        assert await collect_stream(result.token_stream) == ["transferring"]

    @pytest.mark.asyncio
    async def test_process_falls_back_when_classification_and_rag_fail(self, monkeypatch):
        classifier = MagicMock()
        rag_service = MagicMock()
        service = AgentService(classifier, rag_service)

        async def fake_classify_node(state, _classifier):
            raise RuntimeError("classification failed")

        async def fake_rag_stream_node(state, _rag_service):
            raise RuntimeError("rag failed")

        monkeypatch.setattr(agent_nodes, "classify_node", fake_classify_node)
        monkeypatch.setattr(agent_service_module, "_load_route_map", AsyncMock(return_value={}))
        monkeypatch.setattr(agent_service_module, "rag_stream_node", fake_rag_stream_node)

        result = await service.process("What happened?")

        assert result.intent.label == "faq"
        assert result.sources == []
        assert await collect_stream(result.token_stream) == ["抱歉，暂时无法检索信息，请稍后再试。"]
