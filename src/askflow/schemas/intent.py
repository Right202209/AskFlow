from __future__ import annotations

import uuid

from pydantic import BaseModel


class IntentResult(BaseModel):
    label: str
    confidence: float
    needs_clarification: bool = False


class IntentConfigCreate(BaseModel):
    name: str
    display_name: str
    description: str | None = None
    route_target: str
    keywords: list[str] | None = None
    examples: list[str] | None = None
    confidence_threshold: float = 0.7
    is_active: bool = True
    priority: int = 0


class IntentConfigUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    route_target: str | None = None
    keywords: list[str] | None = None
    examples: list[str] | None = None
    confidence_threshold: float | None = None
    is_active: bool | None = None
    priority: int | None = None


class IntentConfigResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    description: str | None
    route_target: str
    keywords: dict | None
    examples: dict | None
    confidence_threshold: float
    is_active: bool
    priority: int

    model_config = {"from_attributes": True}
