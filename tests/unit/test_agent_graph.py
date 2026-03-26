from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import askflow.agent.nodes as agent_nodes
from askflow.agent.graph import AgentGraph
from askflow.agent.state import AgentState
from askflow.schemas.intent import IntentResult


class TestAgentGraph:
    @pytest.mark.asyncio
    async def test_run_classifies_then_routes_to_rag(self, monkeypatch):
        graph = AgentGraph(MagicMock(), MagicMock())
        state = AgentState(question="What is the refund policy?")

        async def fake_classify_node(current_state, _classifier):
            current_state.intent = IntentResult(label="faq", confidence=0.9)
            return current_state

        async def fake_rag_node(current_state, _rag_service):
            current_state.response_tokens = ["policy details"]
            return current_state

        monkeypatch.setattr(agent_nodes, "classify_node", fake_classify_node)
        monkeypatch.setattr(agent_nodes, "rag_node", fake_rag_node)

        result = await graph.run(state, route_map={})

        assert result.intent.label == "faq"
        assert result.response_tokens == ["policy details"]

    @pytest.mark.asyncio
    async def test_run_returns_ticket_unavailable_when_service_missing(self):
        graph = AgentGraph(MagicMock(), MagicMock(), ticket_service=None)
        state = AgentState(intent=IntentResult(label="fault_report", confidence=0.9))

        result = await graph.run(state, route_map={})

        assert result.response_tokens == ["工单服务暂不可用，请联系人工客服。"]

    @pytest.mark.asyncio
    async def test_run_routes_to_tool_node(self, monkeypatch):
        graph = AgentGraph(MagicMock(), MagicMock())
        state = AgentState(intent=IntentResult(label="order_query", confidence=0.95))

        async def fake_tool_node(current_state):
            current_state.response_tokens = ["订单已发货"]
            return current_state

        monkeypatch.setattr(agent_nodes, "tool_node", fake_tool_node)

        result = await graph.run(state, route_map={})

        assert result.response_tokens == ["订单已发货"]
