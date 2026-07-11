"""DB 化提示词模板（plan-docs/ops-platform/01）。

版本语义（D2）：`prompt_versions` 只追加、永不改写；`prompt_templates.active_version_id`
是当前生效版本的指针，"回滚"就是把指针拨回旧版本。`active_version_id` 与
`template_id` 构成 FK 环，用 `use_alter=True` 让建表阶段先落表、后补约束。
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from askflow.models.base import Base, TimestampMixin, UUIDMixin


class PromptTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "prompt_templates"

    # 稳定业务键，如 "rag.system" / "intent.classifier"——代码按 key 取用。
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 声明的占位符清单（如 ["chunks", "question"]），写入前用于渲染校验。
    variables: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_versions.id", use_alter=True, ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PromptVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uniq_prompt_version"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
