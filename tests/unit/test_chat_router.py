from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from askflow.chat.router import (
    archive_conversation,
    delete_conversation,
    rename_conversation,
)
from askflow.core.exceptions import NotFoundError
from askflow.models.conversation import ConversationStatus
from askflow.schemas.conversation import ConversationRename


def make_conversation(user_id: uuid.UUID, **overrides):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=overrides.get("id", uuid.uuid4()),
        user_id=user_id,
        status=overrides.get("status", ConversationStatus.active),
        title=overrides.get("title", "Current title"),
        created_at=overrides.get("created_at", now),
        updated_at=overrides.get("updated_at", now),
    )


async def test_rename_conversation_updates_title(monkeypatch, mock_user, mock_db):
    conversation = make_conversation(mock_user.id, title="Updated title")
    repo = MagicMock()
    repo.get_by_id_for_user = AsyncMock(return_value=conversation)
    repo.update_title = AsyncMock(return_value=conversation)

    monkeypatch.setattr("askflow.chat.router.ConversationRepo", lambda db: repo)

    response = await rename_conversation(
        conversation.id,
        ConversationRename(title="Updated title"),
        db=mock_db,
        user=mock_user,
    )

    repo.update_title.assert_awaited_once_with(conversation.id, "Updated title")
    mock_db.commit.assert_awaited_once()
    assert response.data.title == "Updated title"


async def test_archive_conversation_sets_closed_status(monkeypatch, mock_user, mock_db):
    conversation = make_conversation(mock_user.id, status=ConversationStatus.closed)
    repo = MagicMock()
    repo.get_by_id_for_user = AsyncMock(return_value=conversation)
    repo.update_status = AsyncMock(return_value=conversation)

    monkeypatch.setattr("askflow.chat.router.ConversationRepo", lambda db: repo)

    response = await archive_conversation(
        conversation.id,
        db=mock_db,
        user=mock_user,
    )

    repo.update_status.assert_awaited_once_with(conversation.id, ConversationStatus.closed)
    mock_db.commit.assert_awaited_once()
    assert response.data.status == ConversationStatus.closed


async def test_delete_conversation_clears_session_history(monkeypatch, mock_user, mock_db):
    conversation = make_conversation(mock_user.id)
    repo = MagicMock()
    repo.get_by_id_for_user = AsyncMock(return_value=conversation)
    repo.delete = AsyncMock(return_value=True)
    clear = AsyncMock()

    monkeypatch.setattr("askflow.chat.router.ConversationRepo", lambda db: repo)
    monkeypatch.setattr("askflow.chat.router.session_store", SimpleNamespace(clear=clear))

    response = await delete_conversation(
        conversation.id,
        db=mock_db,
        user=mock_user,
    )

    repo.delete.assert_awaited_once_with(conversation.id)
    mock_db.commit.assert_awaited_once()
    clear.assert_awaited_once_with(str(conversation.id))
    assert response.data.deleted is True


async def test_delete_conversation_rejects_unknown_owner(monkeypatch, mock_user, mock_db):
    repo = MagicMock()
    repo.get_by_id_for_user = AsyncMock(return_value=None)

    monkeypatch.setattr("askflow.chat.router.ConversationRepo", lambda db: repo)

    with pytest.raises(NotFoundError):
        await delete_conversation(uuid.uuid4(), db=mock_db, user=mock_user)

    repo.delete.assert_not_awaited()
    mock_db.commit.assert_not_awaited()
