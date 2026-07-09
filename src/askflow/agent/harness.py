from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from askflow.agent.state import AgentState
from askflow.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class CognitiveHarnessPolicy:
    """Deterministic operating rules around the agent graph."""

    version: str = "askflow-cognitive-harness-v1"
    max_question_chars: int = 2000
    max_history_messages: int = 12
    max_history_content_chars: int = 1200
    max_response_chars: int = 8000
    low_confidence_threshold: float = 0.5
    fallback_route: str = "rag"
    allowed_routes: frozenset[str] = frozenset({"rag", "ticket", "handoff", "clarify", "tool"})
    allowed_history_roles: frozenset[str] = frozenset({"user", "assistant"})
    prompt_control_patterns: tuple[str, ...] = (
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"reveal\s+(your\s+)?(system|developer)\s+prompt",
        r"show\s+(me\s+)?(your\s+)?(system|developer)\s+prompt",
        r"忽略(之前|以上|所有).*(指令|规则)",
        r"(泄露|显示|输出).*(系统提示|系统提示词|开发者消息)",
    )
    empty_input_response: str = "请先描述您的问题，我会帮您查询、报修或转接人工客服。"
    too_long_response: str = "您的问题内容过长，请拆成更短的问题后再发送。"
    prompt_control_response: str = (
        "我不能处理绕过系统约束或获取内部提示的请求。请直接描述需要查询、报修或转人工的问题。"
    )
    fallback_response: str = "抱歉，暂时无法生成有效回复，请稍后再试。"
    response_truncated_notice: str = "\n回复内容较长，已根据服务输出预算截断。"


@dataclass
class HarnessDecision:
    action: str
    reason: str
    state: AgentState
    route: str | None = None
    response_tokens: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


class CognitiveHarness:
    """Applies the cognitive contract for a controllable customer-service agent."""

    def __init__(self, policy: CognitiveHarnessPolicy | None = None) -> None:
        self.policy = policy or CognitiveHarnessPolicy()
        self._prompt_control_re = tuple(
            re.compile(pattern, re.IGNORECASE) for pattern in self.policy.prompt_control_patterns
        )

    def prepare(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        user_id: str = "",
        conversation_id: str = "",
    ) -> HarnessDecision:
        """Normalize inputs and stop requests that violate deterministic rules."""
        flags: list[str] = []
        normalized_question = (question or "").strip()
        sanitized_history = self._sanitize_history(conversation_history or [], flags)

        state = AgentState(
            question=normalized_question,
            conversation_history=sanitized_history,
            user_id=user_id,
            conversation_id=conversation_id,
            harness_trace=self._base_trace(
                question=normalized_question,
                history=sanitized_history,
                flags=flags,
            ),
        )

        if not normalized_question:
            return self._stop(state, "empty_input", self.policy.empty_input_response, flags)

        if len(normalized_question) > self.policy.max_question_chars:
            flags.append("question_too_long")
            return self._stop(state, "question_too_long", self.policy.too_long_response, flags)

        if self._looks_like_prompt_control(normalized_question):
            flags.append("prompt_control_request")
            return self._stop(
                state,
                "prompt_control_request",
                self.policy.prompt_control_response,
                flags,
            )

        state.harness_trace.update({"action": "continue", "reason": "input_accepted"})
        return HarnessDecision(
            action="continue",
            reason="input_accepted",
            state=state,
            flags=flags,
        )

    def choose_route(self, state: AgentState, candidate_route: str) -> str:
        """Validate the route selected by intent/config and apply policy overrides."""
        route = candidate_route
        reason = "route_accepted"
        flags = list(state.harness_trace.get("flags", []))

        if route not in self.policy.allowed_routes:
            flags.append("route_not_allowed")
            route = self.policy.fallback_route
            reason = "route_fallback_not_allowed"

        if state.intent and state.intent.confidence < self.policy.low_confidence_threshold:
            route = "clarify"
            reason = "route_override_low_confidence"
            if "low_confidence" not in flags:
                flags.append("low_confidence")

        state.route = route
        state.harness_trace.update(
            {
                "action": "route",
                "reason": reason,
                "route": route,
                "candidate_route": candidate_route,
                "intent": state.intent.label if state.intent else None,
                "confidence": state.intent.confidence if state.intent else None,
                "flags": flags,
            }
        )
        logger.info(
            "agent_harness_route",
            route=route,
            candidate_route=candidate_route,
            reason=reason,
            flags=flags,
        )
        return route

    def finalize_state(self, state: AgentState) -> AgentState:
        """Enforce an output contract for non-streaming graph paths."""
        flags = list(state.harness_trace.get("flags", []))

        if not any(token.strip() for token in state.response_tokens):
            state.response_tokens = [self.policy.fallback_response]
            flags.append("empty_response_fallback")

        state.response_tokens, truncated = self._limit_tokens(state.response_tokens)
        if truncated:
            flags.append("response_truncated")

        state.harness_trace.update(
            {
                "action": "complete",
                "reason": "response_ready",
                "response_chars": sum(len(token) for token in state.response_tokens),
                "flags": flags,
            }
        )
        return state

    def wrap_stream(self, stream: AsyncIterator[str]) -> AsyncIterator[str]:
        """Bound streaming output without buffering the full answer."""

        async def _wrapped() -> AsyncIterator[str]:
            emitted = 0
            seen = False
            truncated = False

            async for token in stream:
                if not token:
                    continue
                seen = True
                remaining = self.policy.max_response_chars - emitted
                if remaining <= 0:
                    truncated = True
                    break
                if len(token) > remaining:
                    yield token[:remaining]
                    truncated = True
                    break
                emitted += len(token)
                yield token

            if not seen:
                yield self.policy.fallback_response
            elif truncated:
                yield self.policy.response_truncated_notice

        return _wrapped()

    def _sanitize_history(
        self,
        history: list[dict[str, str]],
        flags: list[str],
    ) -> list[dict[str, str]]:
        if len(history) > self.policy.max_history_messages:
            flags.append("history_trimmed")

        sanitized: list[dict[str, str]] = []
        for item in history[-self.policy.max_history_messages :]:
            role = str(item.get("role", "")).strip().lower()
            content = str(item.get("content", "")).strip()

            if role not in self.policy.allowed_history_roles:
                flags.append("history_role_dropped")
                continue
            if len(content) > self.policy.max_history_content_chars:
                content = content[: self.policy.max_history_content_chars]
                flags.append("history_content_truncated")

            if content:
                sanitized.append({"role": role, "content": content})

        return sanitized

    def _looks_like_prompt_control(self, question: str) -> bool:
        return any(pattern.search(question) for pattern in self._prompt_control_re)

    def _base_trace(
        self,
        question: str,
        history: list[dict[str, str]],
        flags: list[str],
    ) -> dict[str, Any]:
        return {
            "run_id": uuid.uuid4().hex,
            "policy_version": self.policy.version,
            "question_chars": len(question),
            "history_messages": len(history),
            "flags": flags,
        }

    def _stop(
        self,
        state: AgentState,
        reason: str,
        response: str,
        flags: list[str],
    ) -> HarnessDecision:
        state.response_tokens = [response]
        state.harness_trace.update(
            {
                "action": "stop",
                "reason": reason,
                "flags": flags,
            }
        )
        logger.info("agent_harness_stop", reason=reason, flags=flags)
        return HarnessDecision(
            action="stop",
            reason=reason,
            state=state,
            response_tokens=[response],
            flags=flags,
        )

    def _limit_tokens(self, tokens: list[str]) -> tuple[list[str], bool]:
        emitted = 0
        limited: list[str] = []

        for token in tokens:
            remaining = self.policy.max_response_chars - emitted
            if remaining <= 0:
                limited.append(self.policy.response_truncated_notice)
                return limited, True
            if len(token) > remaining:
                limited.append(token[:remaining])
                limited.append(self.policy.response_truncated_notice)
                return limited, True
            limited.append(token)
            emitted += len(token)

        return limited, False
