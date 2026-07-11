"""评估报告落盘与趋势对比（plan-docs/knowledge-loop/03 §Design 4）。

每次 run 追加 eval/reports/{ISO 时间戳}.json；`python -m eval.harness.report --last 10`
打印每轮核心指标与相邻差值，最新一轮相对上一轮任一核心指标回退超过
EVAL_REGRESSION_TOLERANCE 时以非零码退出（本地 KB 变更后的可选门禁）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import eval.harness._bootstrap  # noqa: F401  # sys.path 兜底，必须最先导入

from eval.harness.config import (
    CORE_METRICS,
    CORPUS_MAP_FILENAME,
    EVAL_REGRESSION_TOLERANCE,
    REPORTS_DIR,
)

DEFAULT_TREND_RUNS = 10
_METRIC_COLUMN_WIDTH = 36


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def write_report(payload: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORTS_DIR / f"{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_reports(last_n: int) -> list[dict]:
    """按文件名（ISO 时间戳）升序取最近 N 份报告；corpus_map.json 不是报告，跳过。"""
    if not REPORTS_DIR.exists():
        return []
    files = sorted(
        p for p in REPORTS_DIR.glob("*.json") if p.name != CORPUS_MAP_FILENAME
    )
    reports = []
    for path in files[-last_n:]:
        try:
            reports.append({"file": path.name, **json.loads(path.read_text(encoding="utf-8"))})
        except (json.JSONDecodeError, OSError):
            continue
    return reports


def _format_metric(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "  -  "


def print_trend(reports: list[dict]) -> None:
    header = "run".ljust(_METRIC_COLUMN_WIDTH) + "  " + "  ".join(
        metric[:14].rjust(14) for metric in CORE_METRICS
    )
    print(header)
    for report in reports:
        summary = report.get("summary", {})
        row = report["file"].removesuffix(".json").ljust(_METRIC_COLUMN_WIDTH)
        cells = "  ".join(
            _format_metric(summary.get(metric)).rjust(14) for metric in CORE_METRICS
        )
        print(f"{row}  {cells}")


def find_regressions(previous: dict, latest: dict) -> list[str]:
    """两轮 summary 的核心指标对比；某指标任一轮缺失（None）则不判定该指标。"""
    problems: list[str] = []
    prev_summary = previous.get("summary", {})
    last_summary = latest.get("summary", {})
    for metric in CORE_METRICS:
        prev_value = prev_summary.get(metric)
        last_value = last_summary.get(metric)
        if prev_value is None or last_value is None:
            continue
        drop = prev_value - last_value
        if drop > EVAL_REGRESSION_TOLERANCE:
            problems.append(
                f"{metric}: {prev_value:.3f} -> {last_value:.3f} "
                f"(drop {drop:.3f} > tolerance {EVAL_REGRESSION_TOLERANCE})"
            )
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="AskFlow eval trend report")
    parser.add_argument("--last", type=int, default=DEFAULT_TREND_RUNS)
    args = parser.parse_args()

    reports = load_reports(args.last)
    if not reports:
        print("no eval reports yet — run `make eval` first")
        return

    print_trend(reports)
    if len(reports) < 2:
        return

    regressions = find_regressions(reports[-2], reports[-1])
    if regressions:
        print("\nREGRESSION vs previous run:")
        for line in regressions:
            print(f"  - {line}")
        sys.exit(1)
    print("\nno regression vs previous run")


if __name__ == "__main__":
    main()
