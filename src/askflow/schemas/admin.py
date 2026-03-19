from __future__ import annotations

from pydantic import BaseModel


class AnalyticsResponse(BaseModel):
    total_conversations: int = 0
    total_messages: int = 0
    total_tickets: int = 0
    total_documents: int = 0
    tickets_by_status: dict[str, int] = {}
    intent_distribution: dict[str, int] = {}
    avg_confidence: float = 0.0
