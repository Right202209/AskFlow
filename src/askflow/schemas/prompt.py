"""提示词模板 API 契约（ops-platform/01）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from askflow.core.prompts import MAX_PROMPT_CONTENT_CHARS
from askflow.models.prompt import PromptTemplate, PromptVersion


class PromptVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    content: str
    comment: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime


class PromptTemplateResponse(BaseModel):
    """模板 + 当前生效版本内容的扁平视图（列表页与详情页共用）。"""

    id: uuid.UUID
    key: str
    description: str | None = None
    variables: list[str] = Field(default_factory=list)
    is_active: bool
    active_version: int | None = None
    content: str | None = None
    updated_at: datetime

    @classmethod
    def from_pair(
        cls, template: PromptTemplate, version: PromptVersion | None
    ) -> PromptTemplateResponse:
        return cls(
            id=template.id,
            key=template.key,
            description=template.description,
            variables=list(template.variables or []),
            is_active=template.is_active,
            active_version=version.version if version else None,
            content=version.content if version else None,
            updated_at=template.updated_at,
        )


class PromptUpdateRequest(BaseModel):
    """编辑 = 追加新版本并激活；占位符渲染校验在服务层做（需要模板声明的 variables）。"""

    content: str = Field(min_length=1, max_length=MAX_PROMPT_CONTENT_CHARS)
    comment: str | None = None
