from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from askflow.models.knowledge_gap import GapStatus


class GapResponse(BaseModel):
    id: uuid.UUID
    question: str
    question_norm: str
    status: str
    frequency: int
    signals: dict
    last_intent: str | None
    example_conversation_id: uuid.UUID | None
    example_message_id: uuid.UUID | None
    promoted_doc_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GapUpdate(BaseModel):
    """管理端唯一允许的状态迁移是 open → dismissed；promoted 由 Slice 02 的发布路径独占。"""

    status: GapStatus

    @field_validator("status")
    @classmethod
    def only_dismissed(cls, value: GapStatus) -> GapStatus:
        if value != GapStatus.dismissed:
            raise ValueError("only 'dismissed' is allowed; 'promoted' is set by publishing")
        return value


class RelatedGapResponse(BaseModel):
    """embedding 相似度推荐的相关缺口（read-time only，D5）。"""

    id: uuid.UUID
    question: str
    frequency: int
    similarity: float


class DraftCreate(BaseModel):
    """草稿素材：工单 / 会话转录 / 人工输入，至多一种主素材；synthesize 开启 LLM 草拟。"""

    ticket_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    manual_answer: str | None = None
    synthesize: bool = False

    @model_validator(mode="after")
    def single_material(self) -> DraftCreate:
        provided = [
            value
            for value in (self.ticket_id, self.conversation_id, self.manual_answer)
            if value
        ]
        if len(provided) > 1:
            raise ValueError("provide at most one of ticket_id / conversation_id / manual_answer")
        return self


class DraftUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None


class DraftReview(BaseModel):
    review_note: str | None = None


class DraftResponse(BaseModel):
    id: uuid.UUID
    gap_id: uuid.UUID | None
    question: str
    answer: str
    status: str
    source_ticket_id: uuid.UUID | None
    source_conversation_id: uuid.UUID | None
    synthesis: dict | None
    created_by: uuid.UUID | None
    reviewed_by: uuid.UUID | None
    published_doc_id: uuid.UUID | None
    review_note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
