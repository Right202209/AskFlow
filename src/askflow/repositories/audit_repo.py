"""审计日志仓储（plan-docs/ops-platform/02）。

不可变：只暴露 create / list / count，无 update / delete。
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.audit_log import AuditLog


class AuditRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _filtered(
        self,
        *,
        entity_type: str | None,
        actor_id: uuid.UUID | None,
        action: str | None,
    ):
        stmt = select(AuditLog)
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if actor_id:
            stmt = stmt.where(AuditLog.actor_id == actor_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        return stmt

    async def list_filtered(
        self,
        *,
        entity_type: str | None = None,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        limit: int,
        offset: int = 0,
    ) -> list[AuditLog]:
        stmt = (
            self._filtered(entity_type=entity_type, actor_id=actor_id, action=action)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        entity_type: str | None = None,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
    ) -> int:
        inner = self._filtered(
            entity_type=entity_type, actor_id=actor_id, action=action
        ).subquery()
        result = await self._db.execute(select(func.count()).select_from(inner))
        return int(result.scalar_one())
