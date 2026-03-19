from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentUpload(BaseModel):
    title: str
    source: str | None = None
    tags: list[str] | None = None


class DocumentResponse(BaseModel):
    id: uuid.UUID
    title: str
    source: str | None
    file_path: str | None
    status: str
    chunk_count: int
    tags: dict | None
    created_at: datetime
    indexed_at: datetime | None

    model_config = {"from_attributes": True}
