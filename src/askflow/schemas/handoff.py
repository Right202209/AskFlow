from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from askflow.models.handoff import HandoffStatus
from askflow.schemas.message import MessageResponse


class HandoffSessionResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: str
    summary: str
    payload: dict
    assignee: str | None
    created_at: datetime
    claimed_at: datetime | None
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class HandoffDetailResponse(BaseModel):
    """收件箱详情：session + 完整会话历史（MessageRepo，非 Redis 截断历史）。"""

    session: HandoffSessionResponse
    messages: list[MessageResponse]


class HandoffReplyRequest(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reply content cannot be empty")
        return value


class HandoffResolveRequest(BaseModel):
    """关闭会话：resolved（问题已解决）或 returned（交还 AI）；默认暖回流到 active。"""

    status: HandoffStatus = HandoffStatus.resolved
    close_conversation: bool = False

    @field_validator("status")
    @classmethod
    def closing_status_only(cls, value: HandoffStatus) -> HandoffStatus:
        if value not in (HandoffStatus.resolved, HandoffStatus.returned):
            raise ValueError("status must be 'resolved' or 'returned'")
        return value
