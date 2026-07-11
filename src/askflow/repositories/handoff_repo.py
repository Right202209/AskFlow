from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.handoff import HandoffSession, HandoffStatus

# 与 20260710_01_handoff_session.py 的 partial unique index 完全一致。
_OPEN_HANDOFF_INDEX_WHERE = sa.text("status IN ('queued', 'claimed')")

_OPEN_STATUSES = (HandoffStatus.queued, HandoffStatus.claimed)


class HandoffRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        conversation_id: uuid.UUID,
        summary: str,
        payload: dict,
    ) -> HandoffSession:
        """ON CONFLICT DO NOTHING + 回查：同会话重复转接收敛到已有 open session。"""
        stmt = (
            pg_insert(HandoffSession.__table__)
            .values(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                status=HandoffStatus.queued.value,
                summary=summary,
                payload=payload,
            )
            .on_conflict_do_nothing(
                index_elements=["conversation_id"],
                index_where=_OPEN_HANDOFF_INDEX_WHERE,
            )
            .returning(HandoffSession.__table__.c.id)
        )
        result = await self._db.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is not None:
            session = await self.get_by_id(inserted_id)
            if session is None:
                raise RuntimeError("handoff_insert_lost_after_returning")
            return session
        existing = await self.find_open_by_conversation(conversation_id)
        if existing is not None:
            return existing
        raise RuntimeError("handoff_create_conflict_unresolved")

    async def get_by_id(self, session_id: uuid.UUID) -> HandoffSession | None:
        return await self._db.get(HandoffSession, session_id)

    async def find_open_by_conversation(
        self, conversation_id: uuid.UUID
    ) -> HandoffSession | None:
        stmt = select(HandoffSession).where(
            HandoffSession.conversation_id == conversation_id,
            HandoffSession.status.in_(_OPEN_STATUSES),
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_sessions(
        self,
        *,
        status: HandoffStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[HandoffSession]:
        stmt = select(HandoffSession)
        if status is not None:
            stmt = stmt.where(HandoffSession.status == status)
        stmt = stmt.order_by(HandoffSession.created_at.desc()).limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, status: HandoffStatus | None = None) -> int:
        stmt = select(func.count(HandoffSession.id))
        if status is not None:
            stmt = stmt.where(HandoffSession.status == status)
        result = await self._db.execute(stmt)
        return result.scalar() or 0

    async def claim(self, session_id: uuid.UUID, assignee: str) -> HandoffSession | None:
        """原子认领：仅 queued 可认领；0 行更新 = 竞态输家（上层转 409）。"""
        stmt = (
            update(HandoffSession)
            .where(HandoffSession.id == session_id, HandoffSession.status == HandoffStatus.queued)
            .values(
                status=HandoffStatus.claimed,
                assignee=assignee,
                claimed_at=func.now(),
                updated_at=func.now(),
            )
            .returning(HandoffSession.id)
        )
        result = await self._db.execute(stmt)
        if result.scalar_one_or_none() is None:
            return None
        return await self._refresh(session_id)

    async def close(
        self,
        session_id: uuid.UUID,
        *,
        from_status: HandoffStatus,
        to_status: HandoffStatus,
    ) -> HandoffSession | None:
        """条件关闭（claimed → resolved/returned，queued → timed_out）；输家拿 None。"""
        stmt = (
            update(HandoffSession)
            .where(HandoffSession.id == session_id, HandoffSession.status == from_status)
            .values(status=to_status, closed_at=func.now(), updated_at=func.now())
            .returning(HandoffSession.id)
        )
        result = await self._db.execute(stmt)
        if result.scalar_one_or_none() is None:
            return None
        return await self._refresh(session_id)

    async def sweep_expired(self, timeout_minutes: int) -> list[HandoffSession]:
        """锁定超时未认领的 queued 行；FOR UPDATE SKIP LOCKED 让多 worker 清扫互不重复（D9）。"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        stmt = (
            select(HandoffSession)
            .where(
                HandoffSession.status == HandoffStatus.queued,
                HandoffSession.created_at < cutoff,
            )
            .with_for_update(skip_locked=True)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def _refresh(self, session_id: uuid.UUID) -> HandoffSession | None:
        # Core UPDATE 绕过 identity map；populate_existing 强制刷新会话内缓存对象。
        refreshed = await self._db.execute(
            select(HandoffSession)
            .where(HandoffSession.id == session_id)
            .execution_options(populate_existing=True)
        )
        return refreshed.scalar_one_or_none()
