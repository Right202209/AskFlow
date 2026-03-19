from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.auth import get_current_user
from askflow.core.database import get_db
from askflow.models.user import User
from askflow.repositories.ticket_repo import TicketRepo
from askflow.schemas.common import APIResponse, PaginatedResponse
from askflow.schemas.ticket import TicketCreate, TicketResponse, TicketUpdate
from askflow.ticket.notifier import notify_ticket_update
from askflow.ticket.service import TicketService

router = APIRouter()


def _get_service(db: AsyncSession) -> TicketService:
    return TicketService(TicketRepo(db))


@router.post("", response_model=APIResponse[TicketResponse])
async def create_ticket(
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = _get_service(db)
    ticket = await service.create_ticket(
        user_id=user.id,
        type=body.type,
        title=body.title,
        description=body.description,
        priority=body.priority,
        conversation_id=body.conversation_id,
        content=body.content,
    )
    return APIResponse(data=TicketResponse.model_validate(ticket))


@router.get("/{ticket_id}", response_model=APIResponse[TicketResponse])
async def get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = _get_service(db)
    ticket = await service.get_ticket(ticket_id)
    if not ticket:
        return APIResponse(success=False, error="Ticket not found")
    return APIResponse(data=TicketResponse.model_validate(ticket))


@router.put("/{ticket_id}", response_model=APIResponse[TicketResponse])
async def update_ticket(
    ticket_id: uuid.UUID,
    body: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = _get_service(db)
    if body.status:
        ticket = await service.update_status(ticket_id, body.status)
        if ticket:
            await notify_ticket_update(
                user_id=str(ticket.user_id),
                ticket_id=str(ticket.id),
                status=body.status,
                conversation_id=str(ticket.conversation_id) if ticket.conversation_id else None,
            )
    else:
        ticket = await service.get_ticket(ticket_id)
    if not ticket:
        return APIResponse(success=False, error="Ticket not found")
    return APIResponse(data=TicketResponse.model_validate(ticket))


@router.get("", response_model=PaginatedResponse[TicketResponse])
async def list_tickets(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = _get_service(db)
    tickets = await service.list_user_tickets(user.id, limit, offset)
    return PaginatedResponse(
        data=[TicketResponse.model_validate(t) for t in tickets],
        total=len(tickets),
        page=offset // limit + 1,
        limit=limit,
    )
