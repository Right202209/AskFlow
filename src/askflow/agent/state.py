from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from askflow.schemas.intent import IntentResult


@dataclass
class AgentState:
    question: str = ""
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    user_id: str = ""
    conversation_id: str = ""
    intent: IntentResult | None = None
    response_tokens: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    ticket_id: str | None = None
    error: str | None = None
    should_handoff: bool = False
    needs_clarification: bool = False
