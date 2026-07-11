"""审计日志只读接口（ops-platform/02 §Design 5）。

挂在 /api/v1/admin/audit-logs 下，admin-only。仅查询——写路径在各变更服务内联。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.audit import AUDIT_PAGE_LIMIT_MAX
from askflow.core.auth import require_role
from askflow.core.database import get_db
from askflow.models.user import User, UserRole
from askflow.repositories.audit_repo import AuditRepo
from askflow.schemas.audit import AuditLogResponse
from askflow.schemas.common import PaginatedResponse

router = APIRouter()

_DEFAULT_PAGE_LIMIT = 50


@router.get("", response_model=PaginatedResponse[AuditLogResponse])
async def list_audit_logs(
    entity_type: str | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(_DEFAULT_PAGE_LIMIT, gt=0, le=AUDIT_PAGE_LIMIT_MAX),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    repo = AuditRepo(db)
    filters = {"entity_type": entity_type, "actor_id": actor_id, "action": action}
    rows = await repo.list_filtered(**filters, limit=limit, offset=offset)
    total = await repo.count(**filters)
    return PaginatedResponse(
        data=[AuditLogResponse.model_validate(r) for r in rows],
        total=total,
        page=offset // limit + 1,
        limit=limit,
    )
