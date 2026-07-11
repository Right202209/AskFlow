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
        extra: dict | None = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            intent=intent,
            confidence=confidence,
            sources=sources,
            extra=extra,
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

    async def list_recent(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        """会话**尾部**最近 limit 条（按时间正序返回）；handoff 载荷用它拿最新上下文。"""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(reversed(result.scalars().all()))

    async def get_by_id(self, message_id: uuid.UUID) -> Message | None:
        stmt = select(Message).where(Message.id == message_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_preceding_user_message(self, message_id: uuid.UUID) -> Message | None:
        """给定一条 assistant 消息，取同会话中它之前最近的一条 user 消息。

        差评的"问题"是被打分的 assistant 消息之前的那条用户提问；gap radar 用它作为缺口文本。
        """
        target = await self.get_by_id(message_id)
        if target is None:
            return None
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == target.conversation_id,
                Message.role == MessageRole.user,
                Message.created_at <= target.created_at,
                Message.id != target.id,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
