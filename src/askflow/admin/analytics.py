from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.conversation import Conversation
from askflow.models.document import Document
from askflow.models.feedback import MessageFeedback
from askflow.models.message import Message, MessageRole
from askflow.models.ticket import Ticket
from askflow.schemas.admin import AnalyticsResponse


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
    )
