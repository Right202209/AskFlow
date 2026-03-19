from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.message import Message, MessageRole


class MessageRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        conversation_id: uuid.UUID,
        role: MessageRole,
        content: str,
        intent: str | None = None,
        confidence: float | None = None,
        sources: dict | None = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            intent=intent,
            confidence=confidence,
            sources=sources,
        )
        self._db.add(msg)
        await self._db.flush()
        return msg

    async def list_by_conversation(
        self, conversation_id: uuid.UUID, limit: int = 50
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
