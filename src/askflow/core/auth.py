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


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise UnauthorizedError("Missing or invalid authorization header")

    scheme, _, token = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("Missing or invalid authorization header")

    return token.strip()


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: str | None = Header(None),
) -> User:
    token = extract_bearer_token(authorization)
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
