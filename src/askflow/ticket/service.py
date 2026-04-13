from __future__ import annotations

import uuid

from askflow.core.exceptions import ForbiddenError
from askflow.core.logging import get_logger
from askflow.core.metrics import TICKET_COUNT
from askflow.models.ticket import TicketPriority, TicketStatus
from askflow.models.user import User, UserRole
from askflow.repositories.ticket_repo import TicketRepo

logger = get_logger(__name__)


class TicketService:
    """封装工单创建、可见性和更新权限相关的业务规则。"""

    def __init__(self, repo: TicketRepo) -> None:
        self._repo = repo

    async def create_ticket(
        self,
        user_id: uuid.UUID,
        type: str,
        title: str,
        description: str | None = None,
        priority: str | TicketPriority = TicketPriority.medium,
        conversation_id: uuid.UUID | None = None,
        content: dict | None = None,
    ):
        """创建工单；若检测到重复工单，则直接返回已有记录。"""
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
        TICKET_COUNT.labels(type=type, priority=ticket_priority.value).inc()
        logger.info("ticket_created", ticket_id=str(ticket.id))
        return ticket

    async def get_ticket(self, ticket_id: uuid.UUID):
        return await self._repo.get_by_id(ticket_id)

    async def get_ticket_for_actor(self, ticket_id: uuid.UUID, actor: User):
        """只有工单本人或客服/管理员可以查看工单详情。"""
        ticket = await self._repo.get_by_id(ticket_id)
        if not ticket:
            return None
        if self._is_staff(actor) or ticket.user_id == actor.id:
            return ticket
        return None

    async def list_user_tickets(self, user_id: uuid.UUID, limit: int = 20, offset: int = 0):
        return await self._repo.list_by_user(user_id, limit, offset)

    async def count_user_tickets(self, user_id: uuid.UUID) -> int:
        return await self._repo.count_by_user(user_id)

    async def update_status(self, ticket_id: uuid.UUID, status: str):
        ticket_status = TicketStatus(status)
        return await self._repo.update_status(ticket_id, ticket_status)

    async def update_ticket(
        self,
        ticket_id: uuid.UUID,
        actor: User,
        *,
        status: TicketStatus | None = None,
        assignee: str | None = None,
        priority: TicketPriority | None = None,
        content: dict | None = None,
        fields_set: set[str] | None = None,
    ):
        """在写库前校验角色权限，限制普通用户能修改的字段范围。"""
        ticket = await self.get_ticket_for_actor(ticket_id, actor)
        if not ticket:
            return None

        provided_fields = fields_set or set()
        is_staff = self._is_staff(actor)

        if not is_staff:
            # 普通用户只能关闭自己的工单，不能改负责人或优先级。
            if "assignee" in provided_fields or "priority" in provided_fields:
                raise ForbiddenError("Only staff can update assignee or priority")
            if "status" in provided_fields and status != TicketStatus.closed:
                raise ForbiddenError("Users can only close their own tickets")

        return await self._repo.update(
            ticket,
            status=status if "status" in provided_fields else None,
            assignee=assignee,
            priority=priority if "priority" in provided_fields else None,
            content=content,
            fields_set=provided_fields,
        )

    async def get_stats(self) -> dict[str, int]:
        return await self._repo.count_by_status()

    @staticmethod
    def _is_staff(actor: User) -> bool:
        """管理员和客服都视为具备工单操作权限的工作人员。"""
        return actor.role in {UserRole.admin, UserRole.agent}
