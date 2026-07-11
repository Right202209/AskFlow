"""知识缺口雷达的管理端接口（plan-docs/knowledge-loop/01 §Design 4）。

挂在 /api/v1/admin/gaps 下，独立于 admin/router.py（后者已 172 行，避免继续膨胀）。
读接口 admin/agent 可见，dismiss 写接口 admin 独占。
"""

from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.auth import require_role
from askflow.core.database import get_db
from askflow.core.exceptions import NotFoundError
from askflow.core.logging import get_logger
from askflow.knowledge.draft_service import DraftService, DraftSource
from askflow.knowledge.gap_recorder import (
    DEFAULT_GAPS_PAGE_SIZE,
    RELATED_GAPS_CANDIDATES,
    RELATED_GAPS_TOP_N,
)
from askflow.models.knowledge_gap import GapStatus, KnowledgeGap
from askflow.models.user import User, UserRole
from askflow.rag.llm_client import llm_client
from askflow.repositories.knowledge_gap_repo import KnowledgeGapRepo
from askflow.schemas.common import APIResponse, PaginatedResponse
from askflow.schemas.knowledge import (
    DraftCreate,
    DraftResponse,
    GapResponse,
    GapUpdate,
    RelatedGapResponse,
)

logger = get_logger(__name__)

router = APIRouter()

_MAX_PAGE_SIZE = 100


@router.get("", response_model=PaginatedResponse[GapResponse])
async def list_gaps(
    status: GapStatus = GapStatus.open,
    order: str = Query("frequency"),
    limit: int = Query(DEFAULT_GAPS_PAGE_SIZE, gt=0, le=_MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    repo = KnowledgeGapRepo(db)
    gaps = await repo.list_gaps(status=status, order=order, limit=limit, offset=offset)
    total = await repo.count(status=status)
    return PaginatedResponse(
        data=[GapResponse.model_validate(g) for g in gaps],
        total=total,
        page=offset // limit + 1,
        limit=limit,
    )


@router.get("/{gap_id}", response_model=APIResponse[GapResponse])
async def get_gap(
    gap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    gap = await KnowledgeGapRepo(db).get_by_id(gap_id)
    if gap is None:
        raise NotFoundError("Knowledge gap not found")
    return APIResponse(data=GapResponse.model_validate(gap))


@router.get("/{gap_id}/related", response_model=APIResponse[list[RelatedGapResponse]])
async def get_related_gaps(
    gap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    """embedding 相似度推荐：read-time only，embedder 不可用时返回 []（永不阻塞）。"""
    repo = KnowledgeGapRepo(db)
    gap = await repo.get_by_id(gap_id)
    if gap is None:
        raise NotFoundError("Knowledge gap not found")

    candidates = await repo.list_open_by_frequency(limit=RELATED_GAPS_CANDIDATES)
    peers = [g for g in candidates if g.id != gap.id]
    related = await _rank_related(gap, peers)
    return APIResponse(data=related)


@router.patch("/{gap_id}", response_model=APIResponse[GapResponse])
async def update_gap(
    gap_id: uuid.UUID,
    body: GapUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    repo = KnowledgeGapRepo(db)
    gap = await repo.set_status(gap_id, body.status)
    if gap is None:
        raise NotFoundError("Knowledge gap not found")
    await db.commit()
    return APIResponse(data=GapResponse.model_validate(gap))


@router.post("/{gap_id}/draft", response_model=APIResponse[DraftResponse])
async def create_draft_from_gap(
    gap_id: uuid.UUID,
    body: DraftCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    """把缺口 + 素材草拟为待审知识条目；同一 gap 的并发草拟收敛到一条 pending 草稿。"""
    service = DraftService(db, llm_client)
    draft = await service.create_from_gap(
        gap_id,
        DraftSource(
            ticket_id=body.ticket_id,
            conversation_id=body.conversation_id,
            manual_answer=body.manual_answer,
            synthesize=body.synthesize,
        ),
        user.id,
    )
    await db.commit()
    return APIResponse(data=DraftResponse.model_validate(draft))


async def _rank_related(
    gap: KnowledgeGap,
    peers: list[KnowledgeGap],
) -> list[RelatedGapResponse]:
    if not peers:
        return []
    try:
        from askflow.embedding.embedder import create_embedder

        embedder = create_embedder()
        vectors = await embedder.embed([gap.question_norm, *[p.question_norm for p in peers]])
    except Exception as exc:
        logger.warning("related_gaps_embed_failed", error=str(exc))
        return []

    base_vec = vectors[0]
    scored = [
        (peer, _cosine(base_vec, vectors[i + 1]))
        for i, peer in enumerate(peers)
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [
        RelatedGapResponse(
            id=peer.id,
            question=peer.question,
            frequency=peer.frequency,
            similarity=round(similarity, 4),
        )
        for peer, similarity in scored[:RELATED_GAPS_TOP_N]
    ]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
