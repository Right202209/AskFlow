"""草稿知识条目的评审队列接口（plan-docs/knowledge-loop/02 §Design 4）。

挂在 /api/v1/admin/drafts 下。读/编辑是 staff（admin/agent），
approve/reject 是 admin 独占——写门槛与 reindex 对齐。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.auth import require_role
from askflow.core.database import get_db
from askflow.core.exceptions import ConflictError, NotFoundError
from askflow.knowledge.draft_service import DEFAULT_DRAFTS_PAGE_SIZE, DraftService
from askflow.knowledge.publisher import PublishError
from askflow.models.knowledge_draft import DraftStatus
from askflow.models.user import User, UserRole
from askflow.rag.llm_client import llm_client
from askflow.repositories.knowledge_draft_repo import KnowledgeDraftRepo
from askflow.schemas.common import APIResponse, PaginatedResponse
from askflow.schemas.document import DocumentResponse
from askflow.schemas.knowledge import DraftResponse, DraftReview, DraftUpdate

router = APIRouter()

_MAX_PAGE_SIZE = 100


@router.get("", response_model=PaginatedResponse[DraftResponse])
async def list_drafts(
    status: DraftStatus = DraftStatus.draft,
    limit: int = Query(DEFAULT_DRAFTS_PAGE_SIZE, gt=0, le=_MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    repo = KnowledgeDraftRepo(db)
    drafts = await repo.list_drafts(status=status, limit=limit, offset=offset)
    total = await repo.count(status=status)
    return PaginatedResponse(
        data=[DraftResponse.model_validate(d) for d in drafts],
        total=total,
        page=offset // limit + 1,
        limit=limit,
    )


@router.get("/{draft_id}", response_model=APIResponse[DraftResponse])
async def get_draft(
    draft_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    draft = await KnowledgeDraftRepo(db).get_by_id(draft_id)
    if draft is None:
        raise NotFoundError("Draft not found")
    return APIResponse(data=DraftResponse.model_validate(draft))


@router.put("/{draft_id}", response_model=APIResponse[DraftResponse])
async def update_draft(
    draft_id: uuid.UUID,
    body: DraftUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    repo = KnowledgeDraftRepo(db)
    draft = await repo.get_by_id(draft_id)
    if draft is None:
        raise NotFoundError("Draft not found")
    if draft.status != DraftStatus.draft:
        raise ConflictError("Only pending drafts can be edited")
    draft = await repo.update_body(draft, question=body.question, answer=body.answer)
    await db.commit()
    return APIResponse(data=DraftResponse.model_validate(draft))


@router.post("/{draft_id}/approve", response_model=APIResponse[DocumentResponse])
async def approve_draft(
    draft_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    """审批通过并经现有文档管线发布；发布失败草稿自动回到评审队列（可重试）。"""
    service = DraftService(db, llm_client)
    try:
        doc = await service.approve(draft_id, user.id)
    except PublishError as error:
        await db.commit()  # 提交"回退到 draft"的状态，让评审可重试。
        return APIResponse(success=False, error=str(error))
    await db.commit()
    return APIResponse(data=DocumentResponse.model_validate(doc))


@router.post("/{draft_id}/reject", response_model=APIResponse[DraftResponse])
async def reject_draft(
    draft_id: uuid.UUID,
    body: DraftReview,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    """驳回草稿；对应缺口保持 open（问题仍未被知识库覆盖）。"""
    service = DraftService(db, llm_client)
    draft = await service.reject(draft_id, user.id, body.review_note)
    await db.commit()
    return APIResponse(data=DraftResponse.model_validate(draft))
