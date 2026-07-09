from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.feedback import MessageFeedback


class FeedbackRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upsert(
        self,
        *,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        rating: int,
        comment: str | None = None,
    ) -> MessageFeedback:
        """同一 user 对同一 message 重复点击：覆盖 rating/comment 而非新增一行。

        DB 侧的唯一约束 uq_feedback_message_user 守住 race condition：并发两次写入只会
        留下一条记录。
        """
        stmt = (
            insert(MessageFeedback)
            .values(
                id=uuid.uuid4(),
                message_id=message_id,
                user_id=user_id,
                rating=rating,
                comment=comment,
            )
            .on_conflict_do_update(
                index_elements=["message_id", "user_id"],
                set_={"rating": rating, "comment": comment},
            )
            .returning(MessageFeedback)
        )
        result = await self._db.execute(stmt)
        row = result.scalar_one()
        await self._db.flush()
        return row

    async def get_for_user_message(
        self, *, message_id: uuid.UUID, user_id: uuid.UUID
    ) -> MessageFeedback | None:
        stmt = select(MessageFeedback).where(
            MessageFeedback.message_id == message_id,
            MessageFeedback.user_id == user_id,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
