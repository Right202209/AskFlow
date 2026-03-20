from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator

from askflow.models.ticket import TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    type: str
    title: str
    description: str | None = None
    priority: TicketPriority = TicketPriority.medium
    conversation_id: uuid.UUID | None = None
    content: dict | None = None


class TicketUpdate(BaseModel):
    status: TicketStatus | None = None
    assignee: str | None = None
    priority: TicketPriority | None = None
    content: dict | None = None

    @model_validator(mode="after")
    def validate_nullable_enums(self) -> "TicketUpdate":
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        if "priority" in self.model_fields_set and self.priority is None:
            raise ValueError("priority cannot be null")
        return self


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
