"""检索证据强度评估——决定"答"还是"诚实拒答"的唯一依据（plan-docs/honest-rag/01）。

RetrievalResult.score 在三条通道上量纲不同：vector = 1 - distance（约 0..1）、
bm25 = 原始无界分、fused = RRF 排名和（上限约 0.016，是排名的函数而非相关性的函数）。
因此置信度必须按通道归一化后再比阈值。所有常量与公式集中在本模块，
禁止在其他文件出现碎片化的阈值判断。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from askflow.rag.retriever import RetrievalResult

# --- 调参旋钮（按 plan-docs/honest-rag/01 的默认值上线；待对种子知识库人工扫参后固化）---
# 低于该归一化置信度 → 拒答。
GROUNDED_CONFIDENCE_THRESHOLD = 0.35
# 命中数下限：零命中无条件拒答。
MIN_GROUNDED_RESULTS = 1
# BM25 logistic 压缩：原始分等于 MIDPOINT 时映射为 0.5，SCALE 控制陡峭度。
BM25_MIDPOINT = 8.0
BM25_SCALE = 4.0
# fused 通道向下检查的命中条数（在其中找底层 vector 原始分）。
FUSED_LOOKBACK = 3
# 拒答时仍展示的弱证据条数——让用户看到"为什么不答"。
REFUSAL_MAX_SOURCES = 2
REFUSAL_RESPONSE = (
    "这个问题我在知识库中没有找到足够可靠的依据，为避免误导就不猜测了。"
    "您可以换个说法再问，或者我可以为您转接人工客服。"
)

# harness trace 词表（AGENTS.md §4.5）。
WEAK_RETRIEVAL_REFUSAL_FLAG = "weak_retrieval_refusal"

CHANNEL_EMPTY = "empty"
CHANNEL_VECTOR = "vector"
CHANNEL_BM25 = "bm25"
CHANNEL_FUSED = "fused"


@dataclass(frozen=True)
class GroundingAssessment:
    """一次检索的证据强度结论，随查询结果与 harness trace 一起向上传递。"""

    confidence: float  # 0..1，跨通道归一化后的置信度
    grounded: bool  # confidence 与命中数同时达标
    top_score: float  # 原始 top 分数，仅用于 trace 观测
    channel: str  # "vector" | "bm25" | "fused" | "empty"


def assess_grounding(results: list[RetrievalResult]) -> GroundingAssessment:
    """按 top 命中所属通道归一化置信度，再统一比对拒答阈值。"""
    if not results:
        return GroundingAssessment(
            confidence=0.0, grounded=False, top_score=0.0, channel=CHANNEL_EMPTY
        )

    top = results[0]
    if top.source == CHANNEL_BM25:
        confidence = _squash_bm25(top.score)
    elif top.source == CHANNEL_FUSED:
        confidence = _fused_confidence(results)
    else:
        # vector 分数本身约 0..1（1 - distance），夹紧后直接使用；未知通道按相同的保守口径处理。
        confidence = _clamp01(top.score)

    grounded = confidence >= GROUNDED_CONFIDENCE_THRESHOLD and len(results) >= MIN_GROUNDED_RESULTS
    return GroundingAssessment(
        confidence=confidence, grounded=grounded, top_score=top.score, channel=top.source
    )


def record_grounding_trace(trace: dict[str, Any], assessment: GroundingAssessment) -> None:
    """把检索置信度写入 harness trace；证据不足时追加拒答 flag（AGENTS.md §4.5）。"""
    flags = list(trace.get("flags", []))
    if not assessment.grounded and WEAK_RETRIEVAL_REFUSAL_FLAG not in flags:
        flags.append(WEAK_RETRIEVAL_REFUSAL_FLAG)
    trace["flags"] = flags
    trace["retrieval_confidence"] = assessment.confidence
    trace["retrieval_channel"] = assessment.channel


def _squash_bm25(raw_score: float) -> float:
    """logistic 压缩：无界的 BM25 原始分 → 0..1。"""
    return 1.0 / (1.0 + math.exp(-(raw_score - BM25_MIDPOINT) / BM25_SCALE))


def _fused_confidence(results: list[RetrievalResult]) -> float:
    """RRF 融合分是排名的函数，不能直接比阈值——回看底层通道的原始分。"""
    lookback = results[:FUSED_LOOKBACK]
    vector_scores = [
        r.raw_scores[CHANNEL_VECTOR] for r in lookback if CHANNEL_VECTOR in r.raw_scores
    ]
    if vector_scores:
        return _clamp01(max(vector_scores))
    bm25_scores = [r.raw_scores[CHANNEL_BM25] for r in lookback if CHANNEL_BM25 in r.raw_scores]
    if bm25_scores:
        return _squash_bm25(max(bm25_scores))
    # 底层通道分数全部缺失（只会出现在手工构造的 fused 结果里）——按无证据处理。
    return 0.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
