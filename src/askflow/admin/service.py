from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from askflow.agent.service import invalidate_route_map_cache
from askflow.core.logging import get_logger
from askflow.models.document import DocumentStatus
from askflow.repositories.document_repo import DocumentRepo
from askflow.repositories.intent_config_repo import IntentConfigRepo

logger = get_logger(__name__)


class AdminService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._doc_repo = DocumentRepo(db)
        self._intent_repo = IntentConfigRepo(db)

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
        return config

    async def update_intent_config(self, config_id: uuid.UUID, **kwargs):
        config = await self._intent_repo.update(config_id, **kwargs)
        if config:
            invalidate_route_map_cache()
        return config

    async def delete_intent_config(self, config_id: uuid.UUID) -> bool:
        deleted = await self._intent_repo.delete(config_id)
        if deleted:
            invalidate_route_map_cache()
        return deleted
