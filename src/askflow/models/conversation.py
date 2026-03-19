from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from askflow.models.base import Base, TimestampMixin, UUIDMixin


class ConversationStatus(str, enum.Enum):
    active = "active"
    closed = "closed"
    transferred = "transferred"


class Conversation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status"),
        default=ConversationStatus.active,
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation", lazy="selectin", order_by="Message.created_at"
    )
