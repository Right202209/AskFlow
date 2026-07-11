from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.document import Document, DocumentStatus


class DocumentRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        title: str,
        source: str | None = None,
        file_path: str | None = None,
        tags: dict | None = None,
    ) -> Document:
        doc = Document(title=title, source=source, file_path=file_path, tags=tags)
        self._db.add(doc)
        await self._db.flush()
        return doc

    async def claim_for_indexing(
        self, doc_id: uuid.UUID, *, allow_active: bool = False
    ) -> bool:
        statuses = [DocumentStatus.pending, DocumentStatus.failed]
        if allow_active:
            statuses.append(DocumentStatus.active)
        stmt = (
            update(Document)
            .where(Document.id == doc_id, Document.status.in_(statuses))
            .values(
                status=DocumentStatus.indexing,
                index_error=None,
                index_started_at=datetime.now(timezone.utc),
            )
            .returning(Document.id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_by_id(self, doc_id: uuid.UUID) -> Document | None:
        return await self._db.get(Document, doc_id)

    async def list_all(
        self, status: DocumentStatus | None = None, limit: int = 50, offset: int = 0
    ) -> list[Document]:
        stmt = select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)
        if status:
            stmt = stmt.where(Document.status == status)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        doc_id: uuid.UUID,
        status: DocumentStatus,
        chunk_count: int | None = None,
        *,
        index_error: str | None = None,
    ) -> Document | None:
        doc = await self.get_by_id(doc_id)
        if doc:
            doc.status = status
            doc.index_error = index_error
            if chunk_count is not None:
                doc.chunk_count = chunk_count
            if status == DocumentStatus.active:
                doc.indexed_at = datetime.now(timezone.utc)
            if status != DocumentStatus.indexing:
                doc.index_started_at = None
            await self._db.flush()
        return doc

    async def mark_failed(self, doc_id: uuid.UUID, error: str) -> Document | None:
        return await self.update_status(doc_id, DocumentStatus.failed, index_error=error)

    async def restore_active(
        self,
        doc_id: uuid.UUID,
        chunk_count: int,
        *,
        index_error: str | None = None,
    ) -> Document | None:
        doc = await self.get_by_id(doc_id)
        if doc:
            doc.status = DocumentStatus.active
            doc.chunk_count = chunk_count
            doc.index_error = index_error
            doc.index_started_at = None
            await self._db.flush()
        return doc

    async def list_requeue_candidates(self, stale_minutes: int) -> list[Document]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
        stmt = select(Document).where(
            (Document.status == DocumentStatus.pending)
            | (
                (Document.status == DocumentStatus.indexing)
                & (Document.index_started_at < cutoff)
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, doc_id: uuid.UUID) -> bool:
        doc = await self.get_by_id(doc_id)
        if doc:
            await self._db.delete(doc)
            await self._db.flush()
            return True
        return False
