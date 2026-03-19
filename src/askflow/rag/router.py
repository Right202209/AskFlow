from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.auth import get_current_user
from askflow.core.database import get_db
from askflow.embedding.embedder import create_embedder
from askflow.models.user import User
from askflow.rag.llm_client import llm_client
from askflow.rag.reranker import Reranker
from askflow.rag.retriever import HybridRetriever
from askflow.rag.service import RAGService
from askflow.rag.vector_store import get_vector_store
from askflow.schemas.common import APIResponse

router = APIRouter()


class RAGQuery(BaseModel):
    question: str
    conversation_history: list[dict[str, str]] | None = None
    top_k: int = 5


class RAGAnswer(BaseModel):
    answer: str
    sources: list[dict]


def get_rag_service() -> RAGService:
    embedder = create_embedder()
    vector_store = get_vector_store()
    retriever = HybridRetriever(embedder, vector_store)
    reranker = Reranker()
    return RAGService(retriever, reranker, llm_client)


@router.post("/query", response_model=APIResponse[RAGAnswer])
async def rag_query(
    body: RAGQuery,
    user: User = Depends(get_current_user),
):
    service = get_rag_service()
    result = await service.query(
        question=body.question,
        conversation_history=body.conversation_history,
        top_k=body.top_k,
    )
    return APIResponse(data=RAGAnswer(answer=result.answer, sources=result.sources))
