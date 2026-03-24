from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.agent.service import get_agent_service
from askflow.chat.manager import manager
from askflow.chat.protocol import ClientMessage, ClientMessageType, ServerMessage, ServerMessageType
from askflow.chat.session import session_store
from askflow.core.auth import get_current_user
from askflow.core.database import get_db
from askflow.core.exceptions import NotFoundError
from askflow.core.logging import get_logger
from askflow.core.rate_limiter import check_rate_limit
from askflow.models.message import MessageRole
from askflow.models.user import User
from askflow.repositories.conversation_repo import ConversationRepo
from askflow.repositories.message_repo import MessageRepo
from askflow.schemas.common import APIResponse
from askflow.schemas.conversation import ConversationCreate, ConversationResponse
from askflow.schemas.message import MessageResponse

logger = get_logger(__name__)

router = APIRouter()

_cancel_flags: dict[str, bool] = {}


@router.post("/conversations", response_model=APIResponse[ConversationResponse])
async def create_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = ConversationRepo(db)
    conv = await repo.create(user_id=user.id, title=body.title)
    return APIResponse(data=ConversationResponse.model_validate(conv))


@router.get("/conversations", response_model=APIResponse[list[ConversationResponse]])
async def list_conversations(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = ConversationRepo(db)
    conversations = await repo.list_by_user(user.id, limit=limit, offset=offset)
    return APIResponse(data=[ConversationResponse.model_validate(c) for c in conversations])


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
    conversation = await conv_repo.get_by_id(conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise NotFoundError("Conversation not found")

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

                    agent_service = get_agent_service()
                    full_response = []

                    try:
                        token_stream, sources, intent_result = await agent_service.process(
                            question=msg.content,
                            conversation_history=history,
                            user_id=str(user_id),
                            conversation_id=conversation_id,
                        )

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

                        async for token_text in token_stream:
                            if _cancel_flags.get(connection_id):
                                break
                            full_response.append(token_text)
                            await manager.broadcast_token(
                                connection_id, conversation_id, token_text
                            )
                    except Exception as e:
                        logger.exception("agent_processing_error", error=str(e))
                        error_msg = "Sorry, an error occurred. Please try again."
                        full_response.append(error_msg)
                        await manager.broadcast_token(
                            connection_id, conversation_id, error_msg
                        )
                        sources = []

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
