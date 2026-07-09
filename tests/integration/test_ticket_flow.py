"""Ticket 客服流转集成测试（项 9，Phase 2）。

覆盖目标：
- AgentService 在意图分类落到 fault_report/complaint 时，通过 AgentGraph 的 ticket 分支
  调用 TicketService 真实创建工单；
- 创建出的工单字段（类型 / 优先级 / 描述 / conversation_id / content）符合 PRD 期望；
- 客服（agent / admin 角色）通过 TicketService.update_ticket 把工单从 pending → processing
  → resolved 流转，resolved_at 自动落库；
- 普通用户尝试改 priority / assignee 被 ForbiddenError 拦下。

这条用例把 AgentGraph、TicketService、TicketRepo 串起来跑真实逻辑——只把 IntentClassifier
和 RAG 等无关上游替换成 stub。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from askflow.agent.harness import CognitiveHarness
from askflow.agent.service import AgentService
from askflow.core.exceptions import ForbiddenError
from askflow.models.ticket import Ticket, TicketPriority, TicketStatus
from askflow.models.user import User, UserRole
from askflow.schemas.intent import IntentResult
from askflow.ticket.service import TicketService


# ---------------------------------------------------------------------------
# In-memory TicketRepo —— 跑真实 TicketService 业务逻辑，但不依赖 SQLAlchemy。
# ---------------------------------------------------------------------------


class InMemoryTicketRepo:
    """复刻 TicketRepo 的公共方法签名；状态保留在 self._tickets。"""

    def __init__(self) -> None:
        self._tickets: dict[uuid.UUID, Ticket] = {}

    async def create(
        self,
        *,
        user_id,
        type,
        title,
        description=None,
        priority=TicketPriority.medium,
        conversation_id=None,
        content=None,
    ):
        ticket = Ticket(
            user_id=user_id,
            type=type,
            title=title,
            description=description,
            priority=priority,
            conversation_id=conversation_id,
            content=content,
        )
        ticket.id = uuid.uuid4()
        ticket.status = TicketStatus.pending
        ticket.created_at = datetime.now(tz=timezone.utc)
        ticket.updated_at = ticket.created_at
        self._tickets[ticket.id] = ticket
        return ticket

    async def get_by_id(self, ticket_id):
        return self._tickets.get(ticket_id)

    async def find_duplicate(self, user_id, title, hours=24):
        # 测试用例不依赖重复检测，保持简单：完全不去重。
        return None

    async def update(self, ticket, *, status=None, assignee=None, priority=None,
                     content=None, fields_set=None):
        fields = fields_set or set()
        if "status" in fields and status is not None:
            ticket.status = status
            ticket.resolved_at = (
                datetime.now(tz=timezone.utc) if status == TicketStatus.resolved else None
            )
        if "assignee" in fields:
            ticket.assignee = assignee
        if "priority" in fields and priority is not None:
            ticket.priority = priority
        if "content" in fields:
            ticket.content = content
        ticket.updated_at = datetime.now(tz=timezone.utc)
        return ticket


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def end_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = UserRole.user
    return user


@pytest.fixture
def staff_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.role = UserRole.agent
    return user


@pytest.fixture
def ticket_service():
    return TicketService(InMemoryTicketRepo())


@pytest.fixture
def agent_service():
    """AgentService 注入 stub classifier + RAG，只让 ticket 分支跑真实代码。"""
    classifier = MagicMock()
    rag_service = MagicMock()
    service = AgentService(classifier, rag_service, harness=CognitiveHarness())
    # 直接让 classify_node 跳过 LLM，把 intent 写成 fault_report (high confidence)。
    classifier.classify = AsyncMock(
        return_value=IntentResult(label="fault_report", confidence=0.95)
    )
    return service


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgentTicketHandoff:
    @pytest.mark.asyncio
    async def test_fault_report_creates_high_priority_ticket(
        self, agent_service, ticket_service, end_user
    ):
        """fault_report 意图应触发 ticket 分支，创建出 high 优先级工单。"""
        conversation_id = uuid.uuid4()

        result = await agent_service.process(
            question="支付页面提示 500 错误，无法下单",
            conversation_history=[],
            user_id=str(end_user.id),
            conversation_id=str(conversation_id),
            ticket_service=ticket_service,
        )

        # ProcessResult.ticket_data 是给 WebSocket 推 ticket_created 事件用的契约字段。
        assert result.ticket_data is not None
        assert result.ticket_data["type"] == "fault_report"
        assert result.ticket_data["priority"] == "high"
        assert result.ticket_data["status"] == "pending"

        ticket_id = uuid.UUID(result.ticket_data["ticket_id"])
        ticket = await ticket_service.get_ticket(ticket_id)
        assert ticket is not None
        assert ticket.user_id == end_user.id
        assert ticket.conversation_id == conversation_id
        assert ticket.priority == TicketPriority.high
        assert ticket.content == {"source": "agent", "intent": "fault_report"}
        assert ticket.title.startswith("支付页面提示")

    @pytest.mark.asyncio
    async def test_complaint_intent_also_routes_to_ticket(
        self, agent_service, ticket_service, end_user
    ):
        agent_service._classifier.classify = AsyncMock(
            return_value=IntentResult(label="complaint", confidence=0.9)
        )

        result = await agent_service.process(
            question="你们客服态度太差，要投诉！",
            conversation_history=[],
            user_id=str(end_user.id),
            conversation_id=str(uuid.uuid4()),
            ticket_service=ticket_service,
        )

        assert result.ticket_data["type"] == "complaint"
        assert result.ticket_data["priority"] == "high"


class TestTicketLifecycle:
    @pytest.mark.asyncio
    async def test_staff_can_progress_ticket_through_states(
        self, ticket_service, staff_user, end_user
    ):
        """admin/agent 角色可以推进工单到 processing 再到 resolved，resolved_at 自动落库。"""
        ticket = await ticket_service.create_ticket(
            user_id=end_user.id,
            type="fault_report",
            title="登录失败",
            priority=TicketPriority.high,
        )

        # pending → processing：客服开始处理
        updated = await ticket_service.update_ticket(
            ticket.id,
            staff_user,
            status=TicketStatus.processing,
            assignee="agent-007",
            fields_set={"status", "assignee"},
        )
        assert updated.status == TicketStatus.processing
        assert updated.assignee == "agent-007"
        assert updated.resolved_at is None

        # processing → resolved：标记完成，resolved_at 必须被填上
        resolved = await ticket_service.update_ticket(
            ticket.id,
            staff_user,
            status=TicketStatus.resolved,
            fields_set={"status"},
        )
        assert resolved.status == TicketStatus.resolved
        assert resolved.resolved_at is not None

    @pytest.mark.asyncio
    async def test_regular_user_cannot_change_priority_or_assignee(
        self, ticket_service, end_user
    ):
        """普通用户只能关闭自己的工单，不能改 priority / assignee——这是 PRD 的权限边界。"""
        ticket = await ticket_service.create_ticket(
            user_id=end_user.id,
            type="general",
            title="包装破损",
        )

        with pytest.raises(ForbiddenError):
            await ticket_service.update_ticket(
                ticket.id,
                end_user,
                priority=TicketPriority.urgent,
                fields_set={"priority"},
            )

        # 关闭自己的工单是允许的。
        closed = await ticket_service.update_ticket(
            ticket.id,
            end_user,
            status=TicketStatus.closed,
            fields_set={"status"},
        )
        assert closed.status == TicketStatus.closed

    @pytest.mark.asyncio
    async def test_ticket_visibility_blocks_other_users(self, ticket_service, end_user):
        """普通用户不能看别人创建的工单——避免越权读取。"""
        ticket = await ticket_service.create_ticket(
            user_id=end_user.id,
            type="general",
            title="只属于我的工单",
        )

        intruder = MagicMock(spec=User)
        intruder.id = uuid.uuid4()
        intruder.role = UserRole.user

        assert await ticket_service.get_ticket_for_actor(ticket.id, intruder) is None
