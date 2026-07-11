from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from askflow.agent.service import invalidate_route_map_cache, publish_route_map_invalidation
from askflow.core.exceptions import NotFoundError, UnprocessableError
from askflow.core.logging import get_logger
from askflow.core.prompts import prompt_cache
from askflow.models.document import DocumentStatus
from askflow.models.prompt import PromptTemplate, PromptVersion
from askflow.repositories.document_repo import DocumentRepo
from askflow.repositories.intent_config_repo import IntentConfigRepo
from askflow.repositories.prompt_repo import PromptRepo

logger = get_logger(__name__)

# 渲染校验用的占位值——只验证 format 能否成功，不关心内容。
_PLACEHOLDER_DUMMY_VALUE = "x"


def validate_prompt_content(content: str, variables: list[str]) -> None:
    """写入前渲染校验（D2）：占位符拼错/花括号不配对直接 422，防止运行时炸掉分类或 RAG。"""
    dummy = {name: _PLACEHOLDER_DUMMY_VALUE for name in variables}
    try:
        content.format(**dummy)
    except (KeyError, IndexError, ValueError) as exc:
        raise UnprocessableError(f"Prompt placeholder validation failed: {exc}") from exc


class AdminService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._doc_repo = DocumentRepo(db)
        self._intent_repo = IntentConfigRepo(db)
        self._prompt_repo = PromptRepo(db)

    async def list_documents(self, status: str | None = None, limit: int = 50, offset: int = 0):
        doc_status = DocumentStatus(status) if status else None
        return await self._doc_repo.list_all(status=doc_status, limit=limit, offset=offset)

    async def delete_document(self, doc_id: uuid.UUID) -> bool:
        return await self._doc_repo.delete(doc_id)

    async def list_intent_configs(self):
        return await self._intent_repo.get_all_active()

    async def create_intent_config(self, **kwargs):
        config = await self._intent_repo.create(**kwargs)
        invalidate_route_map_cache()
        await publish_route_map_invalidation()
        return config

    async def update_intent_config(self, config_id: uuid.UUID, **kwargs):
        config = await self._intent_repo.update(config_id, **kwargs)
        if config:
            invalidate_route_map_cache()
            await publish_route_map_invalidation()
        return config

    async def delete_intent_config(self, config_id: uuid.UUID) -> bool:
        deleted = await self._intent_repo.delete(config_id)
        if deleted:
            invalidate_route_map_cache()
            await publish_route_map_invalidation()
        return deleted

    # --- 提示词模板（ops-platform/01）：每次变更都走 invalidate + publish 双动作 ---

    async def list_prompts(self) -> list[tuple[PromptTemplate, PromptVersion | None]]:
        return await self._prompt_repo.list_with_active_version()

    async def list_prompt_versions(
        self, key: str, *, limit: int, offset: int = 0
    ) -> tuple[list[PromptVersion], int]:
        template = await self._require_template(key)
        versions = await self._prompt_repo.list_versions(template.id, limit=limit, offset=offset)
        total = await self._prompt_repo.count_versions(template.id)
        return versions, total

    async def update_prompt(
        self,
        key: str,
        *,
        content: str,
        comment: str | None,
        user_id: uuid.UUID | None,
    ) -> tuple[PromptTemplate, PromptVersion]:
        """编辑 = 追加新版本 + 指针切换（D2：历史只增不改）。"""
        template = await self._require_template(key)
        validate_prompt_content(content, list(template.variables or []))
        version = await self._prompt_repo.append_version(
            template.id, content=content, created_by=user_id, comment=comment
        )
        await self._prompt_repo.activate_version(template.id, version.id)
        await self._publish_prompt_invalidation()
        logger.info("prompt_updated", key=key, version=version.version)
        return template, version

    async def activate_prompt_version(
        self, key: str, version_number: int
    ) -> tuple[PromptTemplate, PromptVersion]:
        """回滚 = 把 active 指针拨回历史版本，不产生新行。"""
        template = await self._require_template(key)
        version = await self._prompt_repo.get_version(template.id, version_number)
        if version is None:
            raise NotFoundError(f"Prompt version {version_number} not found for '{key}'")
        await self._prompt_repo.activate_version(template.id, version.id)
        await self._publish_prompt_invalidation()
        logger.info("prompt_version_activated", key=key, version=version_number)
        return template, version

    async def _require_template(self, key: str) -> PromptTemplate:
        template = await self._prompt_repo.get_by_key(key)
        if template is None:
            raise NotFoundError(f"Prompt template '{key}' not found")
        return template

    async def _publish_prompt_invalidation(self) -> None:
        prompt_cache.invalidate()
        await prompt_cache.publish_invalidation()
