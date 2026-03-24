from __future__ import annotations

from askflow.agent.intent_classifier import IntentClassifier
from askflow.agent.nodes import route_by_intent
from askflow.agent.state import AgentState
from askflow.core.logging import get_logger
from askflow.rag.service import RAGService

logger = get_logger(__name__)


class AgentGraph:
    def __init__(self, classifier: IntentClassifier, rag_service: RAGService) -> None:
        self._classifier = classifier
        self._rag_service = rag_service

    async def run(
        self,
        state: AgentState,
        route_map: dict[str, str] | None = None,
    ) -> AgentState:
        from askflow.agent.nodes import (
            classify_node,
            clarify_node,
            handoff_node,
            rag_node,
            ticket_node,
        )

        if not state.intent:
            state = await classify_node(state, self._classifier)

        route = route_by_intent(state, route_map=route_map)

        logger.info("agent_routing", route=route, intent=state.intent.label if state.intent else None)

        if route == "rag":
            state = await rag_node(state, self._rag_service)
        elif route == "ticket":
            state = await ticket_node(state)
        elif route == "handoff":
            state = await handoff_node(state)
        elif route == "clarify":
            state = await clarify_node(state)

        return state
