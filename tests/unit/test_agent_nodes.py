from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import askflow.agent.tools as tools_module
from askflow.agent.nodes import handoff_node, rag_node, ticket_node, tool_node
from askflow.agent.state import AgentState
from askflow.models.ticket import TicketPriority, TicketStatus
from askflow.schemas.intent import IntentResult


def make_stream(chunks):
    async def _stream():
        for chunk in chunks:
            yield chunk

    return _stream()


class TestAgentNodes:
    @pytest.mark.asyncio
    async def test_rag_node_collects_stream_tokens(self):
        state = AgentState(question="hello")
        rag_service = AsyncMock()
        rag_service.query_stream.return_value = (
            make_stream(["A", "B"]),
            [{"title": "Guide", "score": 0.8}],
        )

        result = await rag_node(state, rag_service)

        assert result.response_tokens == ["A", "B"]
        assert result.sources == [{"title": "Guide", "score": 0.8}]

    @pytest.mark.asyncio
    async def test_ticket_node_creates_ticket_and_populates_state(self):
        user_id = uuid.uuid4()
        conversation_id = uuid.uuid4()
        ticket = SimpleNamespace(
            id=uuid.uuid4(),
            status=TicketStatus.pending,
            type="fault_report",
            priority=TicketPriority.high,
        )
        ticket_service = AsyncMock()
        ticket_service.create_ticket.return_value = ticket
        state = AgentState(
            question="The app is broken",
            user_id=str(user_id),
            conversation_id=str(conversation_id),
            intent=IntentResult(label="fault_report", confidence=0.9),
        )

        result = await ticket_node(state, ticket_service)

        ticket_service.create_ticket.assert_awaited_once()
        assert result.ticket_id == str(ticket.id)
        assert result.ticket_data == {
            "ticket_id": str(ticket.id),
            "status": "pending",
            "type": "fault_report",
            "priority": "high",
        }
        assert "已为您创建工单" in result.response_tokens[0]

    @pytest.mark.asyncio
    async def test_ticket_node_rejects_invalid_user_id(self):
        state = AgentState(
            question="help",
            user_id="not-a-uuid",
            intent=IntentResult(label="complaint", confidence=0.9),
        )

        result = await ticket_node(state, AsyncMock())

        assert result.error == "Invalid user identity, cannot create ticket."
        assert result.response_tokens == ["Invalid user identity, cannot create ticket."]

    @pytest.mark.asyncio
    async def test_handoff_node_updates_conversation_status(self):
        conversation_id = uuid.uuid4()
        conversation_repo = AsyncMock()
        state = AgentState(
            question="Need human help",
            conversation_id=str(conversation_id),
            conversation_history=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ],
        )

        result = await handoff_node(state, conversation_repo)

        conversation_repo.update_status.assert_awaited_once()
        assert result.should_handoff is True
        assert result.response_tokens[0] == "正在为您转接人工客服，请稍候。"

    @pytest.mark.asyncio
    async def test_tool_node_uses_tool_display(self, monkeypatch):
        async def fake_execute_tool(**kwargs):
            return {"display": "订单 123456 已发货", "tool": "search_order", "raw": {"order_id": "123456"}}

        monkeypatch.setattr(tools_module, "execute_tool", fake_execute_tool)
        state = AgentState(
            question="Where is order 123456?",
            user_id=str(uuid.uuid4()),
            intent=IntentResult(label="order_query", confidence=0.95),
        )

        result = await tool_node(state)

        assert result.tool_result["tool"] == "search_order"
        assert result.response_tokens == ["订单 123456 已发货"]
