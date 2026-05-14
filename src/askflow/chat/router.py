from __future__ import annotations

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


@router.websocket("/ws/{token}")
async def websocket_endpoint(ws: WebSocket, token: str):
    import jwt
    from pydantic import ValidationError

    from askflow.core.security import decode_access_token
    from askflow.core.database import async_session_factory
    from askflow.repositories.user_repo import UserRepo

    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        await ws.close(code=4001, reason="Invalid token")
        return

    async with async_session_factory() as db:
        user = await UserRepo(db).get_by_id(user_id)
        if user is None or not user.is_active:
            await ws.close(code=4001, reason="User not found or inactive")
            return

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
