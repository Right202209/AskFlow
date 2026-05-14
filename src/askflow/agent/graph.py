from __future__ import annotations

from askflow.agent.intent_classifier import IntentClassifier
from askflow.agent.nodes import route_by_intent
from askflow.agent.state import AgentState
from askflow.core.logging import get_logger
from askflow.rag.service import RAGService
from askflow.repositories.conversation_repo import ConversationRepo
from askflow.ticket.service import TicketService

logger = get_logger(__name__)


class AgentGraph:
    """执行分类后的分支流程，决定助手应该走哪条处理链路。

    构造期只接收无状态的、可单例化的依赖（classifier / RAG）。需要触达 DB 的
    ticket_service 与 conversation_repo 通过 run() 的方法参数注入，避免把每条请求
    都重建一遍整个 RAG 栈。
    """

    def __init__(
        self,
        classifier: IntentClassifier,
        rag_service: RAGService,
    ) -> None:
        self._classifier = classifier
        self._rag_service = rag_service

    async def run(
        self,
        state: AgentState,
        *,
        ticket_service: TicketService | None = None,
        conversation_repo: ConversationRepo | None = None,
        route_map: dict[str, str] | None = None,
    ) -> AgentState:
        """在需要时先分类，再根据路由结果执行对应节点。"""
        from askflow.agent.nodes import (
            classify_node,
            clarify_node,
            handoff_node,
            rag_node,
            ticket_node,
            tool_node,
        )

        if not state.intent:
            state = await classify_node(state, self._classifier)

        route = state.route or route_by_intent(state, route_map=route_map)

        logger.info(
            "agent_routing", route=route, intent=state.intent.label if state.intent else None
        )

        if route == "rag":
            state = await rag_node(state, self._rag_service)
        elif route == "ticket":
            if ticket_service:
                state = await ticket_node(state, ticket_service)
            else:
                state.response_tokens = ["工单服务暂不可用，请联系人工客服。"]
        elif route == "handoff":
            state = await handoff_node(state, conversation_repo)
        elif route == "tool":
            state = await tool_node(state)
        elif route == "clarify":
            state = await clarify_node(state)

        return state
