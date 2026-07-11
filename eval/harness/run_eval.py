"""评估 CLI 入口：python -m eval.harness.run_eval --suite all --k 5 --judge off。

流程：确定性护栏 → 加载 golden（解析 corpus: 引用）→ 装配 RAG 半边 →
并发跑 case → 汇总指标 → 追加时间戳报告 → 打印失败清单与 summary。
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

import eval.harness._bootstrap  # noqa: F401  # sys.path 兜底，必须最先导入

from eval.harness import metrics
from eval.harness.config import EVAL_TOP_K
from eval.harness.report import git_sha, write_report
from eval.harness.runner import build_stack, judge_meta, run_all
from eval.harness.schema import load_corpus_map, load_golden_cases, resolve_corpus_refs
from eval.harness.seed_corpus import require_local_provider


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AskFlow offline eval")
    parser.add_argument("--suite", default="all", help="golden suite name or 'all'")
    parser.add_argument("--k", type=int, default=EVAL_TOP_K, help="retrieval top-k")
    parser.add_argument("--judge", choices=("off", "llm"), default="off")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict:
    from askflow.config import settings
    from askflow.rag.llm_client import llm_client

    corpus_map = load_corpus_map()
    cases = resolve_corpus_refs(load_golden_cases(args.suite), corpus_map)
    print(f"loaded {len(cases)} golden cases (suite={args.suite})")

    stack = build_stack()
    try:
        results = await run_all(stack, cases, judge=args.judge == "llm", top_k=args.k)
    finally:
        await llm_client.close()

    summary = metrics.summarize(results)
    payload = {
        "run_id": uuid.uuid4().hex,
        "git_sha": git_sha(),
        "suite": args.suite,
        "k": args.k,
        "provider_config": {
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
            "llm_model": settings.llm_model,
            **judge_meta(args.judge == "llm"),
        },
        "per_case": [metrics.case_payload(r) for r in results],
        "summary": summary,
    }
    report_path = write_report(payload)

    for line in metrics.failures(results):
        print(f"FAIL {line}")
    print(f"\nreport written to {report_path}")
    for key, value in summary.items():
        rendered = f"{value:.3f}" if isinstance(value, float) else value
        print(f"  {key}: {rendered}")
    return summary


def main() -> None:
    args = parse_args()
    require_local_provider()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
