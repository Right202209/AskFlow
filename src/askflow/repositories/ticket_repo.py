from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.models.ticket import Ticket, TicketPriority, TicketStatus


class TicketRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        user_id: uuid.UUID,
        type: str,
        title: str,
        description: str | None = None,
        priority: TicketPriority = TicketPriority.medium,
        conversation_id: uuid.UUID | None = None,
        content: dict | None = None,
    ) -> Ticket:
        ticket = Ticket(
            user_id=user_id,
            type=type,
            title=title,
            description=description,
            priority=priority,
            conversation_id=conversation_id,
            content=content,
        )
        self._db.add(ticket)
        await self._db.flush()
        return ticket

    async def get_by_id(self, ticket_id: uuid.UUID) -> Ticket | None:
        return await self._db.get(Ticket, ticket_id)

    async def list_by_user(
        self, user_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> list[Ticket]:
        stmt = (
            select(Ticket)
            .where(Ticket.user_id == user_id)
            .order_by(Ticket.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self, ticket_id: uuid.UUID, status: TicketStatus
    ) -> Ticket | None:
        ticket = await self.get_by_id(ticket_id)
        if ticket:
            ticket.status = status
            if status == TicketStatus.resolved:
                ticket.resolved_at = datetime.now(timezone.utc)
            await self._db.flush()
        return ticket

    async def find_duplicate(
        self, user_id: uuid.UUID, title: str, hours: int = 24
    ) -> Ticket | None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = select(Ticket).where(
            and_(
                Ticket.user_id == user_id,
                Ticket.title == title,
                Ticket.created_at >= cutoff,
                Ticket.status.in_([TicketStatus.pending, TicketStatus.processing]),
            )
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(Ticket.status, func.count()).group_by(Ticket.status)
        result = await self._db.execute(stmt)
        return {row[0].value: row[1] for row in result.all()}
