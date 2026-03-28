from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.agent.service import get_agent_service
from askflow.repositories.ticket_repo import TicketRepo
from askflow.ticket.service import TicketService
from askflow.chat.manager import manager
from askflow.chat.protocol import (
    ClientMessage,
    ClientMessageType,
    ServerMessage,
    ServerMessageType,
)
from askflow.chat.session import session_store
from askflow.core.auth import get_current_user
from askflow.core.database import get_db
from askflow.core.exceptions import NotFoundError
from askflow.core.logging import get_logger
from askflow.core.rate_limiter import check_rate_limit
from askflow.models.conversation import ConversationStatus
from askflow.models.message import MessageRole
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
    await db.commit()
    await session_store.clear(str(conversation_id))
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
    from askflow.core.security import decode_access_token
    from askflow.core.database import async_session_factory
    from askflow.repositories.user_repo import UserRepo

    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        await ws.close(code=4001, reason="Invalid token")
        return

    async with async_session_factory() as db:
        user = await UserRepo(db).get_by_id(user_id)
        if user is None or not user.is_active:
            await ws.close(code=4001, reason="User not found or inactive")
            return

    connection_id = uuid.uuid4().hex
    await manager.connect(ws, connection_id, str(user_id))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = ClientMessage.model_validate_json(raw)
            except Exception:
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
                conversation_id = msg.conversation_id or uuid.uuid4().hex

                try:
                    await check_rate_limit(str(user_id))
                except Exception as e:
                    await manager.send_error(connection_id, str(e))
                    continue

                async with async_session_factory() as db:
                    conv_repo = ConversationRepo(db)
                    msg_repo = MessageRepo(db)

                    try:
                        conv_uuid = uuid.UUID(conversation_id)
                    except ValueError:
                        conv = await conv_repo.create(user_id=user_id)
                        conv_uuid = conv.id
                    else:
                        conv = await conv_repo.get_by_id(conv_uuid)
                        if conv is None:
                            conv = await conv_repo.create(user_id=user_id)
                            conv_uuid = conv.id
                        elif conv.user_id != user_id:
                            await manager.send_error(
                                connection_id,
                                "Conversation not found for current user",
                            )
                            continue

                    conversation_id = str(conv_uuid)

                    await session_store.add_message(conversation_id, "user", msg.content)
                    history = await session_store.get_history(conversation_id)

                    await msg_repo.create(
                        conversation_id=conv_uuid,
                        role=MessageRole.user,
                        content=msg.content,
                    )

                    ticket_service = TicketService(TicketRepo(db))
                    agent_service = get_agent_service(
                        ticket_service=ticket_service,
                        conversation_repo=conv_repo,
                    )
                    full_response = []
                    intent_result = None
                    sources = []

                    try:
                        result = await agent_service.process(
                            question=msg.content,
                            conversation_history=history,
                            user_id=str(user_id),
                            conversation_id=conversation_id,
                        )
                        intent_result = result.intent
                        sources = result.sources

                        if intent_result:
                            await manager.send(
                                connection_id,
                                ServerMessage(
                                    type=ServerMessageType.intent,
                                    conversation_id=conversation_id,
                                    data={
                                        "label": intent_result.label,
                                        "confidence": intent_result.confidence,
                                    },
                                ),
                            )

                        async for token_text in result.token_stream:
                            if _cancel_flags.get(connection_id):
                                break
                            full_response.append(token_text)
                            await manager.broadcast_token(
                                connection_id, conversation_id, token_text
                            )

                        # 工单创建成功时推送工单事件
                        if result.ticket_data:
                            await manager.send(
                                connection_id,
                                ServerMessage(
                                    type=ServerMessageType.ticket,
                                    conversation_id=conversation_id,
                                    data=result.ticket_data,
                                ),
                            )

                        # 转人工时推送 handoff 事件
                        if result.should_handoff:
                            await manager.send(
                                connection_id,
                                ServerMessage(
                                    type=ServerMessageType.handoff,
                                    conversation_id=conversation_id,
                                    data={"transferred": True},
                                ),
                            )
                    except Exception as e:
                        logger.exception("agent_processing_error", error=str(e))
                        error_msg = "抱歉，处理过程中出现错误，请稍后再试。"
                        full_response.append(error_msg)
                        await manager.broadcast_token(
                            connection_id, conversation_id, error_msg
                        )

                    response_text = "".join(full_response)
                    await session_store.add_message(
                        conversation_id, "assistant", response_text
                    )
                    await msg_repo.create(
                        conversation_id=conv_uuid,
                        role=MessageRole.assistant,
                        content=response_text,
                        intent=intent_result.label if intent_result else None,
                        confidence=intent_result.confidence if intent_result else None,
                        sources={"sources": sources} if sources else None,
                    )
                    await db.commit()

                    if sources:
                        await manager.send(
                            connection_id,
                            ServerMessage(
                                type=ServerMessageType.source,
                                conversation_id=conversation_id,
                                data={"sources": sources},
                            ),
                        )

                    await manager.send_message_end(
                        connection_id, conversation_id, sources
                    )

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(connection_id, str(user_id))
        _cancel_flags.pop(connection_id, None)
