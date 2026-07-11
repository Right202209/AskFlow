"""系统级健康聚合（Slice 04，§Design 4）。

面向 admin "System" 面板：依赖探活（复用 core/health）+ 文档积压 + 索引新鲜度 +
24h 审计事件 + 版本。所有 DB 派生数字每请求实时算，不进 Prometheus gauge——因此在
`--workers N` 下也返回一致、与具体 worker 无关的结果。质量指标仍留在 get_analytics，
本模块只补"系统状态"，不重复"质量状态"。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.agent.harness import CognitiveHarnessPolicy
from askflow.core.health import check_health
from askflow.models.audit_log import AuditLog
from askflow.models.document import Document, DocumentStatus
from askflow.schemas.admin import SystemHealthResponse
from askflow.version import APP_VERSION

AUDIT_WINDOW_HOURS = 24
SECONDS_PER_HOUR = 3600.0


async def _document_stats(db: AsyncSession) -> tuple[dict[str, int], datetime | None]:
    """按状态计数（全状态 0 兜底）+ 最老 pending 的创建时刻（索引积压信号）。"""
    rows = (
        await db.execute(select(Document.status, func.count()).group_by(Document.status))
    ).all()
    by_status = {s.value: 0 for s in DocumentStatus}
    for status, count in rows:
        by_status[status.value] = count
    oldest_pending = (
        await db.execute(
            select(func.min(Document.created_at)).where(
                Document.status == DocumentStatus.pending
            )
        )
    ).scalar()
    return by_status, oldest_pending


async def _index_freshness(db: AsyncSession) -> tuple[int, datetime | None]:
    """active 文档的分块总数与最近一次 indexed_at——反映索引规模与新鲜度。"""
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Document.chunk_count), 0),
                func.max(Document.indexed_at),
            ).where(Document.status == DocumentStatus.active)
        )
    ).one()
    return int(row[0] or 0), row[1]


async def _audit_events_24h(db: AsyncSession) -> dict[str, int]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=AUDIT_WINDOW_HOURS)
    rows = (
        await db.execute(
            select(AuditLog.action, func.count())
            .where(AuditLog.created_at >= cutoff)
            .group_by(AuditLog.action)
        )
    ).all()
    return {action: count for action, count in rows}


def _age_hours(moment: datetime | None) -> float | None:
    if moment is None:
        return None
    return (datetime.now(tz=timezone.utc) - moment).total_seconds() / SECONDS_PER_HOUR


async def get_system_health(db: AsyncSession) -> SystemHealthResponse:
    documents_by_status, oldest_pending = await _document_stats(db)
    chunks_total, last_indexed_at = await _index_freshness(db)
    audit_events = await _audit_events_24h(db)
    report = await check_health()
    return SystemHealthResponse(
        status=report.status,
        checks=report.checks,
        documents_by_status=documents_by_status,
        oldest_pending_age_hours=_age_hours(oldest_pending),
        chunks_total=chunks_total,
        last_indexed_at=last_indexed_at,
        audit_events_24h=audit_events,
        harness_policy_version=CognitiveHarnessPolicy().version,
        app_version=APP_VERSION,
    )
