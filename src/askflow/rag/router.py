from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from askflow.core.auth import get_current_user
from askflow.embedding.embedder import create_embedder
from askflow.models.user import User
from askflow.rag.filters import RetrievalFilters
from askflow.rag.llm_client import llm_client
from askflow.rag.reranker import Reranker
from askflow.rag.retriever import HybridRetriever
from askflow.rag.service import RAGService
from askflow.rag.vector_store import get_vector_store
from askflow.schemas.common import APIResponse

router = APIRouter()


class RAGQueryFilters(BaseModel):
    """PRD §4.1 要求的按来源 / 时间 / 标签过滤的入参结构。"""

    sources: list[str] | None = None
    doc_ids: list[str] | None = None
    indexed_after: datetime | None = None
    indexed_before: datetime | None = None
    tags: list[str] | None = Field(
        default=None,
        description="预留字段，目前索引时未绑定 tag 语义，传入会被忽略",
    )


class RAGQuery(BaseModel):
    question: str
    conversation_history: list[dict[str, str]] | None = None
    top_k: int = 5
    filters: RAGQueryFilters | None = None


class RAGAnswer(BaseModel):
    answer: str
    sources: list[dict]


def get_rag_service() -> RAGService:
    embedder = create_embedder()
    vector_store = get_vector_store()
    retriever = HybridRetriever(embedder, vector_store)
    reranker = Reranker()
    return RAGService(retriever, reranker, llm_client)


def _to_retrieval_filters(payload: RAGQueryFilters | None) -> RetrievalFilters | None:
    if payload is None:
        return None
    filters = RetrievalFilters(
        sources=payload.sources,
        doc_ids=payload.doc_ids,
        indexed_after=payload.indexed_after,
        indexed_before=payload.indexed_before,
        tags=payload.tags,
    )
    return None if filters.is_empty() and not filters.tags else filters


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
        filters=_to_retrieval_filters(body.filters),
    )
    return APIResponse(data=RAGAnswer(answer=result.answer, sources=result.sources))
