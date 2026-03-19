from __future__ import annotations

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from askflow.models.base import Base, TimestampMixin, UUIDMixin


class IntentConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "intent_configs"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_target: Mapped[str] = mapped_column(String(100), nullable=False)
    keywords: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    examples: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(default=0, nullable=False)
