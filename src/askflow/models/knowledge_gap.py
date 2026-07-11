from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from askflow.models.base import Base, TimestampMixin, UUIDMixin


class GapStatus(str, enum.Enum):
    open = "open"
    promoted = "promoted"
    dismissed = "dismissed"


class KnowledgeGap(Base, UUIDMixin, TimestampMixin):
    """机器人未能回答用户的"知识缺口"——去重聚合的未答问题（plan-docs/knowledge-loop/01）。

    open 状态的行按 question_hash 走 partial unique 去重（见 20260709_01 迁移），
    promoted/dismissed 会释放 hash，让复发的问题可以重新开一条新缺口。
    """

    __tablename__ = "knowledge_gaps"

    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_norm: Mapped[str] = mapped_column(Text, nullable=False)
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[GapStatus] = mapped_column(
        Enum(GapStatus, name="gap_status"),
        default=GapStatus.open,
        nullable=False,
    )
    frequency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 每类失败信号的计数，例如 {"clarify": 2, "negative_feedback": 1}。
    signals: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    example_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    example_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    # Slice 02 发布草稿知识条目后回填，指向进入知识库的 Document。
    promoted_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
