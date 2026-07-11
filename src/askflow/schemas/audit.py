"""审计日志 API 契约（ops-platform/02）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID
    actor_role: str
    action: str
    entity_type: str
    entity_id: uuid.UUID | None = None
    detail: dict | None = None
    trace_id: str | None = None
    created_at: datetime
