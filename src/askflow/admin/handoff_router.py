"""客服收件箱接口（plan-docs/agent-real-handoff/02 §Design 4）。

挂在 /api/v1/admin/handoffs 下，独立于 admin/router.py 以守住 300 行文件上限。
读/认领/回复对 staff（admin/agent）开放；回复与关闭仅限当前 assignee。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.chat.protocol import ServerMessage, ServerMessageType
from askflow.chat.push import publish_user_push
from askflow.chat.session import session_store
from askflow.core.auth import require_role
from askflow.core.database import get_db
from askflow.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from askflow.models.conversation import ConversationStatus
from askflow.models.handoff import HandoffSession, HandoffStatus
from askflow.models.message import MessageRole
from askflow.models.user import User, UserRole
from askflow.repositories.conversation_repo import ConversationRepo
from askflow.repositories.handoff_repo import HandoffRepo
from askflow.repositories.message_repo import MessageRepo
from askflow.schemas.common import APIResponse, PaginatedResponse
from askflow.schemas.handoff import (
    HandoffDetailResponse,
    HandoffReplyRequest,
    HandoffResolveRequest,
    HandoffSessionResponse,
)
from askflow.schemas.message import MessageResponse

router = APIRouter()

DEFAULT_HANDOFFS_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100

_STAFF_ROLES = (UserRole.admin, UserRole.agent)


@router.get("", response_model=PaginatedResponse[HandoffSessionResponse])
async def list_handoffs(
    status: HandoffStatus | None = HandoffStatus.queued,
    limit: int = Query(DEFAULT_HANDOFFS_PAGE_SIZE, gt=0, le=_MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*_STAFF_ROLES)),
):
    repo = HandoffRepo(db)
    sessions = await repo.list_sessions(status=status, limit=limit, offset=offset)
    total = await repo.count(status=status)
    return PaginatedResponse(
        data=[HandoffSessionResponse.model_validate(s) for s in sessions],
        total=total,
        page=offset // limit + 1,
        limit=limit,
    )


@router.get("/{session_id}", response_model=APIResponse[HandoffDetailResponse])
async def get_handoff(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*_STAFF_ROLES)),
):
    session = await _get_session(db, session_id)
    messages = await MessageRepo(db).list_by_conversation(session.conversation_id)
    return APIResponse(
        data=HandoffDetailResponse(
            session=HandoffSessionResponse.model_validate(session),
            messages=[MessageResponse.model_validate(m) for m in messages],
        )
    )


@router.post("/{session_id}/claim", response_model=APIResponse[HandoffSessionResponse])
async def claim_handoff(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*_STAFF_ROLES)),
):
    """原子认领：两个客服抢同一条时，条件 UPDATE 的输家拿 409（D9）。"""
    session = await _get_session(db, session_id)
    claimed = await HandoffRepo(db).claim(session_id, assignee=str(user.id))
    if claimed is None:
        raise ConflictError("Handoff already claimed or closed")
    await db.commit()

    await _push_status_update(db, claimed, {"status": claimed.status.value})
    return APIResponse(data=HandoffSessionResponse.model_validate(claimed))


@router.post("/{session_id}/reply", response_model=APIResponse[HandoffSessionResponse])
async def reply_handoff(
    session_id: uuid.UUID,
    body: HandoffReplyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*_STAFF_ROLES)),
):
    """客服回复：DB 里以 staff 角色落库，Redis 会话镜像为 assistant（AGENTS.md §5，D8）。"""
    session = await _require_assignee(db, session_id, user)
    conversation_id = str(session.conversation_id)

    await MessageRepo(db).create(
        conversation_id=session.conversation_id,
        role=MessageRole.staff,
        content=body.content,
    )
    # 镜像为 assistant：harness 历史白名单只认 user/assistant，否则暖回流后 AI 看不到人工说过什么。
    await session_store.add_message(conversation_id, "assistant", body.content)
    await db.commit()

    await _push_status_update(
        db,
        session,
        {"content": body.content, "staff_name": user.username},
        frame_type=ServerMessageType.staff_message,
    )
    return APIResponse(data=HandoffSessionResponse.model_validate(session))


@router.post("/{session_id}/resolve", response_model=APIResponse[HandoffSessionResponse])
async def resolve_handoff(
    session_id: uuid.UUID,
    body: HandoffResolveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*_STAFF_ROLES)),
):
    """关闭接管：会话暖回流到 active（AI 恢复接管，能看到镜像后的人工轮次）或显式关闭。"""
    session = await _require_assignee(db, session_id, user)
    closed = await HandoffRepo(db).close(
        session_id, from_status=HandoffStatus.claimed, to_status=body.status
    )
    if closed is None:
        raise ConflictError("Handoff already closed")

    next_status = (
        ConversationStatus.closed if body.close_conversation else ConversationStatus.active
    )
    await ConversationRepo(db).update_status(session.conversation_id, next_status)
    await db.commit()

    await _push_status_update(db, closed, {"status": closed.status.value})
    return APIResponse(data=HandoffSessionResponse.model_validate(closed))


async def _get_session(db: AsyncSession, session_id: uuid.UUID) -> HandoffSession:
    session = await HandoffRepo(db).get_by_id(session_id)
    if session is None:
        raise NotFoundError("Handoff session not found")
    return session


async def _require_assignee(db: AsyncSession, session_id: uuid.UUID, user: User) -> HandoffSession:
    """回复/关闭只允许当前认领人操作（未认领/他人认领一律 403/409 语义）。"""
    session = await _get_session(db, session_id)
    if session.status != HandoffStatus.claimed:
        raise ConflictError("Handoff is not in claimed state")
    if session.assignee != str(user.id):
        raise ForbiddenError("Only the assignee can operate this handoff")
    return session


async def _push_status_update(
    db: AsyncSession,
    session: HandoffSession,
    data: dict,
    frame_type: ServerMessageType = ServerMessageType.handoff_update,
) -> None:
    """把状态/回复实时推给会话属主（跨 worker 走 Redis 桥）；用户不在线则静默。"""
    conversation = await ConversationRepo(db).get_by_id(session.conversation_id)
    if conversation is None:
        return
    await publish_user_push(
        str(conversation.user_id),
        ServerMessage(
            type=frame_type,
            conversation_id=str(session.conversation_id),
            data=data,
        ),
    )
