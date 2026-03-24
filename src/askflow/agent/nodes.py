from __future__ import annotations

from collections.abc import AsyncIterator

from askflow.agent.intent_classifier import IntentClassifier
from askflow.agent.state import AgentState
from askflow.core.logging import get_logger
from askflow.rag.service import RAGService
from askflow.schemas.intent import IntentResult

logger = get_logger(__name__)


async def classify_node(state: AgentState, classifier: IntentClassifier) -> AgentState:
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
    return await rag_service.query_stream(
        question=state.question,
        conversation_history=state.conversation_history,
    )


async def ticket_node(state: AgentState) -> AgentState:
    state.response_tokens = [
        "I'll create a ticket for this issue. ",
        "A support agent will follow up with you shortly.",
    ]
    return state


async def handoff_node(state: AgentState) -> AgentState:
    state.should_handoff = True
    state.response_tokens = [
        "I'm transferring you to a human agent. ",
        "Please wait a moment while I connect you.",
    ]
    return state


async def clarify_node(state: AgentState) -> AgentState:
    state.response_tokens = [
        "I'm not entirely sure what you need. ",
        "Could you please provide more details about your question?",
    ]
    return state


_FALLBACK_ROUTES: dict[str, str] = {
    "faq": "rag",
    "product": "rag",
    "order_query": "rag",
    "fault_report": "ticket",
    "complaint": "ticket",
    "handoff": "handoff",
}

VALID_ROUTES = {"rag", "ticket", "handoff", "clarify"}


def route_by_intent(
    state: AgentState,
    route_map: dict[str, str] | None = None,
) -> str:
    if not state.intent:
        return "rag"
    if state.needs_clarification and state.intent.confidence < 0.5:
        return "clarify"

    label = state.intent.label
    mapping = route_map if route_map else _FALLBACK_ROUTES
    target = mapping.get(label, "rag")
    if target not in VALID_ROUTES:
        logger.warning("invalid_route_target", label=label, target=target)
        return "rag"
    return target
