"""回答置信度（plan-docs/honest-rag/03）。

一个公式、一个家：score = RETRIEVAL_WEIGHT × 检索置信度 + VERIFY_WEIGHT × 自检通过率，
服务端直接分档（high/medium/low），REST 与 WS 消费同一个对象，前端不再复算阈值。
注意与意图置信度（messages.confidence 列）是两个概念——见决策 D8。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from askflow.rag.grounding import WEAK_RETRIEVAL_REFUSAL_FLAG
from askflow.rag.verifier import VERDICT_SKIPPED

RETRIEVAL_WEIGHT = 0.6
VERIFY_WEIGHT = 0.4  # 与 RETRIEVAL_WEIGHT 之和必须为 1.0
HIGH_CONFIDENCE_THRESHOLD = 0.75
MEDIUM_CONFIDENCE_THRESHOLD = 0.5

BAND_HIGH = "high"
BAND_MEDIUM = "medium"
BAND_LOW = "low"


@dataclass(frozen=True)
class AnswerConfidence:
    """随 message_end 下发并持久化到 messages.extra.answer_confidence。"""

    score: float  # 0..1
    band: str  # "high" | "medium" | "low"
    retrieval: float  # 输入：slice 01 的 retrieval_confidence
    verify_pass_rate: float | None  # 输入：supported/total；自检跳过时为 None（前端标注"未自检"）

    def to_payload(self) -> dict:
        return asdict(self)


def compute_answer_confidence(
    harness_trace: dict[str, Any] | None,
    verification: dict[str, Any] | None,
) -> AnswerConfidence | None:
    """非 rag 轮次（trace 无 retrieval_confidence）返回 None——工单/转接回复上不该有置信度徽章。"""
    trace = harness_trace or {}
    retrieval = trace.get("retrieval_confidence")
    if retrieval is None:
        return None

    if WEAK_RETRIEVAL_REFUSAL_FLAG in trace.get("flags", []):
        # 拒答轮次：置信度就是"低"，这是诚实的下限。
        return AnswerConfidence(
            score=retrieval, band=BAND_LOW, retrieval=retrieval, verify_pass_rate=None
        )

    pass_rate = _verify_pass_rate(verification)
    if pass_rate is None:
        # 自检没跑成：只用检索分，绝不让权重"虚增"一个半检查的答案。
        score = retrieval
    else:
        score = RETRIEVAL_WEIGHT * retrieval + VERIFY_WEIGHT * pass_rate

    return AnswerConfidence(
        score=round(score, 4),
        band=_band(score),
        retrieval=retrieval,
        verify_pass_rate=pass_rate,
    )


def _verify_pass_rate(verification: dict[str, Any] | None) -> float | None:
    if not verification or not verification.get("checked"):
        return None
    if verification.get("verdict") == VERDICT_SKIPPED:
        return None
    total = verification.get("total") or 0
    if total <= 0:
        return None
    return verification.get("supported", 0) / total


def _band(score: float) -> str:
    if score >= HIGH_CONFIDENCE_THRESHOLD:
        return BAND_HIGH
    if score >= MEDIUM_CONFIDENCE_THRESHOLD:
        return BAND_MEDIUM
    return BAND_LOW
