from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from askflow.repositories.conversation_repo import ConversationRepo


async def test_delete_conversation_removes_messages_and_detaches_tickets(mock_db):
    conversation_id = uuid.uuid4()
    repo = ConversationRepo(mock_db)
    repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=conversation_id))

    deleted = await repo.delete(conversation_id)

    assert deleted is True
    assert mock_db.execute.await_count == 2
    mock_db.delete.assert_awaited_once()
    mock_db.flush.assert_awaited_once()


async def test_delete_conversation_returns_false_when_missing(mock_db):
    repo = ConversationRepo(mock_db)
    repo.get_by_id = AsyncMock(return_value=None)

    deleted = await repo.delete(uuid.uuid4())

    assert deleted is False
    mock_db.execute.assert_not_awaited()
    mock_db.delete.assert_not_awaited()
