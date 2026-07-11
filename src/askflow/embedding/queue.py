from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass

from askflow.core.logging import get_logger
from askflow.core.redis import redis_client

INDEX_QUEUE_KEY = "askflow:index:queue"
INDEX_JOB_KIND_UPLOAD = "upload"
INDEX_JOB_KIND_REINDEX = "reindex"
INDEX_JOB_KINDS = {INDEX_JOB_KIND_UPLOAD, INDEX_JOB_KIND_REINDEX}
QUEUE_POP_TIMEOUT_SECONDS = 5
STALE_INDEXING_REQUEUE_MINUTES = 30
MAX_INDEX_ATTEMPTS = 3
INITIAL_INDEX_ATTEMPT = 1

logger = get_logger(__name__)


@dataclass(frozen=True)
class IndexJob:
    doc_id: str
    kind: str
    attempt: int = INITIAL_INDEX_ATTEMPT

    def __post_init__(self) -> None:
        uuid.UUID(self.doc_id)
        if self.kind not in INDEX_JOB_KINDS:
            raise ValueError(f"Unsupported index job kind: {self.kind}")
        if self.attempt < INITIAL_INDEX_ATTEMPT:
            raise ValueError("Index job attempt must be positive")


async def enqueue_index_job(job: IndexJob) -> None:
    await redis_client.pool.lpush(INDEX_QUEUE_KEY, json.dumps(asdict(job)))


async def pop_index_job() -> IndexJob | None:
    item = await redis_client.pool.brpop(
        INDEX_QUEUE_KEY, timeout=QUEUE_POP_TIMEOUT_SECONDS
    )
    if item is None:
        return None
    try:
        return IndexJob(**json.loads(item[1]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("invalid_index_job_dropped", error=exc.__class__.__name__)
        return None
