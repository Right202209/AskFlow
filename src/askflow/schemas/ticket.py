from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TicketCreate(BaseModel):
    type: str
    title: str
    description: str | None = None
    priority: str = "medium"
    conversation_id: uuid.UUID | None = None
    content: dict | None = None


class TicketUpdate(BaseModel):
    status: str | None = None
    assignee: str | None = None
    priority: str | None = None
    content: dict | None = None


class TicketResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    user_id: uuid.UUID
    type: str
    status: str
    priority: str
    title: str
    description: str | None
    assignee: str | None
    content: dict | None
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}
