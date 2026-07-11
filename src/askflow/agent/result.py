from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from askflow.schemas.intent import IntentResult


class ProcessResult:
    """AgentService.process 的返回值，包含流式 token、来源、意图以及副作用元数据。"""

    __slots__ = (
        "token_stream",
        "sources",
        "intent",
        "ticket_data",
        "should_handoff",
        "tool_result",
        "harness_trace",
    )

    def __init__(
        self,
        token_stream: AsyncIterator[str],
        sources: list[dict],
        intent: IntentResult | None,
        ticket_data: dict[str, Any] | None = None,
        should_handoff: bool = False,
        tool_result: dict[str, Any] | None = None,
        harness_trace: dict[str, Any] | None = None,
    ) -> None:
        self.token_stream = token_stream
        self.sources = sources
        self.intent = intent
        self.ticket_data = ticket_data
        self.should_handoff = should_handoff
        self.tool_result = tool_result
        self.harness_trace = harness_trace or {}
