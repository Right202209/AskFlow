from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.knowledge_draft import DraftStatus, KnowledgeDraft

# 与 20260709_02_knowledge_drafts.py 的 partial unique index 完全一致；
# ON CONFLICT 必须给出同样的 WHERE 子句才能定位到这条 partial 索引。
_PENDING_DRAFT_INDEX_WHERE = sa.text("status = 'draft' AND gap_id IS NOT NULL")


class KnowledgeDraftRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        gap_id: uuid.UUID | None,
        question: str,
        answer: str,
        created_by: uuid.UUID,
        source_ticket_id: uuid.UUID | None = None,
        source_conversation_id: uuid.UUID | None = None,
        synthesis: dict | None = None,
    ) -> KnowledgeDraft:
        """ON CONFLICT DO NOTHING + 回查：两个客服同时给同一个 gap 点"草拟"收敛到一行。

        gap_id 为 NULL 的手工草稿不参与去重（partial index 只覆盖非空 gap_id）。
        """
        stmt = (
            pg_insert(KnowledgeDraft.__table__)
            .values(
                id=uuid.uuid4(),
                gap_id=gap_id,
                question=question,
                answer=answer,
                status=DraftStatus.draft.value,
                source_ticket_id=source_ticket_id,
                source_conversation_id=source_conversation_id,
                synthesis=synthesis,
                created_by=created_by,
            )
            .on_conflict_do_nothing(
                index_elements=["gap_id"],
                index_where=_PENDING_DRAFT_INDEX_WHERE,
            )
            .returning(KnowledgeDraft.__table__.c.id)
        )
        result = await self._db.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is not None:
            draft = await self.get_by_id(inserted_id)
            if draft is None:
                raise RuntimeError("draft_insert_lost_after_returning")
            return draft
        existing = await self.find_pending_by_gap(gap_id)
        if existing is not None:
            return existing
        raise RuntimeError("draft_create_conflict_unresolved")

    async def get_by_id(self, draft_id: uuid.UUID) -> KnowledgeDraft | None:
        return await self._db.get(KnowledgeDraft, draft_id)

    async def find_pending_by_gap(self, gap_id: uuid.UUID | None) -> KnowledgeDraft | None:
        if gap_id is None:
            return None
        stmt = select(KnowledgeDraft).where(
            KnowledgeDraft.gap_id == gap_id,
            KnowledgeDraft.status == DraftStatus.draft,
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_drafts(
        self,
        *,
        status: DraftStatus | None = DraftStatus.draft,
        limit: int = 20,
        offset: int = 0,
    ) -> list[KnowledgeDraft]:
        stmt = select(KnowledgeDraft)
        if status is not None:
            stmt = stmt.where(KnowledgeDraft.status == status)
        stmt = stmt.order_by(KnowledgeDraft.created_at.desc()).limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, status: DraftStatus | None = DraftStatus.draft) -> int:
        stmt = select(func.count(KnowledgeDraft.id))
        if status is not None:
            stmt = stmt.where(KnowledgeDraft.status == status)
        result = await self._db.execute(stmt)
        return result.scalar() or 0

    async def update_body(
        self,
        draft: KnowledgeDraft,
        *,
        question: str | None = None,
        answer: str | None = None,
    ) -> KnowledgeDraft:
        if question is not None:
            draft.question = question
        if answer is not None:
            draft.answer = answer
        await self._db.flush()
        return draft

    async def transition_status(
        self,
        draft_id: uuid.UUID,
        *,
        from_status: DraftStatus,
        to_status: DraftStatus,
        reviewed_by: uuid.UUID | None = None,
        review_note: str | None = None,
    ) -> KnowledgeDraft | None:
        """条件状态迁移：仅当 status 仍为 from_status 时生效；竞态输家拿到 None（上层转 409）。"""
        values: dict = {"status": to_status, "updated_at": func.now()}
        if reviewed_by is not None:
            values["reviewed_by"] = reviewed_by
        if review_note is not None:
            values["review_note"] = review_note
        stmt = (
            update(KnowledgeDraft)
            .where(KnowledgeDraft.id == draft_id, KnowledgeDraft.status == from_status)
            .values(**values)
            .returning(KnowledgeDraft.id)
        )
        result = await self._db.execute(stmt)
        if result.scalar_one_or_none() is None:
            return None
        # Core UPDATE 绕过了 identity map；populate_existing 强制刷新会话内缓存对象。
        refreshed = await self._db.execute(
            select(KnowledgeDraft)
            .where(KnowledgeDraft.id == draft_id)
            .execution_options(populate_existing=True)
        )
        return refreshed.scalar_one_or_none()
