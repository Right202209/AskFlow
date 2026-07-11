"""评估指标（plan-docs/knowledge-loop/03 §Design 3）——全部是 CaseResult 上的纯函数。

核心指标（hit@k / MRR / 拒答正确率 / 证据覆盖 / 引用落点）不依赖 LLM（D9）；
judged_faithfulness 只在 --judge llm 时有值。fused 分数是排名的函数，
任何指标都不做分数阈值判定——hit@k 是集合成员关系。
"""

from __future__ import annotations

from eval.harness.runner import ANSWER_PREVIEW_CHARS, CaseResult

ANSWERABLE = "answerable"
UNANSWERABLE = "unanswerable"


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _valid(results: list[CaseResult], kind: str) -> list[CaseResult]:
    return [r for r in results if r.case.kind == kind and r.error is None]


def hit_at_k(results: list[CaseResult]) -> float | None:
    """answerable 中「期望文档出现在 top-k 检索 doc_id」的占比。"""
    answerable = _valid(results, ANSWERABLE)
    if not answerable:
        return None
    hits = sum(
        1 for r in answerable if set(r.case.expected_doc_ids) & set(r.retrieved_doc_ids)
    )
    return hits / len(answerable)


def mrr(results: list[CaseResult]) -> float | None:
    """首个期望文档的平均倒数排名——比 hit@k 对排序变化更敏感，用于趋势观测。"""
    answerable = _valid(results, ANSWERABLE)
    reciprocal_ranks: list[float] = []
    for r in answerable:
        rank_value = 0.0
        for rank, doc_id in enumerate(r.retrieved_doc_ids, start=1):
            if doc_id in r.case.expected_doc_ids:
                rank_value = 1.0 / rank
                break
        reciprocal_ranks.append(rank_value)
    return _mean(reciprocal_ranks)


def refusal_correctness(results: list[CaseResult]) -> tuple[float | None, float | None]:
    """分类别报告：unanswerable 应拒答（防幻觉），answerable 不应拒答（防过度拒答）。"""
    unanswerable = _valid(results, UNANSWERABLE)
    answerable = _valid(results, ANSWERABLE)
    refused_right = _mean([1.0 if r.refused else 0.0 for r in unanswerable])
    answered_right = _mean([0.0 if r.refused else 1.0 for r in answerable])
    return refused_right, answered_right


def evidence_coverage(results: list[CaseResult]) -> float | None:
    """答案中命中 expected_answer_evidence 子串（casefold）的占比——廉价的忠实度代理。

    无 evidence 的 case 不计入均值（None ≠ 0）。
    """
    per_case: list[float] = []
    for r in _valid(results, ANSWERABLE):
        evidence = r.case.expected_answer_evidence
        if not evidence or r.refused:
            continue
        answer = r.answer.casefold()
        covered = sum(1 for needle in evidence if needle.casefold() in answer)
        per_case.append(covered / len(evidence))
    return _mean(per_case)


def citation_grounding(results: list[CaseResult]) -> float | None:
    """作答的 answerable 中「引用来源包含 ≥1 期望文档」的占比（按 sources[].doc_id）。"""
    answered = [r for r in _valid(results, ANSWERABLE) if not r.refused]
    if not answered:
        return None
    grounded = sum(
        1 for r in answered if set(r.case.expected_doc_ids) & set(r.source_doc_ids)
    )
    return grounded / len(answered)


def judged_faithfulness(results: list[CaseResult]) -> float | None:
    scores = [r.judge_score for r in results if r.judge_score is not None]
    return _mean(scores)  # type: ignore[arg-type]


def summarize(results: list[CaseResult]) -> dict:
    refused_right, answered_right = refusal_correctness(results)
    errors = [r for r in results if r.error is not None]
    return {
        "cases_total": len(results),
        "cases_errored": len(errors),
        "hit_at_k": hit_at_k(results),
        "mrr": mrr(results),
        "refusal_correctness_unanswerable": refused_right,
        "refusal_correctness_answerable": answered_right,
        "evidence_coverage": evidence_coverage(results),
        "citation_grounding": citation_grounding(results),
        "judged_faithfulness": judged_faithfulness(results),
    }


def case_payload(result: CaseResult) -> dict:
    """单 case 的报告载荷：够定位问题（got vs expected + top 检索标题），不重跑也能修。"""
    return {
        "id": result.case.id,
        "kind": result.case.kind,
        "error": result.error,
        "refused": result.refused,
        "expected_doc_ids": result.case.expected_doc_ids,
        "retrieved_doc_ids": result.retrieved_doc_ids,
        "retrieved_titles": result.retrieved_titles,
        "source_doc_ids": result.source_doc_ids,
        "judge_score": result.judge_score,
        "answer_preview": result.answer[:ANSWER_PREVIEW_CHARS],
    }


def failures(results: list[CaseResult]) -> list[str]:
    """人类可读的失败清单：id + 指标 + got-vs-expected + top-3 检索标题。"""
    lines: list[str] = []
    for r in results:
        problems = _case_problems(r)
        if not problems:
            continue
        top_titles = ", ".join(r.retrieved_titles[:3]) or "-"
        lines.append(f"[{r.case.id}] {'; '.join(problems)} | top3: {top_titles}")
    return lines


def _case_problems(r: CaseResult) -> list[str]:
    if r.error is not None:
        return [f"error: {r.error}"]
    problems: list[str] = []
    if r.case.kind == ANSWERABLE:
        if not set(r.case.expected_doc_ids) & set(r.retrieved_doc_ids):
            problems.append("miss: expected doc not in top-k")
        if r.refused:
            problems.append("over-refusal: answerable case refused")
    elif not r.refused:
        problems.append("hallucination-risk: unanswerable case answered")
    return problems
