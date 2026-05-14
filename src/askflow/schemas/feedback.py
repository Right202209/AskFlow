from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class FeedbackCreate(BaseModel):
    # rating: 1 = thumbs up, -1 = thumbs down。中立反馈不收集——要么改善要么删除。
    rating: Literal[-1, 1]
    comment: str | None = None


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    user_id: uuid.UUID
    rating: int
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
