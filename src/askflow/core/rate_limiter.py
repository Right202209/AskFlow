from __future__ import annotations

from askflow.config import settings
from askflow.core.exceptions import RateLimitError
from askflow.core.redis import redis_client


async def check_rate_limit(user_id: str) -> None:
    key = f"rate_limit:{user_id}"
    pool = redis_client.pool
    current = await pool.incr(key)
    if current == 1:
        await pool.expire(key, 60)
    if current > settings.rate_limit_per_minute:
        raise RateLimitError(
            f"Rate limit exceeded: {settings.rate_limit_per_minute} requests per minute"
        )
