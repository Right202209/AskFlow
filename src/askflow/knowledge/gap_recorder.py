"""知识缺口雷达的信号捕获与去重写入（plan-docs/knowledge-loop/01）。

机器人"没答上来"的五类信号（clarify / RAG 拒答 / 低检索置信 / 转人工 / 差评）在这里
统一做 归一化 → 哈希 → upsert 到 knowledge_gaps。所有公开入口都是 best-effort：
radar 故障最多丢一条信号，绝不允许把异常抛回聊天主流程（初始约束 #1）。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from askflow.agent.harness import CognitiveHarnessPolicy
from askflow.core.logging import get_logger
from askflow.models.message import Message
from askflow.rag.grounding import REFUSAL_RESPONSE, WEAK_RETRIEVAL_REFUSAL_FLAG
from askflow.rag.prompt_builder import NO_RESULTS_REFUSAL
from askflow.repositories.knowledge_gap_repo import KnowledgeGapRepo
from askflow.repositories.message_repo import MessageRepo

logger = get_logger(__name__)

# --- 常量（plan-docs/knowledge-loop/01 §Constants）---
# RRF 融合分是排名的函数（k=60 时单路 rank-1 ≈ 1/61 ≈ 0.0164）；低于单路 rank-1 的一半
# 视为"弱共识命中"。仅在 harness trace 缺少 retrieval_confidence 时作为兜底口径（D2）。
LOW_RRF_SCORE_THRESHOLD = 0.008
# honest-rag 之后的首选口径：grounding 归一化置信度落在 [拒答线 0.35, 本阈值) 之间
# ⇒ "答了但证据偏弱"，记 low_retrieval_score 信号。
LOW_RETRIEVAL_CONFIDENCE_THRESHOLD = 0.5
# 归一化问题截断长度（< harness 的 2000 字输入上限）。
MAX_GAP_QUESTION_CHARS = 500

SIGNAL_CLARIFY = "clarify"
SIGNAL_RAG_REFUSAL = "rag_refusal"
SIGNAL_LOW_RETRIEVAL_SCORE = "low_retrieval_score"
SIGNAL_HANDOFF = "handoff"
SIGNAL_NEGATIVE_FEEDBACK = "negative_feedback"
GAP_SIGNAL_KINDS = (
    SIGNAL_CLARIFY,
    SIGNAL_RAG_REFUSAL,
    SIGNAL_LOW_RETRIEVAL_SCORE,
    SIGNAL_HANDOFF,
    SIGNAL_NEGATIVE_FEEDBACK,
)

# 相似缺口推荐（read-time only，D5）与列表页默认分页。
RELATED_GAPS_CANDIDATES = 50
RELATED_GAPS_TOP_N = 5
DEFAULT_GAPS_PAGE_SIZE = 20

# feedback.rating 的差评值（DB CHECK 约束 rating IN (-1, 1)）。
NEGATIVE_FEEDBACK_RATING = -1

_ROUTE_RAG = "rag"
_ROUTE_CLARIFY = "clarify"

_WHITESPACE_RE = re.compile(r"\s+")

# 拒答识别是常量集合比对，不是子串启发式（D3）。三条固定拒答文案：
# 检索零命中（prompt_builder）、证据不足拒答（grounding）、harness 空响应兜底。
_REFUSAL_TEXTS = frozenset(
    {
        NO_RESULTS_REFUSAL,
        REFUSAL_RESPONSE,
        CognitiveHarnessPolicy().fallback_response,
    }
)


@dataclass(frozen=True)
class GapSignal:
    """一次待记录的缺口信号。"""

    kind: str
    question: str
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    intent: str | None = None


@dataclass(frozen=True)
class TurnSignalContext:
    """从一轮 chat 交互提取信号所需的最小上下文。

    与 chat.service.AgentTurn 解耦成独立 dataclass，避免 knowledge → chat 的循环导入。
    """

    question: str
    response_text: str
    sources: list
    harness_trace: dict
    should_handoff: bool
    intent: str | None
    conversation_id: uuid.UUID | None
    message_id: uuid.UUID | None


def normalize_question(question: str) -> str:
    """NFKC → 小写 → 去首尾空白 → 折叠连续空白 → 截断，让同义写法哈希到同一条缺口。"""
    normalized = unicodedata.normalize("NFKC", question or "").lower().strip()
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized[:MAX_GAP_QUESTION_CHARS]


def hash_question(question_norm: str) -> str:
    return hashlib.sha256(question_norm.encode("utf-8")).hexdigest()


async def record_gap(db: AsyncSession, signal: GapSignal) -> None:
    """best-effort 落库：任何异常只记 warning，绝不向上抛——radar 不能弄丢用户消息。"""
    try:
        question_norm = normalize_question(signal.question)
        if not question_norm or signal.kind not in GAP_SIGNAL_KINDS:
            return
        await KnowledgeGapRepo(db).record(
            kind=signal.kind,
            question=signal.question,
            question_norm=question_norm,
            question_hash=hash_question(question_norm),
            conversation_id=signal.conversation_id,
            message_id=signal.message_id,
            intent=signal.intent,
        )
    except Exception as exc:
        logger.warning("gap_record_failed", kind=signal.kind, error=str(exc))


async def maybe_record_gap_from_turn(db: AsyncSession, ctx: TurnSignalContext) -> None:
    """chat 主流程的唯一挂点：识别本轮是否命中失败信号，命中则记一条缺口。"""
    try:
        kind = _detect_signal_kind(ctx)
    except Exception as exc:
        logger.warning("gap_signal_detect_failed", error=str(exc))
        return
    if kind is None:
        return
    await record_gap(
        db,
        GapSignal(
            kind=kind,
            question=ctx.question,
            conversation_id=ctx.conversation_id,
            message_id=ctx.message_id,
            intent=ctx.intent,
        ),
    )


async def record_negative_feedback_gap(
    db: AsyncSession,
    *,
    message: Message,
    rating: int,
) -> None:
    """差评钩子（D4）：rating=-1 时把被打分消息之前的那条用户提问记为缺口。"""
    if rating != NEGATIVE_FEEDBACK_RATING:
        return
    try:
        question_msg = await MessageRepo(db).get_preceding_user_message(message.id)
    except Exception as exc:
        logger.warning("gap_feedback_lookup_failed", error=str(exc))
        return
    if question_msg is None:
        return
    await record_gap(
        db,
        GapSignal(
            kind=SIGNAL_NEGATIVE_FEEDBACK,
            question=question_msg.content,
            conversation_id=message.conversation_id,
            message_id=message.id,
            intent=message.intent,
        ),
    )


def _detect_signal_kind(ctx: TurnSignalContext) -> str | None:
    """一轮最多归入一类信号：clarify → rag 系 → handoff，互斥路由天然不冲突。"""
    trace = ctx.harness_trace or {}
    route = trace.get("route")
    if route == _ROUTE_CLARIFY:
        return SIGNAL_CLARIFY
    if route == _ROUTE_RAG:
        return _detect_rag_signal(ctx, trace)
    if ctx.should_handoff:
        return SIGNAL_HANDOFF
    return None


def _detect_rag_signal(ctx: TurnSignalContext, trace: dict[str, Any]) -> str | None:
    if WEAK_RETRIEVAL_REFUSAL_FLAG in trace.get("flags", []):
        return SIGNAL_RAG_REFUSAL
    if not ctx.sources or ctx.response_text.strip() in _REFUSAL_TEXTS:
        return SIGNAL_RAG_REFUSAL

    confidence = trace.get("retrieval_confidence")
    if confidence is not None:
        weak = float(confidence) < LOW_RETRIEVAL_CONFIDENCE_THRESHOLD
        return SIGNAL_LOW_RETRIEVAL_SCORE if weak else None

    top_score = max((float(s.get("score", 0.0)) for s in ctx.sources), default=0.0)
    return SIGNAL_LOW_RETRIEVAL_SCORE if top_score < LOW_RRF_SCORE_THRESHOLD else None
