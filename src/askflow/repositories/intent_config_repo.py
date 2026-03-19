from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.intent_config import IntentConfig


class IntentConfigRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_all_active(self) -> list[IntentConfig]:
        stmt = (
            select(IntentConfig)
            .where(IntentConfig.is_active.is_(True))
            .order_by(IntentConfig.priority.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, config_id: uuid.UUID) -> IntentConfig | None:
        return await self._db.get(IntentConfig, config_id)

    async def get_by_name(self, name: str) -> IntentConfig | None:
        stmt = select(IntentConfig).where(IntentConfig.name == name)
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def create(self, **kwargs) -> IntentConfig:
        config = IntentConfig(**kwargs)
        self._db.add(config)
        await self._db.flush()
        return config

    async def update(self, config_id: uuid.UUID, **kwargs) -> IntentConfig | None:
        config = await self.get_by_id(config_id)
        if config:
            for key, value in kwargs.items():
                setattr(config, key, value)
            await self._db.flush()
        return config

    async def delete(self, config_id: uuid.UUID) -> bool:
        config = await self.get_by_id(config_id)
        if config:
            await self._db.delete(config)
            await self._db.flush()
            return True
        return False
