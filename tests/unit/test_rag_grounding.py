"""rag/grounding.py 单元测试：跨通道归一化 + 拒答判定 + harness trace 记录。

对应 plan-docs/honest-rag/01：RetrievalResult.score 三条通道量纲不同，
grounding 必须按通道归一化后再比阈值，任何原始分直接比阈值都是错的。
"""

from __future__ import annotations

import pytest

from askflow.rag.grounding import (
    BM25_MIDPOINT,
    FUSED_LOOKBACK,
    GROUNDED_CONFIDENCE_THRESHOLD,
    WEAK_RETRIEVAL_REFUSAL_FLAG,
    assess_grounding,
    record_grounding_trace,
)
from askflow.rag.retriever import RetrievalResult


def make_result(score: float, source: str, raw_scores: dict | None = None) -> RetrievalResult:
    return RetrievalResult(
        id=f"{source}-{score}",
        document="chunk text",
        metadata={"title": "Doc"},
        score=score,
        source=source,
        raw_scores=raw_scores or {},
    )


class TestAssessGroundingEmpty:
    def test_empty_results_refuse_unconditionally(self):
        assessment = assess_grounding([])

        assert assessment.confidence == 0.0
        assert assessment.grounded is False
        assert assessment.channel == "empty"
        assert assessment.top_score == 0.0


class TestAssessGroundingVector:
    def test_vector_above_threshold_is_grounded(self):
        assessment = assess_grounding([make_result(0.82, "vector")])

        assert assessment.grounded is True
        assert assessment.confidence == pytest.approx(0.82)
        assert assessment.channel == "vector"
        assert assessment.top_score == pytest.approx(0.82)

    def test_vector_below_threshold_refuses(self):
        assessment = assess_grounding(
            [make_result(GROUNDED_CONFIDENCE_THRESHOLD - 0.01, "vector")]
        )

        assert assessment.grounded is False

    def test_vector_score_clamped_into_unit_range(self):
        # 距离可能为负（超相似）或超 1，防御性夹紧。
        assert assess_grounding([make_result(1.4, "vector")]).confidence == 1.0
        assert assess_grounding([make_result(-0.2, "vector")]).confidence == 0.0


class TestAssessGroundingBM25:
    def test_low_raw_score_maps_near_zero_and_refuses(self):
        assessment = assess_grounding([make_result(0.5, "bm25")])

        assert assessment.confidence < 0.2
        assert assessment.grounded is False

    def test_high_raw_score_maps_near_one_and_grounds(self):
        assessment = assess_grounding([make_result(30.0, "bm25")])

        assert assessment.confidence > 0.95
        assert assessment.grounded is True

    def test_midpoint_maps_to_half(self):
        assessment = assess_grounding([make_result(BM25_MIDPOINT, "bm25")])

        assert assessment.confidence == pytest.approx(0.5)


class TestAssessGroundingFused:
    def test_uses_max_vector_raw_score_within_lookback(self):
        results = [
            make_result(0.0164, "fused", raw_scores={"vector": 0.55, "bm25": 12.0}),
            make_result(0.0150, "fused", raw_scores={"vector": 0.91}),
            make_result(0.0140, "fused", raw_scores={"bm25": 9.0}),
        ]

        assessment = assess_grounding(results)

        assert assessment.confidence == pytest.approx(0.91)
        assert assessment.grounded is True
        assert assessment.channel == "fused"

    def test_vector_hit_outside_lookback_window_is_ignored(self):
        results = [make_result(0.016, "fused", raw_scores={"bm25": 1.0}) for _ in range(FUSED_LOOKBACK)]
        results.append(make_result(0.001, "fused", raw_scores={"vector": 0.99}))

        assessment = assess_grounding(results)

        # 窗口内只有弱 bm25 分——高分 vector 命中在窗口外，不参与判定。
        assert assessment.grounded is False

    def test_falls_back_to_bm25_squash_when_no_vector_survived(self):
        results = [make_result(0.016, "fused", raw_scores={"bm25": 30.0})]

        assessment = assess_grounding(results)

        assert assessment.confidence > 0.95
        assert assessment.grounded is True

    def test_no_raw_scores_at_all_refuses(self):
        results = [make_result(0.016, "fused")]

        assessment = assess_grounding(results)

        assert assessment.confidence == 0.0
        assert assessment.grounded is False


class TestRecordGroundingTrace:
    def test_refusal_appends_flag_and_fields(self):
        trace: dict = {"flags": ["low_confidence"]}
        assessment = assess_grounding([])

        record_grounding_trace(trace, assessment)

        assert trace["flags"] == ["low_confidence", WEAK_RETRIEVAL_REFUSAL_FLAG]
        assert trace["retrieval_confidence"] == 0.0
        assert trace["retrieval_channel"] == "empty"

    def test_grounded_records_fields_without_flag(self):
        trace: dict = {}
        assessment = assess_grounding([make_result(0.9, "vector")])

        record_grounding_trace(trace, assessment)

        assert WEAK_RETRIEVAL_REFUSAL_FLAG not in trace["flags"]
        assert trace["retrieval_confidence"] == pytest.approx(0.9)
        assert trace["retrieval_channel"] == "vector"

    def test_flag_not_duplicated_on_repeat_recording(self):
        trace: dict = {}
        assessment = assess_grounding([])

        record_grounding_trace(trace, assessment)
        record_grounding_trace(trace, assessment)

        assert trace["flags"].count(WEAK_RETRIEVAL_REFUSAL_FLAG) == 1
