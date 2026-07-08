from __future__ import annotations

from datetime import datetime, timezone
from inspect import signature
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from askflow.chat.router import list_conversations


class _RepoFactory:
    def __init__(self, repo):
        self.repo = repo

    def __call__(self, db):
        return self.repo


@pytest.mark.asyncio
async def test_list_conversations_returns_current_users_history(mock_user):
    first = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        status="active",
        title="Second",
        last_message_preview="Second latest message",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        messages=[SimpleNamespace(content="Second latest message")],
    )
    second = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        status="active",
        title="First",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        messages=[],
    )
    repo = MagicMock()
    repo.list_by_user = AsyncMock(return_value=[first, second])
    db = AsyncMock()

    import askflow.chat.router as chat_router

    original_repo = chat_router.ConversationRepo
    chat_router.ConversationRepo = _RepoFactory(repo)
    try:
        response = await list_conversations(limit=20, offset=0, db=db, user=mock_user)
    finally:
        chat_router.ConversationRepo = original_repo

    assert response.success is True
    assert [item.id for item in response.data] == [first.id, second.id]
    assert response.data[0].title == "Second"
    assert response.data[0].last_message_preview == "Second latest message"
    assert response.data[1].title == "First"
    assert response.data[1].last_message_preview is None
    repo.list_by_user.assert_awaited_once_with(mock_user.id, limit=20, offset=0)


def test_list_conversations_constrains_pagination_query_params():
    params = signature(list_conversations).parameters

    assert params["limit"].default.gt == 0
    assert params["limit"].default.le == 100
    assert params["offset"].default.ge == 0
