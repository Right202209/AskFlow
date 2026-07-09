from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from askflow.core.exceptions import ForbiddenError
from askflow.models.ticket import TicketPriority, TicketStatus
from askflow.models.user import UserRole
from askflow.ticket.service import TicketService


def make_actor(role: UserRole, actor_id: uuid.UUID | None = None):
    return SimpleNamespace(id=actor_id or uuid.uuid4(), role=role)


class TestTicketService:
    @pytest.mark.asyncio
    async def test_create_ticket_returns_duplicate_without_creating_new_one(self):
        repo = AsyncMock()
        duplicate = SimpleNamespace(id=uuid.uuid4())
        repo.find_duplicate.return_value = duplicate
        service = TicketService(repo)

        result = await service.create_ticket(
            user_id=uuid.uuid4(),
            type="fault_report",
            title="Same title",
        )

        assert result is duplicate
        repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_ticket_converts_priority_before_saving(self):
        repo = AsyncMock()
        repo.find_duplicate.return_value = None
        created_ticket = SimpleNamespace(id=uuid.uuid4())
        repo.create.return_value = created_ticket
        service = TicketService(repo)

        result = await service.create_ticket(
            user_id=uuid.uuid4(),
            type="complaint",
            title="Need help",
            priority="high",
        )

        assert result is created_ticket
        assert repo.create.await_args.kwargs["priority"] == TicketPriority.high

    @pytest.mark.asyncio
    async def test_get_ticket_for_actor_blocks_other_users(self):
        repo = AsyncMock()
        repo.get_by_id.return_value = SimpleNamespace(user_id=uuid.uuid4())
        service = TicketService(repo)
        actor = make_actor(UserRole.user)

        result = await service.get_ticket_for_actor(uuid.uuid4(), actor)

        assert result is None

    @pytest.mark.asyncio
    async def test_update_ticket_rejects_priority_change_for_normal_user(self):
        actor_id = uuid.uuid4()
        actor = make_actor(UserRole.user, actor_id)
        repo = AsyncMock()
        repo.get_by_id.return_value = SimpleNamespace(user_id=actor_id)
        service = TicketService(repo)

        with pytest.raises(ForbiddenError):
            await service.update_ticket(
                uuid.uuid4(),
                actor,
                priority=TicketPriority.high,
                fields_set={"priority"},
            )

    @pytest.mark.asyncio
    async def test_update_ticket_allows_user_to_close_own_ticket(self):
        actor_id = uuid.uuid4()
        actor = make_actor(UserRole.user, actor_id)
        ticket = SimpleNamespace(user_id=actor_id)
        updated_ticket = SimpleNamespace(status=TicketStatus.closed)
        repo = AsyncMock()
        repo.get_by_id.return_value = ticket
        repo.update.return_value = updated_ticket
        service = TicketService(repo)

        result = await service.update_ticket(
            uuid.uuid4(),
            actor,
            status=TicketStatus.closed,
            fields_set={"status"},
        )

        assert result is updated_ticket
        repo.update.assert_awaited_once_with(
            ticket,
            status=TicketStatus.closed,
            assignee=None,
            priority=None,
            content=None,
            fields_set={"status"},
        )
