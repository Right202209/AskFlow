from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.user import User


class UserRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id) -> User | None:
        return await self._db.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def create(self, **kwargs) -> User:
        user = User(**kwargs)
        self._db.add(user)
        await self._db.flush()
        return user
