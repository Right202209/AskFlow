from __future__ import annotations

import redis.asyncio as aioredis

from askflow.config import settings


class RedisClient:
    def __init__(self) -> None:
        self._pool: aioredis.Redis | None = None

    async def initialize(self) -> None:
        self._pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )

    @property
    def pool(self) -> aioredis.Redis:
        if self._pool is None:
            raise RuntimeError("Redis client not initialized. Call initialize() first.")
        return self._pool

    async def close(self) -> None:
        if self._pool:
            await self._pool.aclose()
            self._pool = None


redis_client = RedisClient()
