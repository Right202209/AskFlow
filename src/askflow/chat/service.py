"""WebSocket 消息处理服务层，路由层只负责协议分发，真正的业务流程集中在这里。"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from askflow.agent.service import get_agent_service
from askflow.chat.manager import manager
from askflow.chat.protocol import ClientMessage, ServerMessage, ServerMessageType
from askflow.chat.session import session_store
from askflow.core.database import async_session_factory
from askflow.core.exceptions import RateLimitError
from askflow.core.logging import get_logger
from askflow.core.rate_limiter import check_rate_limit
from askflow.models.message import MessageRole
from askflow.repositories.conversation_repo import ConversationRepo
from askflow.repositories.message_repo import MessageRepo
from askflow.repositories.ticket_repo import TicketRepo
from askflow.ticket.service import TicketService

logger = get_logger(__name__)


async def process_user_message(
    user_id: uuid.UUID,
    connection_id: str,
    msg: ClientMessage,
    is_cancelled: Callable[[], bool],
) -> None:
    """一条用户消息的完整生命周期：限流 → 会话落盘 → Agent → 流式回写 → 事件推送。"""
    if not await _enforce_rate_limit(user_id, connection_id):
        return

    conversation_id = msg.conversation_id or uuid.uuid4().hex

    async with async_session_factory() as db:
        conv_repo = ConversationRepo(db)
        msg_repo = MessageRepo(db)

        conv_uuid = await _ensure_conversation(conv_repo, conversation_id, user_id, connection_id)
        if conv_uuid is None:
            return
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

        response_text, intent_result, sources = await _stream_agent_response(
            agent_service=agent_service,
            connection_id=connection_id,
            conversation_id=conversation_id,
            question=msg.content,
            history=history,
            user_id=user_id,
            is_cancelled=is_cancelled,
        )

        await session_store.add_message(conversation_id, "assistant", response_text)
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
        await manager.send_message_end(connection_id, conversation_id, sources)


async def _enforce_rate_limit(user_id: uuid.UUID, connection_id: str) -> bool:
    try:
        await check_rate_limit(str(user_id))
        return True
    except RateLimitError as e:
        await manager.send_error(connection_id, e.message)
        return False
    except Exception:
        logger.exception("rate_limit_check_failed", user_id=str(user_id))
        await manager.send_error(connection_id, "Rate limit check failed")
        return False


async def _ensure_conversation(
    conv_repo: ConversationRepo,
    conversation_id: str,
    user_id: uuid.UUID,
    connection_id: str,
) -> uuid.UUID | None:
    """按需创建或校验会话归属，返回 UUID，或在不属于当前用户时返回 None。"""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        conv = await conv_repo.create(user_id=user_id)
        return conv.id

    conv = await conv_repo.get_by_id(conv_uuid)
    if conv is None:
        conv = await conv_repo.create(user_id=user_id)
        return conv.id
    if conv.user_id != user_id:
        await manager.send_error(
            connection_id,
            "Conversation not found for current user",
        )
        return None
    return conv_uuid


async def _stream_agent_response(
    agent_service,
    connection_id: str,
    conversation_id: str,
    question: str,
    history: list[dict[str, str]],
    user_id: uuid.UUID,
    is_cancelled: Callable[[], bool],
) -> tuple[str, object, list]:
    """驱动 Agent 并推送 intent / token / ticket / handoff 事件。"""
    full_response: list[str] = []
    intent_result = None
    sources: list = []

    try:
        result = await agent_service.process(
            question=question,
            conversation_history=history,
            user_id=str(user_id),
            conversation_id=conversation_id,
        )
        if result.harness_trace:
            logger.info(
                "agent_harness_trace",
                conversation_id=conversation_id,
                run_id=result.harness_trace.get("run_id"),
                route=result.harness_trace.get("route"),
                reason=result.harness_trace.get("reason"),
                flags=result.harness_trace.get("flags", []),
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
            if is_cancelled():
                break
            full_response.append(token_text)
            await manager.broadcast_token(connection_id, conversation_id, token_text)

        if result.ticket_data:
            await manager.send(
                connection_id,
                ServerMessage(
                    type=ServerMessageType.ticket,
                    conversation_id=conversation_id,
                    data=result.ticket_data,
                ),
            )

        if result.should_handoff:
            await manager.send(
                connection_id,
                ServerMessage(
                    type=ServerMessageType.handoff,
                    conversation_id=conversation_id,
                    data={"transferred": True},
                ),
            )
    except Exception:
        logger.exception("agent_processing_error")
        error_msg = "抱歉，处理过程中出现错误，请稍后再试。"
        full_response.append(error_msg)
        await manager.broadcast_token(connection_id, conversation_id, error_msg)

    return "".join(full_response), intent_result, sources
