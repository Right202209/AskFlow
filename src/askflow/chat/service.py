"""WebSocket 消息处理服务层，路由层只负责协议分发，真正的业务流程集中在这里。"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from askflow.agent.handoff import HandoffService
from askflow.agent.service import get_agent_service
from askflow.agent.slots import read_pending_tool
from askflow.chat.confidence import compute_answer_confidence
from askflow.chat.manager import manager
from askflow.chat.protocol import (
    ClientMessage,
    MessageEndPayload,
    ServerMessage,
    ServerMessageType,
)
from askflow.chat.push import publish_user_push
from askflow.chat.session import session_store
from askflow.chat.turns import AgentTurn, stream_agent_response, turn_signal_context
from askflow.config import settings
from askflow.core.database import async_session_factory
from askflow.core.exceptions import RateLimitError
from askflow.core.logging import get_logger
from askflow.core.masking import mask_text
from askflow.core.rate_limiter import check_rate_limit
from askflow.knowledge.gap_recorder import maybe_record_gap_from_turn
from askflow.models.conversation import Conversation, ConversationStatus
from askflow.models.message import MessageRole
from askflow.rag.grounding import WEAK_RETRIEVAL_REFUSAL_FLAG
from askflow.rag.llm_client import llm_client
from askflow.rag.verifier import (
    INVALID_CITATIONS_FLAG,
    VERIFY_SKIPPED_FLAG,
    VerificationResult,
    verify_answer,
)
from askflow.repositories.conversation_repo import ConversationRepo
from askflow.repositories.handoff_repo import HandoffRepo
from askflow.repositories.message_repo import MessageRepo
from askflow.repositories.ticket_repo import TicketRepo
from askflow.ticket.service import TicketService

logger = get_logger(__name__)


def _persisted_content(text: str) -> str:
    """按运营开关决定落库文本是否脱敏（默认关：脱敏会降低接管/摘要质量，ops-platform/02 D5）。"""
    return mask_text(text) if settings.mask_stored_messages else text


async def process_user_message(
    user_id: uuid.UUID,
    connection_id: str,
    msg: ClientMessage,
    is_cancelled: Callable[[], bool],
) -> None:
    """一条用户消息的完整生命周期：限流 → 会话落盘 → Agent → 流式回写 → 自检 → 事件推送。"""
    if not await _enforce_rate_limit(user_id, connection_id):
        return

    raw_conversation_id = msg.conversation_id or uuid.uuid4().hex

    async with async_session_factory() as db:
        conv_repo = ConversationRepo(db)
        msg_repo = MessageRepo(db)

        conversation = await _ensure_conversation(
            conv_repo, raw_conversation_id, user_id=user_id, connection_id=connection_id
        )
        if conversation is None:
            return
        conversation_id = str(conversation.id)

        # 人工接管期间（transferred）：消息照常落库并让客服可见，但绝不派发给 AI（D5）。
        if conversation.status == ConversationStatus.transferred:
            await _handle_transferred_message(
                db, msg_repo=msg_repo, conversation=conversation,
                msg=msg, connection_id=connection_id,
            )
            return

        await session_store.add_message(conversation_id, "user", msg.content)
        history = await session_store.get_history(conversation_id)
        await msg_repo.create(
            conversation_id=conversation.id,
            role=MessageRole.user,
            content=_persisted_content(msg.content),
        )

        # 单例 AgentService 在 lifespan 启动时已装配；这里只把请求级的 DB-bound
        # 依赖（ticket / conversation / handoff）通过 process() 参数传入。
        # pending_tool 从会话 metadata 读出——多轮槽位填充的续跑依据（agent/slots.py）。
        turn = await stream_agent_response(
            agent_service=get_agent_service(),
            connection_id=connection_id,
            conversation_id=conversation_id,
            question=msg.content,
            history=history,
            user_id=user_id,
            is_cancelled=is_cancelled,
            ticket_service=TicketService(TicketRepo(db)),
            conversation_repo=conv_repo,
            handoff_service=HandoffService(db, llm_client),
            pending_tool=read_pending_tool(conversation.metadata_),
        )

        await _finalize_assistant_turn(
            db=db,
            msg_repo=msg_repo,
            connection_id=connection_id,
            conversation_uuid=conversation.id,
            question=msg.content,
            turn=turn,
        )


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
    *,
    user_id: uuid.UUID,
    connection_id: str,
) -> Conversation | None:
    """按需创建或校验会话归属；返回完整 Conversation 对象（状态/metadata 后续流程要读）。"""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        return await conv_repo.create(user_id=user_id)

    conv = await conv_repo.get_by_id(conv_uuid)
    if conv is None:
        return await conv_repo.create(user_id=user_id)
    if conv.user_id != user_id:
        await manager.send_error(
            connection_id,
            "Conversation not found for current user",
        )
        return None
    return conv


async def _handle_transferred_message(
    db,
    *,
    msg_repo: MessageRepo,
    conversation: Conversation,
    msg: ClientMessage,
    connection_id: str,
) -> None:
    """接管态消息网关：落库 + 会话镜像 + 轻量回执，客服在线则实时递到收件箱视图。"""
    conversation_id = str(conversation.id)
    await session_store.add_message(conversation_id, "user", msg.content)
    await msg_repo.create(
        conversation_id=conversation.id,
        role=MessageRole.user,
        content=_persisted_content(msg.content),
    )
    session = await HandoffRepo(db).find_open_by_conversation(conversation.id)
    await db.commit()

    status = session.status.value if session else ConversationStatus.transferred.value
    await manager.send(
        connection_id,
        ServerMessage(
            type=ServerMessageType.handoff_update,
            conversation_id=conversation_id,
            data={"status": status},
        ),
    )
    if session and session.assignee:
        await publish_user_push(
            session.assignee,
            ServerMessage(
                type=ServerMessageType.handoff_update,
                conversation_id=conversation_id,
                data={"status": status, "new_user_message": msg.content},
            ),
        )


async def _finalize_assistant_turn(
    *,
    db,
    msg_repo: MessageRepo,
    connection_id: str,
    conversation_uuid: uuid.UUID,
    question: str,
    turn: AgentTurn,
) -> None:
    """自检 → 置信度 → 持久化 → source/message_end 推送；REST 与 WS 共用同一份 payload。"""
    conversation_id = str(conversation_uuid)
    verification = await _maybe_verify_answer(turn)
    confidence = compute_answer_confidence(turn.harness_trace, verification)
    answer_confidence = confidence.to_payload() if confidence else None

    await session_store.add_message(conversation_id, "assistant", turn.response_text)
    # harness_trace / verification / answer_confidence 都落到 messages.metadata，
    # 让"这条回答为什么被 truncate / 自检结论是什么"能用一句 SQL 查出来。
    assistant_message = await msg_repo.create(
        conversation_id=conversation_uuid,
        role=MessageRole.assistant,
        content=_persisted_content(turn.response_text),
        intent=turn.intent.label if turn.intent else None,
        confidence=turn.intent.confidence if turn.intent else None,
        sources={"sources": turn.sources} if turn.sources else None,
        extra=_build_message_extra(turn, verification, answer_confidence),
    )
    # 缺口雷达挂点（best-effort，共享本轮事务）：clarify / 拒答 / 弱检索 / 转人工在此捕获。
    await maybe_record_gap_from_turn(
        db,
        turn_signal_context(
            question, turn, conversation_id=conversation_uuid, message_id=assistant_message.id
        ),
    )
    await db.commit()

    if turn.sources:
        await manager.send(
            connection_id,
            ServerMessage(
                type=ServerMessageType.source,
                conversation_id=conversation_id,
                data={"sources": turn.sources},
            ),
        )
    await manager.send_message_end(
        connection_id,
        conversation_id,
        MessageEndPayload(
            sources=turn.sources,
            message_id=str(assistant_message.id),
            verification=verification,
            answer_confidence=answer_confidence,
        ),
    )


def _build_message_extra(
    turn: AgentTurn,
    verification: dict | None,
    answer_confidence: dict | None,
) -> dict | None:
    extra: dict = {}
    if turn.harness_trace:
        extra["harness_trace"] = turn.harness_trace
    if verification is not None:
        extra["verification"] = verification
    if answer_confidence is not None:
        extra["answer_confidence"] = answer_confidence
    return extra or None


async def _maybe_verify_answer(turn: AgentTurn) -> dict | None:
    """只对真正走 RAG 作答的轮次自检；拒答/非 rag/无来源轮次不产生自检记录。"""
    trace = turn.harness_trace or {}
    is_rag_answer = (
        trace.get("route") == "rag"
        and bool(turn.sources)
        and bool(turn.response_text)
        and WEAK_RETRIEVAL_REFUSAL_FLAG not in trace.get("flags", [])
    )
    if not is_rag_answer:
        return None

    result = await verify_answer(turn.response_text, turn.sources, llm_client)
    _record_verify_flags(trace, result)
    return result.to_payload()


def _record_verify_flags(trace: dict, result: VerificationResult) -> None:
    flags = list(trace.get("flags", []))
    if not result.checked and VERIFY_SKIPPED_FLAG not in flags:
        flags.append(VERIFY_SKIPPED_FLAG)
    if result.invalid_citations and INVALID_CITATIONS_FLAG not in flags:
        flags.append(INVALID_CITATIONS_FLAG)
    trace["flags"] = flags
