from __future__ import annotations

import enum

from sqlalchemy import String, Enum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from askflow.models.base import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    user = "user"
    agent = "agent"
    admin = "admin"


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.user, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    conversations = relationship("Conversation", back_populates="user", lazy="selectin")
