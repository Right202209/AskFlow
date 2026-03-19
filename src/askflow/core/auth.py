from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.database import get_db
from askflow.core.exceptions import ForbiddenError, UnauthorizedError
from askflow.core.security import decode_access_token
from askflow.models.user import User, UserRole
from askflow.repositories.user_repo import UserRepo


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: str | None = Header(None),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid authorization header")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        raise UnauthorizedError("Invalid token")
    repo = UserRepo(db)
    user = await repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


def require_role(*roles: UserRole):
    async def _check(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if user.role not in roles:
            raise ForbiddenError(f"Required role: {', '.join(r.value for r in roles)}")
        return user
    return _check
