from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy import String, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.logging import get_logger
from askflow.models.ticket import Ticket, TicketPriority, TicketStatus

logger = get_logger(__name__)


# 与 alembic/versions/20260519_01_ticket_open_unique.py 里 partial unique index 完全一致；
# PostgreSQL 的 ON CONFLICT 必须给出同样的 WHERE 子句才能定位到这条 partial 索引。
_OPEN_TICKET_INDEX_WHERE = sa.text("status NOT IN ('closed', 'resolved')")


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
        """通过 INSERT ON CONFLICT DO NOTHING 让 DB 兜底并发去重——冲突时回查已有开放工单。

        正常路径只走一次 INSERT。极端情况下，赢家工单在我们 ON CONFLICT 与 find_open_duplicate
        之间又被关闭，会进入第二次重试——这时分区索引已经空出位置，正常插入成功。
        """
        for attempt in range(2):
            stmt = (
                pg_insert(Ticket.__table__)
                .values(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    type=type,
                    title=title,
                    description=description,
                    status=TicketStatus.pending.value,
                    priority=priority.value,
                    conversation_id=conversation_id,
                    content=content,
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "title"],
                    index_where=_OPEN_TICKET_INDEX_WHERE,
                )
                .returning(Ticket.__table__.c.id)
            )
            result = await self._db.execute(stmt)
            inserted_id = result.scalar_one_or_none()
            if inserted_id is not None:
                ticket = await self.get_by_id(inserted_id)
                if ticket is None:
                    # RETURNING 给了 id 但 get_by_id 读不到——只在事务被外部 rollback 时出现。
                    raise RuntimeError("ticket_insert_lost_after_returning")
                return ticket
            existing = await self.find_open_duplicate(user_id, title)
            if existing is not None:
                return existing
            logger.warning(
                "ticket_conflict_without_open_duplicate",
                user_id=str(user_id),
                title=title,
                attempt=attempt,
            )
        raise RuntimeError("ticket_create_conflict_unresolved")

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

    async def update_status(self, ticket_id: uuid.UUID, status: TicketStatus) -> Ticket | None:
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

    async def find_open_duplicate(self, user_id: uuid.UUID, title: str) -> Ticket | None:
        """与 uniq_open_user_title partial index 同范围：所有未关闭/未解决的同名工单。

        ON CONFLICT 兜底路径用它回查"已经被另一并发请求创建的开放工单"，因此**必须不带时间窗口**——
        否则 24h 之前留下的长期未关闭工单会让冲突路径回查不到，从而抛 RuntimeError。
        """
        stmt = select(Ticket).where(
            and_(
                Ticket.user_id == user_id,
                Ticket.title == title,
                Ticket.status.in_([TicketStatus.pending, TicketStatus.processing]),
            )
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_all(
        self,
        limit: int = 20,
        offset: int = 0,
        status: TicketStatus | None = None,
    ) -> list[Ticket]:
        stmt = select(Ticket).order_by(Ticket.created_at.desc())
        if status is not None:
            stmt = stmt.where(Ticket.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

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
        """客服/管理员视角的全量工单检索，支持状态/优先级/负责人/关键词过滤。"""
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
        return result.scalar() or 0

    async def count_all(self, status: TicketStatus | None = None) -> int:
        stmt = select(func.count(Ticket.id))
        if status is not None:
            stmt = stmt.where(Ticket.status == status)
        result = await self._db.execute(stmt)
        return result.scalar() or 0

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
        return result.scalar() or 0

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
