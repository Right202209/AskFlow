from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from askflow.models.base import Base, TimestampMixin, UUIDMixin


class HandoffStatus(str, enum.Enum):
    queued = "queued"
    claimed = "claimed"
    resolved = "resolved"
    returned = "returned"
    timed_out = "timed_out"


class HandoffSession(Base, UUIDMixin, TimestampMixin):
    """一次人工接管的活会话（plan-docs/agent-real-handoff/02）。

    与 tickets 刻意分表：handoff 是"活的认领"（claim/回流），工单是异步工作项（resolve），
    生命周期不同。每个 conversation 最多一条 open（queued/claimed）session——
    见 20260710_01 迁移的 partial unique index。
    """

    __tablename__ = "handoff_sessions"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[HandoffStatus] = mapped_column(
        Enum(HandoffStatus, name="handoff_session_status"),
        default=HandoffStatus.queued,
        nullable=False,
    )
    # 摘要失败时为空串（payload.flags 里带 summary_failed）——转接绝不因摘要失败而阻塞。
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 完整 HandoffPayload：recent_messages / intent_history / user_meta / ticket_refs / flags。
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    assignee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
