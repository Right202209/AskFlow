from __future__ import annotations

import uuid

from askflow.agent.intent_classifier import IntentClassifier
from askflow.agent.state import AgentState
from askflow.core.logging import get_logger
from askflow.rag.grounding import record_grounding_trace
from askflow.rag.service import RAGService, RAGStreamResult
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
        result = await rag_service.query_stream(
            question=state.question,
            conversation_history=state.conversation_history,
        )
        record_grounding_trace(state.harness_trace, result.grounding)
        state.sources = result.sources

        async for token in result.token_stream:
            state.response_tokens.append(token)
    except Exception as e:
        logger.error("rag_node_error", error=str(e))
        state.error = str(e)
    return state


async def rag_stream_node(state: AgentState, rag_service: RAGService) -> RAGStreamResult:
    """直接返回 RAG 流结果，适合由上层 WebSocket/HTTP 逐 token 转发。

    检索证据强度（含弱检索拒答 flag）在这里写入 harness trace——
    上层构建 ProcessResult 时 trace 已经携带 retrieval_confidence。
    """
    result = await rag_service.query_stream(
        question=state.question,
        conversation_history=state.conversation_history,
    )
    record_grounding_trace(state.harness_trace, result.grounding)
    return result


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
    handoff_service=None,
) -> AgentState:
    """标记需要人工接管：会话置 transferred，并把摘要+载荷入队到客服收件箱。

    入队（agent/handoff.py::HandoffService.enqueue）失败只记日志——转接状态本身
    已生效，超时清扫与收件箱兜底；绝不因队列故障把用户堵在原地。
    """
    state.should_handoff = True

    if conversation_repo and state.conversation_id:
        try:
            from askflow.models.conversation import ConversationStatus

            conv_uuid = uuid.UUID(state.conversation_id)
            await conversation_repo.update_status(conv_uuid, ConversationStatus.transferred)
            logger.info("conversation_transferred", conversation_id=state.conversation_id)
        except Exception as e:
            logger.error("handoff_transfer_failed", error=str(e))

    if handoff_service is not None and state.conversation_id:
        try:
            await handoff_service.enqueue(state)
        except Exception as e:
            logger.error("handoff_enqueue_failed", error=str(e))

    state.response_tokens = [
        "正在为您转接人工客服，请稍候。",
        "您的问题摘要和对话记录将一并转交给客服人员。",
    ]
    return state


async def tool_node(
    state: AgentState,
    llm_client=None,
    rag_service: RAGService | None = None,
    conversation_repo=None,
) -> AgentState:
    """业务查询工具调用节点。

    通过 LLM 提取查询参数，调用对应的业务接口并返回格式化结果。
    目前支持的工具：order_query（订单查询）、knowledge_search（知识检索）。
    槽位缺失（needs_slot）时经 agent/slots.py 把挂起记录持久化到
    conversations.metadata，成功结果则清档——多轮槽位填充的档案推进都在这里。
    """
    from askflow.agent.slots import sync_pending_after_tool
    from askflow.agent.tools import execute_tool

    intent_label = state.intent.label if state.intent else "order_query"

    try:
        result = await execute_tool(
            tool_name=intent_label,
            question=state.question,
            user_id=state.user_id,
            conversation_history=state.conversation_history,
            llm_client=llm_client,
            rag_service=rag_service,
        )
        state.tool_result = result
        state.response_tokens = [result.get("display", "查询完成，暂无更多信息。")]
        await sync_pending_after_tool(state, result, conversation_repo)
    except Exception as e:
        logger.error("tool_node_error", tool=intent_label, error=str(e))
        state.error = str(e)
        state.response_tokens = [
            "抱歉，业务查询失败，请稍后再试。",
        ]
    return state


# 澄清话术的代码兜底默认值：运行时优先读 DB 模板（core/prompts.py，键 agent.clarify）。
CLARIFY_RESPONSE = "我不太确定您的需求，能否请您提供更多细节以便我更好地帮助您？"


async def clarify_node(state: AgentState) -> AgentState:
    """在分类置信度不足时，要求用户补充信息（文案可经 admin 提示词模板调整）。"""
    from askflow.core.prompts import PROMPT_KEY_AGENT_CLARIFY, get_prompt

    state.response_tokens = [await get_prompt(PROMPT_KEY_AGENT_CLARIFY)]
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
