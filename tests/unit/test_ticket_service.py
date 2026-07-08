from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from askflow.models.user import UserRole
from askflow.ticket.service import TicketService


@pytest.mark.asyncio
async def test_list_tickets_for_regular_user_uses_user_scope(mock_user):
    repo = AsyncMock()
    repo.list_by_user = AsyncMock(return_value=[SimpleNamespace(id="t1")])
    repo.count_by_user = AsyncMock(return_value=1)
    repo.list_for_staff = AsyncMock()
    repo.count_for_staff = AsyncMock()
    service = TicketService(repo)

    tickets, total = await service.list_tickets_for_actor(
        mock_user,
        limit=20,
        offset=0,
        status="pending",
        query="login",
    )

    assert tickets == [SimpleNamespace(id="t1")]
    assert total == 1
    repo.list_by_user.assert_awaited_once_with(
        mock_user.id,
        limit=20,
        offset=0,
        status="pending",
        query="login",
    )
    repo.count_by_user.assert_awaited_once_with(
        mock_user.id,
        status="pending",
        query="login",
    )
    repo.list_for_staff.assert_not_called()
    repo.count_for_staff.assert_not_called()


@pytest.mark.asyncio
async def test_list_tickets_for_staff_uses_staff_scope(admin_user):
    repo = AsyncMock()
    repo.list_by_user = AsyncMock()
    repo.count_by_user = AsyncMock()
    repo.list_for_staff = AsyncMock(return_value=[SimpleNamespace(id="t2")])
    repo.count_for_staff = AsyncMock(return_value=4)
    service = TicketService(repo)

    tickets, total = await service.list_tickets_for_actor(
        admin_user,
        limit=10,
        offset=10,
        status="processing",
        priority="high",
        assignee="agent-01",
        query="refund",
    )

    assert tickets == [SimpleNamespace(id="t2")]
    assert total == 4
    repo.list_for_staff.assert_awaited_once_with(
        limit=10,
        offset=10,
        status="processing",
        priority="high",
        assignee="agent-01",
        query="refund",
    )
    repo.count_for_staff.assert_awaited_once_with(
        status="processing",
        priority="high",
        assignee="agent-01",
        query="refund",
    )
    repo.list_by_user.assert_not_called()
    repo.count_by_user.assert_not_called()


@pytest.mark.asyncio
async def test_list_tickets_for_agent_is_treated_as_staff(mock_user):
    mock_user.role = UserRole.agent
    repo = AsyncMock()
    repo.list_for_staff = AsyncMock(return_value=[])
    repo.count_for_staff = AsyncMock(return_value=0)
    service = TicketService(repo)

    tickets, total = await service.list_tickets_for_actor(mock_user, limit=5, offset=0)

    assert tickets == []
    assert total == 0
    repo.list_for_staff.assert_awaited_once_with(
        limit=5,
        offset=0,
        status=None,
        priority=None,
        assignee=None,
        query=None,
    )
    repo.count_for_staff.assert_awaited_once_with(
        status=None,
        priority=None,
        assignee=None,
        query=None,
    )
