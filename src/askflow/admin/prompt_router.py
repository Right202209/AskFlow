"""提示词模板管理接口（ops-platform/01 §Design 3）。

挂在 /api/v1/admin/prompts 下，独立成文件守住 admin/router.py 的 300 行上限。
读对 staff（admin/agent）开放；编辑与版本切换仅限 admin。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.admin.service import AdminService
from askflow.core.audit import (
    ACTION_PROMPT_ACTIVATE,
    ACTION_PROMPT_UPDATE,
    ENTITY_PROMPT_TEMPLATE,
    AuditContext,
    record_audit,
)
from askflow.core.auth import require_role
from askflow.core.database import get_db
from askflow.core.prompts import MAX_VERSIONS_LISTED
from askflow.models.user import User, UserRole
from askflow.schemas.common import APIResponse, PaginatedResponse
from askflow.schemas.prompt import (
    PromptTemplateResponse,
    PromptUpdateRequest,
    PromptVersionResponse,
)

router = APIRouter()

_STAFF_ROLES = (UserRole.admin, UserRole.agent)


@router.get("", response_model=APIResponse[list[PromptTemplateResponse]])
async def list_prompts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*_STAFF_ROLES)),
):
    pairs = await AdminService(db).list_prompts()
    return APIResponse(
        data=[PromptTemplateResponse.from_pair(template, version) for template, version in pairs]
    )


@router.get("/{key}/versions", response_model=PaginatedResponse[PromptVersionResponse])
async def list_prompt_versions(
    key: str,
    limit: int = Query(MAX_VERSIONS_LISTED, gt=0, le=MAX_VERSIONS_LISTED),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*_STAFF_ROLES)),
):
    versions, total = await AdminService(db).list_prompt_versions(key, limit=limit, offset=offset)
    return PaginatedResponse(
        data=[PromptVersionResponse.model_validate(v) for v in versions],
        total=total,
        page=offset // limit + 1,
        limit=limit,
    )


@router.put("/{key}", response_model=APIResponse[PromptTemplateResponse])
async def update_prompt(
    key: str,
    body: PromptUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    """编辑追加新版本并激活；占位符渲染校验失败返回 422（服务层 UnprocessableError）。"""
    template, version = await AdminService(db).update_prompt(
        key, content=body.content, comment=body.comment, user_id=user.id
    )
    await record_audit(
        db,
        AuditContext(
            actor=user,
            action=ACTION_PROMPT_UPDATE,
            entity_type=ENTITY_PROMPT_TEMPLATE,
            entity_id=template.id,
            detail={"key": key, "version": version.version, "comment": body.comment},
        ),
    )
    return APIResponse(data=PromptTemplateResponse.from_pair(template, version))


@router.post("/{key}/activate/{version_number}", response_model=APIResponse[PromptTemplateResponse])
async def activate_prompt_version(
    key: str,
    version_number: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    """回滚：把 active 指针拨回历史版本（不产生新版本行）。"""
    template, version = await AdminService(db).activate_prompt_version(key, version_number)
    await record_audit(
        db,
        AuditContext(
            actor=user,
            action=ACTION_PROMPT_ACTIVATE,
            entity_type=ENTITY_PROMPT_TEMPLATE,
            entity_id=template.id,
            detail={"key": key, "version": version_number},
        ),
    )
    return APIResponse(data=PromptTemplateResponse.from_pair(template, version))
