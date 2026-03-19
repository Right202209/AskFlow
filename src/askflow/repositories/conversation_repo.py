from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.conversation import Conversation, ConversationStatus


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
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self, conv_id: uuid.UUID, status: ConversationStatus
    ) -> Conversation | None:
        conv = await self.get_by_id(conv_id)
        if conv:
            conv.status = status
            await self._db.flush()
        return conv
