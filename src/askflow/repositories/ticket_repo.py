from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, and_, func, or_, select
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
        self,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        query: str | None = None,
    ) -> list[Ticket]:
        stmt = self._build_filtered_query(
            user_id=user_id,
            status=status,
            priority=None,
            assignee=None,
            query=query,
        )
        stmt = stmt.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_user(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        query: str | None = None,
    ) -> int:
        stmt = self._build_filtered_query(
            user_id=user_id,
            status=status,
            priority=None,
            assignee=None,
            query=query,
            count_only=True,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def list_for_staff(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        query: str | None = None,
    ) -> list[Ticket]:
        stmt = self._build_filtered_query(
            user_id=None,
            status=status,
            priority=priority,
            assignee=assignee,
            query=query,
        )
        stmt = stmt.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_for_staff(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        query: str | None = None,
    ) -> int:
        stmt = self._build_filtered_query(
            user_id=None,
            status=status,
            priority=priority,
            assignee=assignee,
            query=query,
            count_only=True,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def update_status(
        self, ticket_id: uuid.UUID, status: TicketStatus
    ) -> Ticket | None:
        ticket = await self.get_by_id(ticket_id)
        if ticket:
            ticket.status = status
            if status == TicketStatus.resolved:
                ticket.resolved_at = datetime.now(timezone.utc)
            else:
                ticket.resolved_at = None
            await self._db.flush()
        return ticket

    async def update(
        self,
        ticket: Ticket,
        *,
        status: TicketStatus | None = None,
        assignee: str | None = None,
        priority: TicketPriority | None = None,
        content: dict | None = None,
        fields_set: set[str] | None = None,
    ) -> Ticket:
        fields = fields_set or set()

        if "status" in fields and status is not None:
            ticket.status = status
            if status == TicketStatus.resolved:
                ticket.resolved_at = datetime.now(timezone.utc)
            else:
                ticket.resolved_at = None

        if "assignee" in fields:
            ticket.assignee = assignee

        if "priority" in fields and priority is not None:
            ticket.priority = priority

        if "content" in fields:
            ticket.content = content

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

    def _build_filtered_query(
        self,
        *,
        user_id: uuid.UUID | None,
        status: str | None,
        priority: str | None,
        assignee: str | None,
        query: str | None,
        count_only: bool = False,
    ):
        stmt = select(func.count()).select_from(Ticket) if count_only else select(Ticket)

        if user_id is not None:
            stmt = stmt.where(Ticket.user_id == user_id)
        if status:
            stmt = stmt.where(Ticket.status == TicketStatus(status))
        if priority:
            stmt = stmt.where(Ticket.priority == TicketPriority(priority))
        if assignee:
            stmt = stmt.where(Ticket.assignee == assignee)
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Ticket.title.ilike(pattern),
                    Ticket.description.ilike(pattern),
                    func.cast(Ticket.id, String).ilike(pattern),
                    func.cast(Ticket.conversation_id, String).ilike(pattern),
                    Ticket.assignee.ilike(pattern),
                )
            )

        return stmt
