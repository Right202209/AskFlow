from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.config import settings
from askflow.models.conversation import Conversation
from askflow.models.document import Document
from askflow.models.feedback import MessageFeedback
from askflow.models.message import Message, MessageRole
from askflow.models.ticket import Ticket, TicketStatus
from askflow.schemas.admin import (
    AnalyticsResponse,
    TicketDashboardResponse,
    TicketTrendPoint,
)


async def get_analytics(db: AsyncSession) -> AnalyticsResponse:
    # 将 4 个 count 与平均置信度合并为一次 round-trip，减少 admin 面板的 DB 延迟。
    aggregates_stmt = select(
        select(func.count(Conversation.id)).scalar_subquery().label("conv"),
        select(func.count(Message.id)).scalar_subquery().label("msg"),
        select(func.count(Ticket.id)).scalar_subquery().label("tkt"),
        select(func.count(Document.id)).scalar_subquery().label("doc"),
        select(func.avg(Message.confidence))
        .where(Message.confidence.isnot(None))
        .scalar_subquery()
        .label("avg_conf"),
    )
    row = (await db.execute(aggregates_stmt)).one()

    ticket_status_rows = (
        await db.execute(select(Ticket.status, func.count()).group_by(Ticket.status))
    ).all()
    tickets_by_status = {str(r[0].value): r[1] for r in ticket_status_rows}

    intent_rows = (
        await db.execute(
            select(Message.intent, func.count())
            .where(Message.intent.isnot(None))
            .group_by(Message.intent)
        )
    ).all()
    intent_distribution = {r[0]: r[1] for r in intent_rows}

    # harness_fallback_rate / harness_truncate_rate：替代空洞的 avg_confidence，让运营能直接看
    # "harness 多频繁救场"。harness_trace 落在 messages.metadata JSONB 里。
    fallback_expr = func.coalesce(
        Message.extra["harness_trace"]["fallback_reason"].astext, literal_column("''")
    )
    truncate_expr = func.coalesce(
        Message.extra["harness_trace"]["truncate_flag"].astext, literal_column("''")
    )
    harness_stmt = select(
        func.count(Message.id).label("total"),
        func.sum(case((fallback_expr != "", 1), else_=0)).label("fallback_hits"),
        func.sum(case((truncate_expr.in_(["true", "True"]), 1), else_=0)).label("truncate_hits"),
    ).where(Message.role == MessageRole.assistant)
    harness_row = (await db.execute(harness_stmt)).one()
    total_assistant = harness_row.total or 0
    fallback_rate = float(harness_row.fallback_hits) / total_assistant if total_assistant else 0.0
    truncate_rate = float(harness_row.truncate_hits) / total_assistant if total_assistant else 0.0

    # 拦截分类型聚合：reason 是单值列，可以直接 GROUP BY；flags 是 JSONB 数组，
    # 通过 jsonb_array_elements_text 展平后再聚合。两者结合让运营能定位"今天哪类拦截在涨"。
    reason_expr = Message.extra["harness_trace"]["reason"].astext
    reason_rows = (
        await db.execute(
            select(reason_expr.label("reason"), func.count())
            .where(Message.role == MessageRole.assistant, reason_expr.isnot(None))
            .group_by(reason_expr)
        )
    ).all()
    reason_distribution = {row[0]: row[1] for row in reason_rows if row[0]}

    flag_col = func.jsonb_array_elements_text(
        Message.extra["harness_trace"]["flags"]
    ).column_valued("flag")
    flag_rows = (
        await db.execute(
            select(flag_col, func.count())
            .where(Message.role == MessageRole.assistant)
            .group_by(flag_col)
        )
    ).all()
    flag_distribution = {row[0]: row[1] for row in flag_rows if row[0]}

    # thumbs_down_rate_7d：用真实用户反馈替代 avg_confidence 作为唯一可信质量信号。
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
    feedback_stmt = select(
        func.count(MessageFeedback.id).label("total"),
        func.sum(case((MessageFeedback.rating == -1, 1), else_=0)).label("downs"),
    ).where(MessageFeedback.created_at >= cutoff)
    feedback_row = (await db.execute(feedback_stmt)).one()
    total_feedback_7d = feedback_row.total or 0
    thumbs_down_rate_7d = (
        float(feedback_row.downs) / total_feedback_7d if total_feedback_7d else 0.0
    )

    return AnalyticsResponse(
        total_conversations=row.conv or 0,
        total_messages=row.msg or 0,
        total_tickets=row.tkt or 0,
        total_documents=row.doc or 0,
        tickets_by_status=tickets_by_status,
        intent_distribution=intent_distribution,
        avg_confidence=float(row.avg_conf) if row.avg_conf is not None else 0.0,
        harness_fallback_rate=fallback_rate,
        harness_truncate_rate=truncate_rate,
        thumbs_down_rate_7d=thumbs_down_rate_7d,
        feedback_total_7d=total_feedback_7d,
        harness_reason_distribution=reason_distribution,
        harness_flag_distribution=flag_distribution,
    )


async def get_ticket_dashboard(db: AsyncSession) -> TicketDashboardResponse:
    """工单系统级看板:status/优先级分布、SLA 超时、7 天进出趋势。

    分四次查询合并到 Python 端:
    - status 聚合 → 全局占比
    - open(pending+processing)按优先级 → 定位"高优是不是堆积"
    - SLA 超时计数 + 最老 open 工单年龄 → 排队压力告警
    - 最近 7 天 created/resolved 按日 → 给前端折线对比

    没有把 SLA 阈值做成每条工单各异的复杂规则,因为当前 PRD 还没区分优先级 SLA;
    设一个 settings.ticket_sla_hours 全局阈值是当前最小可用的实现。
    """
    now = datetime.now(tz=timezone.utc)
    sla_hours = settings.ticket_sla_hours
    sla_cutoff = now - timedelta(hours=sla_hours)
    trend_cutoff = now - timedelta(days=7)

    # 状态聚合:四种状态都给个 0 兜底,前端可直接 .pending / .processing 取数。
    status_rows = (
        await db.execute(select(Ticket.status, func.count()).group_by(Ticket.status))
    ).all()
    status_counts: dict[str, int] = {s.value: 0 for s in TicketStatus}
    for status, count in status_rows:
        status_counts[status.value] = count
    pending = status_counts[TicketStatus.pending.value]
    processing = status_counts[TicketStatus.processing.value]
    resolved = status_counts[TicketStatus.resolved.value]
    closed = status_counts[TicketStatus.closed.value]
    open_total = pending + processing

    # open 工单按优先级 → 让前端"high/urgent 堆积"看板能直接渲染。
    open_filter = Ticket.status.in_([TicketStatus.pending, TicketStatus.processing])
    priority_rows = (
        await db.execute(
            select(Ticket.priority, func.count()).where(open_filter).group_by(Ticket.priority)
        )
    ).all()
    open_by_priority = {p.value: c for p, c in priority_rows}

    # SLA 超时:open + created_at < cutoff;同时取最老 open 工单的 created_at,
    # 一次往返够用。MIN(created_at) NULL 时说明当前完全没有 open 工单。
    sla_row = (
        await db.execute(
            select(
                func.count(Ticket.id).label("breach"),
                func.min(Ticket.created_at).label("oldest"),
            ).where(open_filter, Ticket.created_at < sla_cutoff)
        )
    ).one()
    breach_total = sla_row.breach or 0

    oldest_open_row = (
        await db.execute(select(func.min(Ticket.created_at)).where(open_filter))
    ).scalar()
    if oldest_open_row is not None:
        # SQLAlchemy 取出来已是 timezone-aware(列定义 DateTime(timezone=True));
        # 减法直接得 timedelta,转小时,前端可读。
        oldest_age_hours: float | None = (now - oldest_open_row).total_seconds() / 3600.0
    else:
        oldest_age_hours = None

    # 7 天进出量:created 走 created_at,resolved 走 resolved_at;
    # date_trunc('day') 让结果按天分桶,Python 侧再拼成稀疏 → 密集序列。
    day_expr_created = func.date_trunc("day", Ticket.created_at)
    created_rows = (
        await db.execute(
            select(day_expr_created.label("day"), func.count())
            .where(Ticket.created_at >= trend_cutoff)
            .group_by(day_expr_created)
        )
    ).all()
    day_expr_resolved = func.date_trunc("day", Ticket.resolved_at)
    resolved_rows = (
        await db.execute(
            select(day_expr_resolved.label("day"), func.count())
            .where(Ticket.resolved_at.isnot(None), Ticket.resolved_at >= trend_cutoff)
            .group_by(day_expr_resolved)
        )
    ).all()
    created_by_day = {_day_key(row[0]): row[1] for row in created_rows}
    resolved_by_day = {_day_key(row[0]): row[1] for row in resolved_rows}

    # 用今天往回数 7 天,保证前端折线 X 轴是连续日期(空白日期补 0)。
    trend: list[TicketTrendPoint] = []
    today = now.date()
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        trend.append(
            TicketTrendPoint(
                date=key,
                created=created_by_day.get(key, 0),
                resolved=resolved_by_day.get(key, 0),
            )
        )

    return TicketDashboardResponse(
        open_total=open_total,
        pending_total=pending,
        processing_total=processing,
        resolved_total=resolved,
        closed_total=closed,
        sla_breach_total=breach_total,
        sla_hours=sla_hours,
        open_by_priority=open_by_priority,
        oldest_open_age_hours=oldest_age_hours,
        daily_trend=trend,
    )


def _day_key(value) -> str:
    """把 date_trunc('day', ...) 的返回值规整成 YYYY-MM-DD 字符串。"""
    if value is None:
        return ""
    if hasattr(value, "date"):
        return value.date().isoformat()
    return str(value)[:10]
