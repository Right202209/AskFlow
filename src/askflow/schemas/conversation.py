from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationRename(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class DeleteConversationResponse(BaseModel):
    deleted: bool


class ConversationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
