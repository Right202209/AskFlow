from __future__ import annotations

import json
from collections import defaultdict

from askflow.core.logging import get_logger
from askflow.core.redis import redis_client

logger = get_logger(__name__)

MAX_HISTORY = 20


class SessionStore:
    async def get_history(self, conversation_id: str) -> list[dict[str, str]]:
        pool = redis_client.pool
        key = f"chat:history:{conversation_id}"
        raw = await pool.lrange(key, 0, MAX_HISTORY - 1)
        return [json.loads(item) for item in raw]

    async def add_message(
        self, conversation_id: str, role: str, content: str
    ) -> None:
        pool = redis_client.pool
        key = f"chat:history:{conversation_id}"
        await pool.rpush(key, json.dumps({"role": role, "content": content}))
        await pool.ltrim(key, -MAX_HISTORY, -1)
        await pool.expire(key, 86400)

    async def clear(self, conversation_id: str) -> None:
        pool = redis_client.pool
        await pool.delete(f"chat:history:{conversation_id}")


session_store = SessionStore()
