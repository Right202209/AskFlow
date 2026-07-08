from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.conversation import Conversation, ConversationStatus
from askflow.models.message import Message


class ConversationRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, user_id: uuid.UUID, title: str | None = None) -> Conversation:
        conv = Conversation(user_id=user_id, title=title)
        self._db.add(conv)
        await self._db.flush()
        return conv

    async def get_by_id(self, conv_id: uuid.UUID) -> Conversation | None:
        return await self._db.get(Conversation, conv_id)

    async def list_by_user(
        self, user_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> list[Conversation]:
        latest_message_preview = (
            select(Message.content)
            .where(Message.conversation_id == Conversation.id)
            .order_by(Message.created_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            select(Conversation, latest_message_preview.label("last_message_preview"))
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        rows = result.all()
        conversations: list[Conversation] = []
        for conversation, last_message_preview in rows:
            conversation.last_message_preview = last_message_preview[:80] if last_message_preview else None
            conversations.append(conversation)
        return conversations

    async def touch(self, conversation: Conversation) -> Conversation:
        conversation.updated_at = datetime.now(timezone.utc)
        await self._db.flush()
        return conversation

    async def update_status(
        self, conv_id: uuid.UUID, status: ConversationStatus
    ) -> Conversation | None:
        conv = await self.get_by_id(conv_id)
        if conv:
            conv.status = status
            await self.touch(conv)
        return conv
