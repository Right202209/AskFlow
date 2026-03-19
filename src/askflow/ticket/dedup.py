from __future__ import annotations

import uuid

from askflow.core.logging import get_logger
from askflow.repositories.ticket_repo import TicketRepo

logger = get_logger(__name__)


async def check_duplicate(repo: TicketRepo, user_id: uuid.UUID, title: str) -> bool:
    existing = await repo.find_duplicate(user_id, title)
    if existing:
        logger.info("duplicate_ticket_detected", existing_id=str(existing.id), title=title)
        return True
    return False
