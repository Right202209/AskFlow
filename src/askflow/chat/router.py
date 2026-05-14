from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.chat.manager import manager
from askflow.chat.protocol import (
    ClientMessage,
    ClientMessageType,
    ServerMessage,
    ServerMessageType,
)
from askflow.chat.service import process_user_message
from askflow.chat.session import session_store
from askflow.core.auth import get_current_user
from askflow.core.database import get_db
from askflow.core.exceptions import NotFoundError
from askflow.core.logging import get_logger
from askflow.models.conversation import ConversationStatus
from askflow.models.user import User
from askflow.repositories.conversation_repo import ConversationRepo
from askflow.repositories.message_repo import MessageRepo
from askflow.schemas.common import APIResponse
from askflow.schemas.conversation import (
    DeleteConversationResponse,
    ConversationCreate,
    ConversationRename,
    ConversationResponse,
)
from askflow.schemas.message import MessageResponse

logger = get_logger(__name__)

router = APIRouter()

# 握手后允许客户端发送 auth 帧的最长等待时间，避免恶意挂连接占用资源。
AUTH_FRAME_TIMEOUT_SECONDS = 5

_cancel_flags: dict[str, bool] = {}


async def _get_user_conversation(
    repo: ConversationRepo, conversation_id: uuid.UUID, user_id: uuid.UUID
):
    conversation = await repo.get_by_id_for_user(conversation_id, user_id)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    return conversation


@router.post("/conversations", response_model=APIResponse[ConversationResponse])
async def create_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = ConversationRepo(db)
    conv = await repo.create(user_id=user.id, title=body.title)
    return APIResponse(data=ConversationResponse.model_validate(conv))


@router.get(
    "/conversations",
    response_model=APIResponse[list[ConversationResponse]],
)
async def list_conversations(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = ConversationRepo(db)
    conversations = await repo.list_by_user(user.id, limit=limit, offset=offset)
    return APIResponse(data=[ConversationResponse.model_validate(c) for c in conversations])


@router.patch(
    "/conversations/{conversation_id}",
    response_model=APIResponse[ConversationResponse],
)
async def rename_conversation(
    conversation_id: uuid.UUID,
    body: ConversationRename,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = ConversationRepo(db)
    await _get_user_conversation(repo, conversation_id, user.id)
    conversation = await repo.update_title(conversation_id, body.title)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    await db.commit()
    return APIResponse(data=ConversationResponse.model_validate(conversation))


@router.post(
    "/conversations/{conversation_id}/archive",
    response_model=APIResponse[ConversationResponse],
)
async def archive_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = ConversationRepo(db)
    await _get_user_conversation(repo, conversation_id, user.id)
    conversation = await repo.update_status(conversation_id, ConversationStatus.closed)
    if conversation is None:
        raise NotFoundError("Conversation not found")
    await db.commit()
    return APIResponse(data=ConversationResponse.model_validate(conversation))


@router.delete(
    "/conversations/{conversation_id}",
    response_model=APIResponse[DeleteConversationResponse],
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = ConversationRepo(db)
    await _get_user_conversation(repo, conversation_id, user.id)
    deleted = await repo.delete(conversation_id)
    if not deleted:
        raise NotFoundError("Conversation not found")

    try:
        await session_store.clear(str(conversation_id))
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(
            "conversation_delete_failed",
            conversation_id=str(conversation_id),
            user_id=str(user.id),
        )
        raise

    return APIResponse(data=DeleteConversationResponse(deleted=True))


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=APIResponse[list[MessageResponse]],
)
async def get_messages(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv_repo = ConversationRepo(db)
    await _get_user_conversation(conv_repo, conversation_id, user.id)

    repo = MessageRepo(db)
    messages = await repo.list_by_conversation(conversation_id)
    return APIResponse(data=[MessageResponse.model_validate(m) for m in messages])


async def _authenticate_token(token: str) -> uuid.UUID | None:
    """校验 JWT 并确认用户存在且活跃，失败一律返回 None 由调用方决定关闭语义。"""
    import jwt

    from askflow.core.database import async_session_factory
    from askflow.core.security import decode_access_token
    from askflow.repositories.user_repo import UserRepo

    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None

    async with async_session_factory() as db:
        user = await UserRepo(db).get_by_id(user_id)
        if user is None or not user.is_active:
            return None
    return user_id


async def _run_session(ws: WebSocket, user_id: uuid.UUID) -> None:
    """认证后驱动连接的消息循环；调用方必须在此之前完成 ws.accept()。"""
    from pydantic import ValidationError

    connection_id = uuid.uuid4().hex
    await manager.connect(ws, connection_id, str(user_id))

    def is_cancelled() -> bool:
        return _cancel_flags.get(connection_id, False)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = ClientMessage.model_validate_json(raw)
            except (ValidationError, ValueError):
                await manager.send_error(connection_id, "Invalid message format")
                continue

            if msg.type == ClientMessageType.auth:
                # 已认证连接上再收到 auth 帧是误用，丢弃即可，不要重新认证。
                continue

            if msg.type == ClientMessageType.ping:
                await manager.send(
                    connection_id,
                    ServerMessage(type=ServerMessageType.pong),
                )
                continue

            if msg.type == ClientMessageType.cancel:
                _cancel_flags[connection_id] = True
                continue

            if msg.type == ClientMessageType.message:
                _cancel_flags[connection_id] = False
                await process_user_message(user_id, connection_id, msg, is_cancelled)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(connection_id, str(user_id))
        _cancel_flags.pop(connection_id, None)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """握手后等待首帧 auth 完成认证，让 JWT 不再出现在 URL/access log/浏览器历史中。"""
    from pydantic import ValidationError

    await ws.accept()

    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_FRAME_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        await ws.close(code=4001, reason="Auth frame timeout")
        return
    except WebSocketDisconnect:
        return

    try:
        msg = ClientMessage.model_validate_json(raw)
    except (ValidationError, ValueError):
        await ws.close(code=4001, reason="Invalid auth frame")
        return

    if msg.type != ClientMessageType.auth or not msg.token:
        await ws.close(code=4001, reason="First frame must be auth")
        return

    user_id = await _authenticate_token(msg.token)
    if user_id is None:
        await ws.close(code=4001, reason="Invalid token")
        return

    await _run_session(ws, user_id)


@router.websocket("/ws/{token}")
async def websocket_endpoint_legacy(ws: WebSocket, token: str):
    """Deprecated: token-in-URL 会被反代日志和浏览器历史记录，请改用 /ws + auth 帧。"""
    logger.warning("ws_legacy_url_token_used")

    user_id = await _authenticate_token(token)
    if user_id is None:
        await ws.close(code=4001, reason="Invalid token")
        return

    await ws.accept()
    await _run_session(ws, user_id)
