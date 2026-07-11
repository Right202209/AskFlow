"""一轮 agent 交互的驱动与事件推送——chat/service.py 的执行半边。

AgentTurn 是持久化与 message_end 构造共用的数据载体；stream_agent_response
负责驱动 AgentService 并把 intent / token / ticket / handoff 事件推给 WS 连接。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from askflow.chat.manager import manager
from askflow.chat.protocol import ServerMessage, ServerMessageType
from askflow.core.logging import get_logger
from askflow.knowledge.gap_recorder import TurnSignalContext
from askflow.schemas.intent import IntentResult

logger = get_logger(__name__)

AGENT_ERROR_RESPONSE = "抱歉，处理过程中出现错误，请稍后再试。"


@dataclass
class AgentTurn:
    """一轮 agent 交互的产物——持久化与 message_end 构造共用同一份数据。"""

    response_text: str = ""
    intent: IntentResult | None = None
    sources: list = field(default_factory=list)
    harness_trace: dict = field(default_factory=dict)
    should_handoff: bool = False


def turn_signal_context(
    question: str,
    turn: AgentTurn,
    *,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
) -> TurnSignalContext:
    """把一轮产物投影成缺口雷达需要的最小上下文，避免 knowledge → chat 的反向依赖。"""
    return TurnSignalContext(
        question=question,
        response_text=turn.response_text,
        sources=turn.sources,
        harness_trace=turn.harness_trace or {},
        should_handoff=turn.should_handoff,
        intent=turn.intent.label if turn.intent else None,
        conversation_id=conversation_id,
        message_id=message_id,
    )


async def stream_agent_response(
    *,
    agent_service,
    connection_id: str,
    conversation_id: str,
    question: str,
    history: list[dict[str, str]],
    user_id: uuid.UUID,
    is_cancelled: Callable[[], bool],
    ticket_service=None,
    conversation_repo=None,
    handoff_service=None,
    pending_tool: dict | None = None,
) -> AgentTurn:
    """驱动 Agent 并推送 intent / token / ticket / handoff 事件。"""
    turn = AgentTurn()
    full_response: list[str] = []

    try:
        result = await agent_service.process(
            question=question,
            conversation_history=history,
            user_id=str(user_id),
            conversation_id=conversation_id,
            ticket_service=ticket_service,
            conversation_repo=conversation_repo,
            handoff_service=handoff_service,
            pending_tool=pending_tool,
        )
        turn.intent = result.intent
        turn.sources = result.sources
        turn.should_handoff = bool(result.should_handoff)
        if result.harness_trace:
            turn.harness_trace = result.harness_trace
            logger.info(
                "agent_harness_trace",
                conversation_id=conversation_id,
                run_id=result.harness_trace.get("run_id"),
                route=result.harness_trace.get("route"),
                reason=result.harness_trace.get("reason"),
                flags=result.harness_trace.get("flags", []),
            )

        await _push_intent(connection_id, conversation_id, turn)

        async for token_text in result.token_stream:
            if is_cancelled():
                break
            full_response.append(token_text)
            await manager.broadcast_token(connection_id, conversation_id, token_text)

        await _push_side_effects(connection_id, conversation_id, result)
    except Exception:
        logger.exception("agent_processing_error")
        full_response.append(AGENT_ERROR_RESPONSE)
        await manager.broadcast_token(connection_id, conversation_id, AGENT_ERROR_RESPONSE)

    turn.response_text = "".join(full_response)
    return turn


async def _push_intent(connection_id: str, conversation_id: str, turn: AgentTurn) -> None:
    if not turn.intent:
        return
    await manager.send(
        connection_id,
        ServerMessage(
            type=ServerMessageType.intent,
            conversation_id=conversation_id,
            data={"label": turn.intent.label, "confidence": turn.intent.confidence},
        ),
    )


async def _push_side_effects(connection_id: str, conversation_id: str, result) -> None:
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
