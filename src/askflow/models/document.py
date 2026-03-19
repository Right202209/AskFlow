from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from askflow.models.base import Base, TimestampMixin, UUIDMixin


class DocumentStatus(str, enum.Enum):
    indexing = "indexing"
    active = "active"
    archived = "archived"


class Document(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"),
        default=DocumentStatus.indexing,
        nullable=False,
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
