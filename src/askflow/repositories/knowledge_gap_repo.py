from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.knowledge_gap import GapStatus, KnowledgeGap

# 与 20260709_01_knowledge_gaps.py 的 partial unique index 完全一致；
# ON CONFLICT 必须给出同样的 WHERE 子句才能定位到这条 partial 索引。
_OPEN_GAP_INDEX_WHERE = sa.text("status = 'open'")

# 允许 order 参数的白名单——避免把外部字符串直接拼进 order_by。
_ORDER_COLUMNS = {
    "frequency": KnowledgeGap.frequency,
    "updated_at": KnowledgeGap.updated_at,
    "created_at": KnowledgeGap.created_at,
}


class KnowledgeGapRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record(
        self,
        *,
        kind: str,
        question: str,
        question_norm: str,
        question_hash: str,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        intent: str | None = None,
    ) -> None:
        """按 question_hash 去重 upsert：命中 open 缺口则 frequency +1 并累加对应信号计数。

        与 tickets 的 ON CONFLICT DO NOTHING 不同，这里要 DO UPDATE——我们要的是计数递增，
        而不是空操作。并发同 hash 的多个 worker 都落到同一行，天然无 check-then-insert 竞态（D1）。
        """
        signal_bump = func.jsonb_build_object(
            kind,
            func.coalesce(sa.cast(KnowledgeGap.signals[kind].astext, sa.Integer), 0) + 1,
        )
        stmt = (
            pg_insert(KnowledgeGap.__table__)
            .values(
                id=uuid.uuid4(),
                question=question,
                question_norm=question_norm,
                question_hash=question_hash,
                status=GapStatus.open.value,
                frequency=1,
                signals={kind: 1},
                last_intent=intent,
                example_conversation_id=conversation_id,
                example_message_id=message_id,
            )
            .on_conflict_do_update(
                index_elements=["question_hash"],
                index_where=_OPEN_GAP_INDEX_WHERE,
                set_={
                    "frequency": KnowledgeGap.frequency + 1,
                    "question": question,
                    "last_intent": func.coalesce(sa.literal(intent), KnowledgeGap.last_intent),
                    "signals": KnowledgeGap.signals.op("||")(signal_bump),
                    "updated_at": func.now(),
                },
            )
        )
        await self._db.execute(stmt)

    async def list_gaps(
        self,
        *,
        status: GapStatus | None = GapStatus.open,
        order: str = "frequency",
        limit: int = 20,
        offset: int = 0,
    ) -> list[KnowledgeGap]:
        order_col = _ORDER_COLUMNS.get(order, KnowledgeGap.frequency)
        stmt = select(KnowledgeGap)
        if status is not None:
            stmt = stmt.where(KnowledgeGap.status == status)
        stmt = stmt.order_by(order_col.desc(), KnowledgeGap.updated_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, status: GapStatus | None = GapStatus.open) -> int:
        stmt = select(func.count(KnowledgeGap.id))
        if status is not None:
            stmt = stmt.where(KnowledgeGap.status == status)
        result = await self._db.execute(stmt)
        return result.scalar() or 0

    async def get_by_id(self, gap_id: uuid.UUID) -> KnowledgeGap | None:
        return await self._db.get(KnowledgeGap, gap_id)

    async def set_status(self, gap_id: uuid.UUID, status: GapStatus) -> KnowledgeGap | None:
        gap = await self.get_by_id(gap_id)
        if gap is not None:
            gap.status = status
            await self._db.flush()
        return gap

    async def list_open_by_frequency(self, *, limit: int) -> list[KnowledgeGap]:
        """相似缺口推荐的候选池：取频次最高的若干 open 缺口（read-time only）。"""
        stmt = (
            select(KnowledgeGap)
            .where(KnowledgeGap.status == GapStatus.open)
            .order_by(KnowledgeGap.frequency.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
