"""管理面变更审计（plan-docs/ops-platform/02，D4）。

写路径是显式服务调用，不是装饰器/中间件：有价值的载荷（变更前状态、文档标题、
版本号）只在服务内部才知道，且中间件在独立事务提交——为已回滚的变更留审计行比不留
更糟。因此 record_audit 复用端点已持有的同一 AsyncSession，变更成功后、响应前调用，
commit/rollback 共享 → 变更与审计原子成对。detail 落库前经 masking 脱敏。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.masking import mask_dict
from askflow.core.metrics import AUDIT_EVENTS
from askflow.core.trace import get_trace_id
from askflow.models.audit_log import AuditLog
from askflow.models.user import User

# 动作词表——审计行的 action 列取值。
ACTION_DOCUMENT_UPLOAD = "document.upload"
ACTION_DOCUMENT_REINDEX = "document.reindex"
ACTION_DOCUMENT_INDEX_FAILED = "document.index_failed"
ACTION_DOCUMENT_DELETE = "document.delete"
ACTION_INTENT_CREATE = "intent.create"
ACTION_INTENT_UPDATE = "intent.update"
ACTION_INTENT_DELETE = "intent.delete"
ACTION_PROMPT_UPDATE = "prompt.update"
ACTION_PROMPT_ACTIVATE = "prompt.activate"
ACTION_TICKET_STATUS_CHANGE = "ticket.status_change"

# 实体类型——审计行的 entity_type 列取值。
ENTITY_DOCUMENT = "document"
ENTITY_INTENT_CONFIG = "intent_config"
ENTITY_PROMPT_TEMPLATE = "prompt_template"
ENTITY_TICKET = "ticket"

AUDIT_RETENTION_DAYS = 365
AUDIT_PAGE_LIMIT_MAX = 100


@dataclass
class AuditContext:
    """审计参数聚合——绕开 ≤3 位置参约束。"""

    actor: User
    action: str
    entity_type: str
    entity_id: uuid.UUID | None = None
    detail: dict | None = None


async def record_audit(db: AsyncSession, ctx: AuditContext) -> None:
    """在调用方事务内追加一条脱敏审计行（不 commit——随主变更一起提交/回滚）。"""
    row = AuditLog(
        actor_id=ctx.actor.id,
        actor_role=ctx.actor.role.value,
        action=ctx.action,
        entity_type=ctx.entity_type,
        entity_id=ctx.entity_id,
        detail=mask_dict(ctx.detail) if ctx.detail else None,
        trace_id=get_trace_id() or None,
    )
    db.add(row)
    # 计数在 db.add 之后自增——极少数随主事务回滚的情况会轻微多计，对 Counter 可接受。
    AUDIT_EVENTS.labels(action=ctx.action).inc()
