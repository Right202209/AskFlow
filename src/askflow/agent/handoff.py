"""人工接管协议的核心：转接载荷、摘要、入队与超时清扫（plan-docs/agent-real-handoff/02）。

摘要在转接轮同步生成但带硬超时（D4）：失败就转"仅转录"载荷（summary=""+
summary_failed flag），转接绝不因 LLM 阻塞或失败。recent_messages 从 MessageRepo
读（durable），不用 Redis session（20 条截断 + 24h TTL 不可靠）。
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.agent.state import AgentState
from askflow.config import settings
from askflow.core.logging import get_logger
from askflow.core.metrics import HANDOFF_TIMEOUT_COUNT
from askflow.models.conversation import ConversationStatus
from askflow.models.handoff import HandoffSession, HandoffStatus
from askflow.models.ticket import Ticket, TicketPriority
from askflow.rag.llm_client import LLMClient
from askflow.repositories.conversation_repo import ConversationRepo
from askflow.repositories.handoff_repo import HandoffRepo
from askflow.repositories.message_repo import MessageRepo
from askflow.repositories.ticket_repo import TicketRepo

logger = get_logger(__name__)

# --- 常量（plan-docs/agent-real-handoff/02 §Constants）---
HANDOFF_RECENT_MESSAGES = 10
HANDOFF_SUMMARY_TIMEOUT_S = 8
HANDOFF_SWEEP_INTERVAL_S = 60
SUMMARY_FAILED_FLAG = "summary_failed"
ESCALATION_TICKET_TYPE = "handoff_timeout"

SUMMARY_SYSTEM_PROMPT = (
    "You are a customer-service shift-handover assistant. Summarize the conversation "
    "for the human agent about to take over: the user's problem, what has been tried, "
    "and what they need now. Reply in the user's language, within 120 words, plain text."
)
SUMMARY_USER_TEMPLATE = """### Conversation
{transcript}

### Latest user message
{question}

Write the handover summary:"""


class HandoffService:
    """转接入队编排；与请求级 AsyncSession 绑定，由 chat 层按请求构造。"""

    def __init__(self, db: AsyncSession, llm: LLMClient) -> None:
        self._db = db
        self._llm = llm

    async def enqueue(self, state: AgentState) -> HandoffSession | None:
        """构建载荷 → 摘要（限时）→ 入队；同会话重复转接收敛到已有 open session。"""
        try:
            conv_uuid = uuid.UUID(state.conversation_id)
        except (ValueError, AttributeError):
            return None

        payload = await self._build_payload(state, conv_uuid)
        summary = await self._summarize(state.question, payload)
        if summary is None:
            payload["flags"] = [*payload.get("flags", []), SUMMARY_FAILED_FLAG]
            summary = ""

        session = await HandoffRepo(self._db).create(
            conversation_id=conv_uuid, summary=summary, payload=payload
        )
        logger.info("handoff_enqueued", session_id=str(session.id), summary_chars=len(summary))
        return session

    async def _build_payload(self, state: AgentState, conv_uuid: uuid.UUID) -> dict:
        conversation = await ConversationRepo(self._db).get_by_id(conv_uuid)
        messages = await MessageRepo(self._db).list_recent(conv_uuid, HANDOFF_RECENT_MESSAGES)

        intent_history: list[str] = []
        for message in messages:
            if message.intent and message.intent not in intent_history:
                intent_history.append(message.intent)

        ticket_rows = await self._db.execute(
            select(Ticket.id).where(Ticket.conversation_id == conv_uuid)
        )
        return {
            "recent_messages": [
                {
                    "role": m.role.value,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
            "intent_history": intent_history,
            "user_meta": {
                "user_id": state.user_id,
                "session_start_at": (
                    conversation.created_at.isoformat()
                    if conversation and conversation.created_at
                    else None
                ),
            },
            "ticket_refs": [str(row[0]) for row in ticket_rows.all()],
        }

    async def _summarize(self, question: str, payload: dict) -> str | None:
        """同步摘要 + 硬超时（D4）；任何失败返回 None，由调用方降级为仅转录载荷。"""
        transcript = "\n".join(
            f"{m['role']}: {m['content']}" for m in payload.get("recent_messages", [])
        )
        messages = [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": SUMMARY_USER_TEMPLATE.format(transcript=transcript, question=question),
            },
        ]
        try:
            summary = await asyncio.wait_for(
                self._llm.chat(messages), timeout=HANDOFF_SUMMARY_TIMEOUT_S
            )
            return summary.strip() or None
        except Exception as exc:
            logger.warning("handoff_summary_failed", error=str(exc))
            return None


async def sweep_expired_handoffs() -> int:
    """超时清扫（§7）：queued 超时 → 升级工单（必走 TicketRepo.create）→ timed_out → 通知用户。

    FOR UPDATE SKIP LOCKED 保证多 worker 并发清扫不重复升级（D9）。
    """
    from askflow.core.database import async_session_factory

    processed = 0
    async with async_session_factory() as db:
        repo = HandoffRepo(db)
        expired = await repo.sweep_expired(settings.handoff_pickup_timeout_min)
        for session in expired:
            await _escalate_expired(db, repo, session)
            processed += 1
        await db.commit()
    if processed:
        logger.info("handoff_sweep_escalated", count=processed)
    return processed


async def _escalate_expired(db: AsyncSession, repo: HandoffRepo, session: HandoffSession) -> None:
    conversation = await ConversationRepo(db).get_by_id(session.conversation_id)
    if conversation is None:
        await repo.close(
            session.id, from_status=HandoffStatus.queued, to_status=HandoffStatus.timed_out
        )
        return

    ticket = await TicketRepo(db).create(
        user_id=conversation.user_id,
        type=ESCALATION_TICKET_TYPE,
        title=f"人工接管超时：会话 {session.conversation_id}",
        description=session.summary or "转接后长时间无人认领，已自动升级为工单跟进。",
        priority=TicketPriority.high,
        conversation_id=session.conversation_id,
        content={"handoff_session_id": str(session.id)},
    )
    await repo.close(
        session.id, from_status=HandoffStatus.queued, to_status=HandoffStatus.timed_out
    )
    # 超时后会话交还 AI：否则 transferred 网关既没有客服也不派发 AI，用户被困死。
    await ConversationRepo(db).update_status(session.conversation_id, ConversationStatus.active)
    HANDOFF_TIMEOUT_COUNT.inc()
    await _notify_timeout(str(conversation.user_id), session, str(ticket.id))


async def _notify_timeout(user_id: str, session: HandoffSession, ticket_id: str) -> None:
    from askflow.chat.protocol import ServerMessage, ServerMessageType
    from askflow.chat.push import publish_user_push

    await publish_user_push(
        user_id,
        ServerMessage(
            type=ServerMessageType.handoff_update,
            conversation_id=str(session.conversation_id),
            data={"status": HandoffStatus.timed_out.value, "ticket_id": ticket_id},
        ),
    )
