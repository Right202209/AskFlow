"""提示词模板仓储（ops-platform/01）。

版本号分配用 max+1 + UNIQUE(template_id, version) 兜底：两个管理员并发编辑时，
输家撞唯一约束 → 上层转 409。激活指针只做 UPDATE，不产生新版本行。
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.exceptions import ConflictError
from askflow.models.prompt import PromptTemplate, PromptVersion


class PromptRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def load_active_contents(self) -> dict[str, str]:
        """key → 当前生效内容；缓存 loader 用的一次性全量查询。"""
        stmt = (
            select(PromptTemplate.key, PromptVersion.content)
            .join(PromptVersion, PromptTemplate.active_version_id == PromptVersion.id)
            .where(PromptTemplate.is_active.is_(True))
        )
        rows = await self._db.execute(stmt)
        return {key: content for key, content in rows.all()}

    async def list_with_active_version(
        self,
    ) -> list[tuple[PromptTemplate, PromptVersion | None]]:
        stmt = (
            select(PromptTemplate, PromptVersion)
            .outerjoin(PromptVersion, PromptTemplate.active_version_id == PromptVersion.id)
            .order_by(PromptTemplate.key)
        )
        rows = await self._db.execute(stmt)
        return [(template, version) for template, version in rows.all()]

    async def get_by_key(self, key: str) -> PromptTemplate | None:
        result = await self._db.execute(
            select(PromptTemplate).where(PromptTemplate.key == key)
        )
        return result.scalar_one_or_none()

    async def get_active_version(self, template: PromptTemplate) -> PromptVersion | None:
        if template.active_version_id is None:
            return None
        result = await self._db.execute(
            select(PromptVersion).where(PromptVersion.id == template.active_version_id)
        )
        return result.scalar_one_or_none()

    async def get_version(
        self, template_id: uuid.UUID, version: int
    ) -> PromptVersion | None:
        result = await self._db.execute(
            select(PromptVersion).where(
                PromptVersion.template_id == template_id,
                PromptVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def list_versions(
        self, template_id: uuid.UUID, *, limit: int, offset: int = 0
    ) -> list[PromptVersion]:
        stmt = (
            select(PromptVersion)
            .where(PromptVersion.template_id == template_id)
            .order_by(PromptVersion.version.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_versions(self, template_id: uuid.UUID) -> int:
        result = await self._db.execute(
            select(func.count())
            .select_from(PromptVersion)
            .where(PromptVersion.template_id == template_id)
        )
        return int(result.scalar_one())

    async def append_version(
        self,
        template_id: uuid.UUID,
        *,
        content: str,
        created_by: uuid.UUID | None,
        comment: str | None,
    ) -> PromptVersion:
        """追加下一个版本；并发编辑撞 UNIQUE(template_id, version) → 409。"""
        next_version = await self._next_version(template_id)
        row = PromptVersion(
            template_id=template_id,
            version=next_version,
            content=content,
            created_by=created_by,
            comment=comment,
        )
        self._db.add(row)
        try:
            await self._db.flush()
        except IntegrityError as exc:
            raise ConflictError("Concurrent prompt edit detected, please retry") from exc
        return row

    async def activate_version(
        self, template_id: uuid.UUID, version_id: uuid.UUID
    ) -> None:
        await self._db.execute(
            update(PromptTemplate)
            .where(PromptTemplate.id == template_id)
            .values(active_version_id=version_id)
        )

    async def _next_version(self, template_id: uuid.UUID) -> int:
        result = await self._db.execute(
            select(func.max(PromptVersion.version)).where(
                PromptVersion.template_id == template_id
            )
        )
        current_max = result.scalar_one_or_none()
        return (current_max or 0) + 1
