from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.agent.service import get_agent_service
from askflow.core.auth import get_current_user
from askflow.core.database import get_db
from askflow.models.user import User
from askflow.schemas.common import APIResponse
from askflow.schemas.intent import IntentResult

router = APIRouter()


class ClassifyRequest(BaseModel):
    message: str
    context: list[dict[str, str]] | None = None


@router.post("/classify", response_model=APIResponse[IntentResult])
async def classify_intent(
    body: ClassifyRequest,
    user: User = Depends(get_current_user),
):
    service = get_agent_service()
    result = await service._classifier.classify(body.message, body.context)
    return APIResponse(data=result)
