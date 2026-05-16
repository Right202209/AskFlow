from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from askflow.agent.tools import execute_tool, search_knowledge


@pytest.mark.asyncio
async def test_search_knowledge_without_rag_service_returns_empty():
    assert await search_knowledge("hello") == []


@pytest.mark.asyncio
async def test_search_knowledge_maps_rag_sources_to_chunks():
    rag_service = AsyncMock()
    rag_service.query.return_value = SimpleNamespace(
        answer="ignored",
        sources=[
            {
                "title": "Password Reset",
                "source": "kb/account.md",
                "chunk": "Reset via the settings page.",
                "score": 0.91,
            },
            {
                "title": "",
                "source": "",
                "chunk": "Fallback chunk.",
                "score": 0.4,
            },
        ],
    )

    chunks = await search_knowledge("how to reset password", rag_service=rag_service)

    rag_service.query.assert_awaited_once_with(question="how to reset password", top_k=5)
    assert chunks == [
        {
            "title": "Password Reset",
            "source": "kb/account.md",
            "content": "Reset via the settings page.",
            "score": 0.91,
        },
        {
            "title": "",
            "source": "",
            "content": "Fallback chunk.",
            "score": 0.4,
        },
    ]


@pytest.mark.asyncio
async def test_search_knowledge_swallows_rag_errors():
    rag_service = AsyncMock()
    rag_service.query.side_effect = RuntimeError("retriever down")

    chunks = await search_knowledge("anything", rag_service=rag_service)

    assert chunks == []


@pytest.mark.asyncio
async def test_execute_tool_routes_knowledge_search_with_chunks():
    rag_service = AsyncMock()
    rag_service.query.return_value = SimpleNamespace(
        answer="x",
        sources=[
            {
                "title": "Returns Policy",
                "source": "policy/returns.md",
                "chunk": "Within 7 days.",
                "score": 0.8,
            }
        ],
    )

    result = await execute_tool(
        tool_name="knowledge_search",
        question="What is the return policy?",
        user_id="user-1",
        conversation_history=[],
        rag_service=rag_service,
    )

    assert result["tool"] == "search_knowledge"
    assert "Returns Policy" in result["display"]
    assert "Within 7 days." in result["display"]
    assert result["raw"][0]["source"] == "policy/returns.md"


@pytest.mark.asyncio
async def test_execute_tool_knowledge_search_empty_chunks_uses_fallback_copy():
    rag_service = AsyncMock()
    rag_service.query.return_value = SimpleNamespace(answer="", sources=[])

    result = await execute_tool(
        tool_name="kb_search",
        question="unknown topic",
        user_id="user-1",
        conversation_history=[],
        rag_service=rag_service,
    )

    assert result["tool"] == "search_knowledge"
    assert "暂未在知识库" in result["display"]
    assert result["raw"] == []
