from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from askflow.agent.intent_classifier import IntentClassifier
from askflow.agent.state import AgentState
from askflow.core.logging import get_logger
from askflow.rag.service import RAGService
from askflow.ticket.service import TicketService

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Intent → ticket type / priority mapping
# ---------------------------------------------------------------------------
_INTENT_TICKET_MAP: dict[str, dict] = {
    "fault_report": {"type": "fault_report", "priority": "high"},
    "complaint": {"type": "complaint", "priority": "high"},
}
_DEFAULT_TICKET = {"type": "general", "priority": "medium"}


async def classify_node(state: AgentState, classifier: IntentClassifier) -> AgentState:
    """补全下游路由依赖的意图信息。"""
    intent = await classifier.classify(state.question, state.conversation_history)
    state.intent = intent
    state.needs_clarification = intent.needs_clarification
    logger.info(
        "intent_classified",
        intent=intent.label,
        confidence=intent.confidence,
    )
    return state


async def rag_node(state: AgentState, rag_service: RAGService) -> AgentState:
    """执行 RAG 查询，并把流式输出写回可变的 agent 状态。"""
    try:
        token_stream, sources = await rag_service.query_stream(
            question=state.question,
            conversation_history=state.conversation_history,
        )
        state.sources = sources

        async for token in token_stream:
            state.response_tokens.append(token)
    except Exception as e:
        logger.error("rag_node_error", error=str(e))
        state.error = str(e)
    return state


async def rag_stream_node(
    state: AgentState, rag_service: RAGService
) -> tuple[AsyncIterator[str], list[dict]]:
    """直接返回 RAG 流，适合由上层 WebSocket/HTTP 逐 token 转发。"""
    return await rag_service.query_stream(
        question=state.question,
        conversation_history=state.conversation_history,
    )


async def ticket_node(state: AgentState, ticket_service: TicketService) -> AgentState:
    """通过 TicketService 创建真实工单，并将工单信息写入 state。"""
    intent_label = state.intent.label if state.intent else "general"
    ticket_cfg = _INTENT_TICKET_MAP.get(intent_label, _DEFAULT_TICKET)

    try:
        user_uuid = uuid.UUID(state.user_id)
    except (ValueError, AttributeError):
        state.error = "Invalid user identity, cannot create ticket."
        state.response_tokens = [state.error]
        return state

    conv_uuid: uuid.UUID | None = None
    if state.conversation_id:
        try:
            conv_uuid = uuid.UUID(state.conversation_id)
        except ValueError:
            pass

    try:
        ticket = await ticket_service.create_ticket(
            user_id=user_uuid,
            type=ticket_cfg["type"],
            title=state.question[:200],
            description=state.question,
            priority=ticket_cfg["priority"],
            conversation_id=conv_uuid,
            content={"source": "agent", "intent": intent_label},
        )
        state.ticket_id = str(ticket.id)
        state.ticket_data = {
            "ticket_id": str(ticket.id),
            "status": ticket.status.value
            if hasattr(ticket.status, "value")
            else str(ticket.status),
            "type": ticket.type,
            "priority": ticket.priority.value
            if hasattr(ticket.priority, "value")
            else str(ticket.priority),
        }
        state.response_tokens = [
            f"已为您创建工单，编号：{ticket.id}。",
            "客服人员将尽快跟进处理，请留意工单状态更新。",
        ]
    except Exception as e:
        logger.error("ticket_node_create_failed", error=str(e))
        state.error = str(e)
        state.response_tokens = [
            "抱歉，工单创建失败，请稍后再试或联系人工客服。",
        ]
    return state


async def handoff_node(
    state: AgentState,
    conversation_repo=None,
) -> AgentState:
    """标记需要人工接管，并将会话状态更新为 transferred。"""
    state.should_handoff = True

    if conversation_repo and state.conversation_id:
        try:
            from askflow.models.conversation import ConversationStatus

            conv_uuid = uuid.UUID(state.conversation_id)
            await conversation_repo.update_status(conv_uuid, ConversationStatus.transferred)
            logger.info("conversation_transferred", conversation_id=state.conversation_id)
        except Exception as e:
            logger.error("handoff_transfer_failed", error=str(e))

    state.response_tokens = [
        "正在为您转接人工客服，请稍候。",
        "您的问题摘要和对话记录将一并转交给客服人员。",
    ]
    return state


async def tool_node(state: AgentState, llm_client=None) -> AgentState:
    """业务查询工具调用节点。

    通过 LLM 提取查询参数，调用对应的业务接口并返回格式化结果。
    目前支持的工具：order_query（订单查询）。后续可通过注册表扩展。
    """
    from askflow.agent.tools import execute_tool

    intent_label = state.intent.label if state.intent else "order_query"

    try:
        result = await execute_tool(
            tool_name=intent_label,
            question=state.question,
            user_id=state.user_id,
            conversation_history=state.conversation_history,
            llm_client=llm_client,
        )
        state.tool_result = result
        state.response_tokens = [result.get("display", "查询完成，暂无更多信息。")]
    except Exception as e:
        logger.error("tool_node_error", tool=intent_label, error=str(e))
        state.error = str(e)
        state.response_tokens = [
            "抱歉，业务查询失败，请稍后再试。",
        ]
    return state


async def clarify_node(state: AgentState) -> AgentState:
    """在分类置信度不足时，要求用户补充信息。"""
    state.response_tokens = [
        "我不太确定您的需求，",
        "能否请您提供更多细节以便我更好地帮助您？",
    ]
    return state


_FALLBACK_ROUTES: dict[str, str] = {
    "faq": "rag",
    "product": "rag",
    "order_query": "tool",
    "fault_report": "ticket",
    "complaint": "ticket",
    "handoff": "handoff",
}

VALID_ROUTES = {"rag", "ticket", "handoff", "clarify", "tool"}


def route_by_intent(
    state: AgentState,
    route_map: dict[str, str] | None = None,
) -> str:
    """把意图标签解析为可执行节点名，并在异常配置下回退到安全默认值。"""
    if not state.intent:
        return "rag"
    if state.needs_clarification and state.intent.confidence < 0.5:
        return "clarify"

    label = state.intent.label
    # 数据库中的动态配置优先，没有配置时再使用内置映射。
    mapping = route_map if route_map else _FALLBACK_ROUTES
    target = mapping.get(label, "rag")
    if target not in VALID_ROUTES:
        logger.warning("invalid_route_target", label=label, target=target)
        return "rag"
    return target
