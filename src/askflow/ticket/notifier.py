from __future__ import annotations

from askflow.chat.manager import manager
from askflow.chat.protocol import ServerMessage, ServerMessageType
from askflow.core.logging import get_logger

logger = get_logger(__name__)


async def notify_ticket_update(
    user_id: str,
    ticket_id: str,
    status: str,
    conversation_id: str | None = None,
) -> None:
    message = ServerMessage(
        type=ServerMessageType.ticket,
        conversation_id=conversation_id,
        data={
            "ticket_id": ticket_id,
            "status": status,
            "message": f"Ticket {ticket_id[:8]}... status updated to: {status}",
        },
    )
    await manager.send_to_user(user_id, message)
    logger.info(
        "ticket_notification_sent",
        user_id=user_id,
        ticket_id=ticket_id,
        status=status,
    )
