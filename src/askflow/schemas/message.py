from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    intent: str | None = None
    # 注意：confidence 是"意图置信度"；回答置信度在 extra.answer_confidence（决策 D8）。
    confidence: float | None = None
    sources: dict | None = None
    # messages.metadata 透传（harness_trace / verification / answer_confidence），
    # 让历史回放与 WS 实时帧渲染同一份徽章。
    extra: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
