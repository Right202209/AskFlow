from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.conversation import Conversation, ConversationStatus
from askflow.models.message import Message
from askflow.models.ticket import Ticket


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

    async def get_by_id_for_user(
        self, conv_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == user_id,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

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
        conversations: list[Conversation] = []
        for conv, preview in result.all():
            # 预览列不在 ORM 映射里，挂成实例属性让 ConversationResponse(from_attributes) 能读到。
            conv.last_message_preview = preview
            conversations.append(conv)
        return conversations

    async def update_title(self, conv_id: uuid.UUID, title: str | None) -> Conversation | None:
        conv = await self.get_by_id(conv_id)
        if conv:
            conv.title = title
            await self._db.flush()
            await self._db.refresh(conv)
        return conv

    async def update_status(
        self, conv_id: uuid.UUID, status: ConversationStatus
    ) -> Conversation | None:
        conv = await self.get_by_id(conv_id)
        if conv:
            conv.status = status
            await self._db.flush()
            await self._db.refresh(conv)
        return conv

    async def update_metadata(self, conv_id: uuid.UUID, patch: dict) -> Conversation | None:
        """merge-patch 更新 metadata JSONB：只合并给定 key，value=None 表示删除该 key。

        绝不整体覆盖——metadata 可能同时承载 pending_tool 之外的其他键。
        JSONB 列必须重新赋值新 dict，原地修改不会触发 SQLAlchemy 变更检测。
        """
        conv = await self.get_by_id(conv_id)
        if conv is None:
            return None
        merged = dict(conv.metadata_ or {})
        for key, value in patch.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        conv.metadata_ = merged
        await self._db.flush()
        return conv

    async def delete(self, conv_id: uuid.UUID) -> bool:
        conv = await self.get_by_id(conv_id)
        if conv is None:
            return False

        await self._db.execute(
            update(Ticket).where(Ticket.conversation_id == conv_id).values(conversation_id=None)
        )
        await self._db.execute(delete(Message).where(Message.conversation_id == conv_id))
        await self._db.delete(conv)
        await self._db.flush()
        return True
