from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.conversation import Conversation
from askflow.models.document import Document
from askflow.models.message import Message
from askflow.models.ticket import Ticket
from askflow.schemas.admin import AnalyticsResponse


async def get_analytics(db: AsyncSession) -> AnalyticsResponse:
    conv_count = (await db.execute(select(func.count(Conversation.id)))).scalar() or 0
    msg_count = (await db.execute(select(func.count(Message.id)))).scalar() or 0
    ticket_count = (await db.execute(select(func.count(Ticket.id)))).scalar() or 0
    doc_count = (await db.execute(select(func.count(Document.id)))).scalar() or 0

    ticket_status_rows = (
        await db.execute(select(Ticket.status, func.count()).group_by(Ticket.status))
    ).all()
    tickets_by_status = {str(row[0].value): row[1] for row in ticket_status_rows}

    intent_rows = (
        await db.execute(
            select(Message.intent, func.count())
            .where(Message.intent.isnot(None))
            .group_by(Message.intent)
        )
    ).all()
    intent_distribution = {row[0]: row[1] for row in intent_rows}

    avg_conf_result = (
        await db.execute(
            select(func.avg(Message.confidence)).where(Message.confidence.isnot(None))
        )
    ).scalar()
    avg_confidence = float(avg_conf_result) if avg_conf_result else 0.0

    return AnalyticsResponse(
        total_conversations=conv_count,
        total_messages=msg_count,
        total_tickets=ticket_count,
        total_documents=doc_count,
        tickets_by_status=tickets_by_status,
        intent_distribution=intent_distribution,
        avg_confidence=avg_confidence,
    )
