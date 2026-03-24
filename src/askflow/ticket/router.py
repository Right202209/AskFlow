from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.auth import get_current_user
from askflow.core.database import get_db
from askflow.core.exceptions import NotFoundError
from askflow.models.user import User
from askflow.repositories.conversation_repo import ConversationRepo
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
    if body.conversation_id is not None:
        conv_repo = ConversationRepo(db)
        conversation = await conv_repo.get_by_id(body.conversation_id)
        if conversation is None or conversation.user_id != user.id:
            raise NotFoundError("Conversation not found")

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
    ticket = await service.get_ticket_for_actor(ticket_id, user)
    if not ticket:
        raise NotFoundError("Ticket not found")
    return APIResponse(data=TicketResponse.model_validate(ticket))


@router.put("/{ticket_id}", response_model=APIResponse[TicketResponse])
async def update_ticket(
    ticket_id: uuid.UUID,
    body: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = _get_service(db)
    current_ticket = await service.get_ticket_for_actor(ticket_id, user)
    if not current_ticket:
        raise NotFoundError("Ticket not found")

    previous_status = current_ticket.status
    updates = body.model_dump(exclude_unset=True)
    ticket = await service.update_ticket(
        ticket_id,
        user,
        status=updates.get("status"),
        assignee=updates.get("assignee"),
        priority=updates.get("priority"),
        content=updates.get("content"),
        fields_set=set(updates.keys()),
    )
    if not ticket:
        raise NotFoundError("Ticket not found")
    if "status" in updates and ticket.status != previous_status:
        await notify_ticket_update(
            user_id=str(ticket.user_id),
            ticket_id=str(ticket.id),
            status=ticket.status.value,
            conversation_id=str(ticket.conversation_id) if ticket.conversation_id else None,
        )
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
    total = await service.count_user_tickets(user.id)
    return PaginatedResponse(
        data=[TicketResponse.model_validate(t) for t in tickets],
        total=total,
        page=offset // limit + 1,
        limit=limit,
    )
