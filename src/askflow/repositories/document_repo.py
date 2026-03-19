from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
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
        self, doc_id: uuid.UUID, status: DocumentStatus, chunk_count: int | None = None
    ) -> Document | None:
        doc = await self.get_by_id(doc_id)
        if doc:
            doc.status = status
            if chunk_count is not None:
                doc.chunk_count = chunk_count
            if status == DocumentStatus.active:
                doc.indexed_at = datetime.now(timezone.utc)
            await self._db.flush()
        return doc

    async def delete(self, doc_id: uuid.UUID) -> bool:
        doc = await self.get_by_id(doc_id)
        if doc:
            await self._db.delete(doc)
            await self._db.flush()
            return True
        return False
