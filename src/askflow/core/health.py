"""深度健康检查（Slice 04，§Design 3）。

对 Postgres/Redis/Chroma/MinIO 并发探活，每项独立超时——一个吊死的依赖不拖垮其余检查。
安全约束：结果只暴露异常类名（如 `error:ConnectionError`），绝不带异常消息，避免连接串/凭据
从 /health 泄漏（对外未鉴权）。LLM 端点不在此检查：外部、慢，且应用对其降级可用。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import text

from askflow.config import settings
from askflow.core.database import async_session_factory
from askflow.core.minio_client import minio_client
from askflow.core.redis import redis_client
from askflow.rag.vector_store import get_vector_store

HEALTH_CHECK_TIMEOUT_SECONDS = 2.0
STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"


@dataclass(frozen=True)
class HealthReport:
    status: str
    checks: dict[str, str]

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


async def _check_postgres() -> None:
    async with async_session_factory() as db:
        await db.execute(text("SELECT 1"))


async def _check_redis() -> None:
    await redis_client.pool.ping()


async def _check_chroma() -> None:
    await asyncio.to_thread(get_vector_store().heartbeat)


async def _check_minio() -> None:
    await asyncio.to_thread(minio_client.bucket_exists, settings.minio_bucket)


_CHECKS: dict[str, Callable[[], Awaitable[None]]] = {
    "postgres": _check_postgres,
    "redis": _check_redis,
    "chroma": _check_chroma,
    "minio": _check_minio,
}


async def _run_check(check: Callable[[], Awaitable[None]]) -> str:
    try:
        await asyncio.wait_for(check(), timeout=HEALTH_CHECK_TIMEOUT_SECONDS)
        return STATUS_OK
    except Exception as exc:  # noqa: BLE001 - 只报类名，绝不带消息（防连接串泄漏）
        return f"error:{exc.__class__.__name__}"


async def check_health() -> HealthReport:
    """并发跑全部依赖检查，任一失败即整体 degraded。"""
    names = list(_CHECKS)
    results = await asyncio.gather(*(_run_check(_CHECKS[name]) for name in names))
    checks = dict(zip(names, results))
    healthy = all(value == STATUS_OK for value in checks.values())
    return HealthReport(status=STATUS_OK if healthy else STATUS_DEGRADED, checks=checks)
