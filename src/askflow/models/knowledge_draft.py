from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from askflow.models.base import Base, TimestampMixin, UUIDMixin


class DraftStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    rejected = "rejected"


class KnowledgeDraft(Base, UUIDMixin, TimestampMixin):
    """把一个知识缺口 + 素材（工单/转人工记录/人工输入）变成待审知识条目（plan-docs/knowledge-loop/02）。

    审批通过后经现有文档管线（PG + MinIO + Chroma）发布为普通 Document；
    每个 gap 最多一条 pending 草稿（见 20260709_02 迁移的 partial unique index）。
    """

    __tablename__ = "knowledge_drafts"

    gap_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_gaps.id", ondelete="SET NULL"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus, name="draft_status"),
        default=DraftStatus.draft,
        nullable=False,
    )
    source_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True
    )
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    # LLM 辅助草拟时的元数据：{model, prompt_version, generated: bool}。
    synthesis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
