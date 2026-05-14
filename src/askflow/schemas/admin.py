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
    # 新质量信号：harness 兜底比例、截断比例、7 天 thumbs-down 占比。
    # 替换空洞的 avg_confidence 作为"线上是不是变差了"的判定依据。
    harness_fallback_rate: float = 0.0
    harness_truncate_rate: float = 0.0
    thumbs_down_rate_7d: float = 0.0
    feedback_total_7d: int = 0
