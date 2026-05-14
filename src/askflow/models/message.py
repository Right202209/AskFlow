from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from askflow.models.base import Base, TimestampMixin, UUIDMixin


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class Message(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 任意结构化元数据，目前主要承载 harness_trace（路由决策、fallback/truncate flag 等）。
    # 用 SQLAlchemy 的 `attribute_name = "extra"` 把 ORM 属性名与 DB 列名分开，避免与
    # `DeclarativeBase.metadata` 冲突。
    extra: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    conversation = relationship("Conversation", back_populates="messages")
