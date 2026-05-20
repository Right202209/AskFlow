"""TicketRepo.create 的 ON CONFLICT 兜底路径单元测试。

对应 IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md #3：partial unique index 把工单去重提到 DB 层，
当 pg_insert.on_conflict_do_nothing 把 INSERT 让给另一并发请求时，repo.create 必须回查并返回
已有的开放工单，而不是错误地报"创建成功"或抛 IntegrityError。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from askflow.models.ticket import TicketPriority
from askflow.repositories.ticket_repo import TicketRepo


def _result_with_id(inserted_id: uuid.UUID | None):
    """伪造 SQLAlchemy execute() 的 Result——只暴露我们用到的 scalar_one_or_none()。"""
    result = SimpleNamespace()
    result.scalar_one_or_none = lambda: inserted_id
    return result


class TestTicketRepoCreateConflict:
    async def test_create_returns_inserted_ticket_when_no_conflict(self, mock_db):
        repo = TicketRepo(mock_db)
        new_ticket_id = uuid.uuid4()
        ticket = SimpleNamespace(id=new_ticket_id)
        mock_db.execute = AsyncMock(return_value=_result_with_id(new_ticket_id))
        repo.get_by_id = AsyncMock(return_value=ticket)

        result = await repo.create(
            user_id=uuid.uuid4(),
            type="fault_report",
            title="Login fails",
            priority=TicketPriority.high,
        )

        assert result is ticket
        # 正常路径：只发一次 INSERT，不调用 find_open_duplicate。
        assert mock_db.execute.await_count == 1

    async def test_create_returns_existing_ticket_on_conflict(self, mock_db):
        """ON CONFLICT 时 RETURNING 给不出 id，回查 find_open_duplicate 拿到赢家工单。"""
        repo = TicketRepo(mock_db)
        existing_id = uuid.uuid4()
        existing = SimpleNamespace(id=existing_id)
        mock_db.execute = AsyncMock(return_value=_result_with_id(None))
        repo.find_open_duplicate = AsyncMock(return_value=existing)
        repo.get_by_id = AsyncMock()

        result = await repo.create(
            user_id=uuid.uuid4(),
            type="complaint",
            title="服务态度",
        )

        assert result is existing
        repo.find_open_duplicate.assert_awaited_once()
        # 拿到 existing 后不应再 SELECT by id。
        repo.get_by_id.assert_not_awaited()

    async def test_create_retries_when_winner_closed_between_conflict_and_refetch(self, mock_db):
        """冲突回查没拿到（赢家被另一线程瞬间关掉），再 INSERT 一次必须成功。"""
        repo = TicketRepo(mock_db)
        final_id = uuid.uuid4()
        final_ticket = SimpleNamespace(id=final_id)
        # 两次 execute：第一次冲突；第二次插入成功。
        mock_db.execute = AsyncMock(
            side_effect=[
                _result_with_id(None),
                _result_with_id(final_id),
            ]
        )
        # 第一次冲突后回查未命中，进入第二次重试。
        repo.find_open_duplicate = AsyncMock(return_value=None)
        repo.get_by_id = AsyncMock(return_value=final_ticket)

        result = await repo.create(
            user_id=uuid.uuid4(),
            type="general",
            title="Edge case",
        )

        assert result is final_ticket
        assert mock_db.execute.await_count == 2
        repo.find_open_duplicate.assert_awaited_once()

    async def test_create_raises_after_two_unresolved_conflicts(self, mock_db):
        """两次都冲突且都查不到开放工单——抛 RuntimeError 而非沉默成功，提示调用方重试。"""
        repo = TicketRepo(mock_db)
        mock_db.execute = AsyncMock(
            side_effect=[
                _result_with_id(None),
                _result_with_id(None),
            ]
        )
        repo.find_open_duplicate = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="ticket_create_conflict_unresolved"):
            await repo.create(
                user_id=uuid.uuid4(),
                type="general",
                title="Never settles",
            )


class TestTicketServiceConcurrentCreate:
    """模拟应用层 find_duplicate 漏检 + 多协程同时 create——只有一份新工单胜出。"""

    async def test_service_returns_winner_when_fast_path_misses(self):
        """find_duplicate 返回 None（24h 窗口外）但 repo 走 ON CONFLICT 回查兜住去重。"""
        import asyncio

        from askflow.ticket.service import TicketService

        winner_id = uuid.uuid4()
        winner = SimpleNamespace(id=winner_id)

        # Repo 给两份 await：第一份"赢"得 INSERT，第二份冲突——但两份最终都返回同一条 winner 工单。
        repo = AsyncMock()
        repo.find_duplicate.return_value = None
        repo.create.return_value = winner

        service = TicketService(repo)

        user_id = uuid.uuid4()
        results = await asyncio.gather(
            *(
                service.create_ticket(user_id=user_id, type="fault_report", title="同一标题")
                for _ in range(5)
            )
        )

        assert {r.id for r in results} == {winner_id}
        assert repo.create.await_count == 5
