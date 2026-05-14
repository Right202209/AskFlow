from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.conversation import Conversation
from askflow.models.document import Document
from askflow.models.message import Message
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

    return AnalyticsResponse(
        total_conversations=row.conv or 0,
        total_messages=row.msg or 0,
        total_tickets=row.tkt or 0,
        total_documents=row.doc or 0,
        tickets_by_status=tickets_by_status,
        intent_distribution=intent_distribution,
        avg_confidence=float(row.avg_conf) if row.avg_conf is not None else 0.0,
    )
