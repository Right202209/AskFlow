from __future__ import annotations

import uuid

from askflow.core.logging import get_logger
from askflow.core.metrics import TICKET_COUNT
from askflow.models.ticket import TicketPriority, TicketStatus
from askflow.repositories.ticket_repo import TicketRepo
from askflow.ticket.dedup import check_duplicate

logger = get_logger(__name__)


class TicketService:
    def __init__(self, repo: TicketRepo) -> None:
        self._repo = repo

    async def create_ticket(
        self,
        user_id: uuid.UUID,
        type: str,
        title: str,
        description: str | None = None,
        priority: str = "medium",
        conversation_id: uuid.UUID | None = None,
        content: dict | None = None,
    ):
        duplicate = await self._repo.find_duplicate(user_id, title)
        if duplicate:
            logger.info("ticket_duplicate_found", existing_id=str(duplicate.id))
            return duplicate

        ticket_priority = TicketPriority(priority)
        ticket = await self._repo.create(
            user_id=user_id,
            type=type,
            title=title,
            description=description,
            priority=ticket_priority,
            conversation_id=conversation_id,
            content=content,
        )
        TICKET_COUNT.labels(type=type, priority=priority).inc()
        logger.info("ticket_created", ticket_id=str(ticket.id))
        return ticket

    async def get_ticket(self, ticket_id: uuid.UUID):
        return await self._repo.get_by_id(ticket_id)

    async def list_user_tickets(
        self, user_id: uuid.UUID, limit: int = 20, offset: int = 0
    ):
        return await self._repo.list_by_user(user_id, limit, offset)

    async def update_status(self, ticket_id: uuid.UUID, status: str):
        ticket_status = TicketStatus(status)
        return await self._repo.update_status(ticket_id, ticket_status)

    async def get_stats(self) -> dict[str, int]:
        return await self._repo.count_by_status()
