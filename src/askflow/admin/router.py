from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.admin.analytics import get_analytics
from askflow.admin.service import AdminService
from askflow.core.auth import get_current_user, require_role
from askflow.core.database import get_db
from askflow.core.security import create_access_token, hash_password, verify_password
from askflow.models.user import User, UserRole
from askflow.repositories.user_repo import UserRepo
from askflow.schemas.admin import AnalyticsResponse
from askflow.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from askflow.schemas.common import APIResponse
from askflow.schemas.document import DocumentResponse
from askflow.schemas.intent import IntentConfigCreate, IntentConfigResponse, IntentConfigUpdate

router = APIRouter()


@router.post("/auth/register", response_model=APIResponse[UserResponse])
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    repo = UserRepo(db)
    existing = await repo.get_by_username(body.username)
    if existing:
        return APIResponse(success=False, error="Username already exists")
    user = await repo.create(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    return APIResponse(data=UserResponse.model_validate(user))


@router.post("/auth/login", response_model=APIResponse[TokenResponse])
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    repo = UserRepo(db)
    user = await repo.get_by_username(body.username)
    if not user or not verify_password(body.password, user.hashed_password):
        return APIResponse(success=False, error="Invalid credentials")
    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return APIResponse(data=TokenResponse(access_token=token))


@router.get("/documents", response_model=APIResponse[list[DocumentResponse]])
async def list_documents(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    service = AdminService(db)
    docs = await service.list_documents(status=status)
    return APIResponse(data=[DocumentResponse.model_validate(d) for d in docs])


@router.delete("/documents/{doc_id}", response_model=APIResponse)
async def delete_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    service = AdminService(db)
    deleted = await service.delete_document(doc_id)
    if not deleted:
        return APIResponse(success=False, error="Document not found")
    from askflow.embedding.embedder import create_embedder
    from askflow.embedding.service import EmbeddingService
    from askflow.rag.vector_store import get_vector_store
    embed_service = EmbeddingService(create_embedder(), get_vector_store())
    await embed_service.delete_document(str(doc_id))
    return APIResponse(data={"deleted": True})


@router.get("/intents", response_model=APIResponse[list[IntentConfigResponse]])
async def list_intents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    service = AdminService(db)
    configs = await service.list_intent_configs()
    return APIResponse(data=[IntentConfigResponse.model_validate(c) for c in configs])


@router.post("/intents", response_model=APIResponse[IntentConfigResponse])
async def create_intent(
    body: IntentConfigCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    service = AdminService(db)
    config = await service.create_intent_config(**body.model_dump())
    return APIResponse(data=IntentConfigResponse.model_validate(config))


@router.put("/intents/{config_id}", response_model=APIResponse[IntentConfigResponse])
async def update_intent(
    config_id: uuid.UUID,
    body: IntentConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    service = AdminService(db)
    config = await service.update_intent_config(
        config_id, **body.model_dump(exclude_unset=True)
    )
    if not config:
        return APIResponse(success=False, error="Intent config not found")
    return APIResponse(data=IntentConfigResponse.model_validate(config))


@router.get("/analytics", response_model=APIResponse[AnalyticsResponse])
async def analytics(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    data = await get_analytics(db)
    return APIResponse(data=data)
