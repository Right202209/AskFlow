"""golden 集加载与校验（plan-docs/knowledge-loop/03 §Design 1）。

每行一个 JSON 对象；kind ∈ {answerable, unanswerable}，answerable 必须给出
expected_doc_ids。语料引用写作 "corpus:<stem>"，加载时经 corpus_map.json
解析为真实 doc_id，让 golden 集跨全新数据库保持有效。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator

from eval.harness.config import CORPUS_MAP_FILENAME, CORPUS_REF_PREFIX, GOLDEN_DIR, REPORTS_DIR


class GoldenCase(BaseModel):
    id: str
    question: str
    kind: Literal["answerable", "unanswerable"]
    expected_doc_ids: list[str] = []
    expected_answer_evidence: list[str] = []
    filters: dict | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def answerable_needs_docs(self) -> GoldenCase:
        if self.kind == "answerable" and not self.expected_doc_ids:
            raise ValueError(f"answerable case {self.id!r} requires expected_doc_ids")
        if self.kind == "unanswerable" and self.expected_doc_ids:
            raise ValueError(f"unanswerable case {self.id!r} must not list expected_doc_ids")
        return self


def load_suite_files(suite: str) -> list[Path]:
    """suite=all → golden/ 下全部 .jsonl；否则匹配单个 <suite>.jsonl。"""
    if suite == "all":
        files = sorted(GOLDEN_DIR.glob("*.jsonl"))
    else:
        files = [GOLDEN_DIR / f"{suite}.jsonl"]
    missing = [str(f) for f in files if not f.exists()]
    if missing or not files:
        raise FileNotFoundError(f"golden suite not found: {suite} ({missing or 'no files'})")
    return files


def load_golden_cases(suite: str) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    seen_ids: set[str] = set()
    for path in load_suite_files(suite):
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            case = GoldenCase.model_validate(json.loads(line))
            if case.id in seen_ids:
                raise ValueError(f"duplicate golden case id {case.id!r} ({path}:{line_no})")
            seen_ids.add(case.id)
            cases.append(case)
    return cases


def load_corpus_map() -> dict[str, dict]:
    """title→doc_id 映射由 seed_corpus 写出；缺失时提示先跑 make eval-seed。"""
    path = REPORTS_DIR / CORPUS_MAP_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run `make eval-seed` against the local stack first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_corpus_refs(cases: list[GoldenCase], corpus_map: dict[str, dict]) -> list[GoldenCase]:
    """把 expected_doc_ids 里的 corpus:<stem> 引用替换为 seed 时分配的真实 doc_id。"""
    resolved: list[GoldenCase] = []
    for case in cases:
        doc_ids = [_resolve_ref(ref, corpus_map, case.id) for ref in case.expected_doc_ids]
        resolved.append(case.model_copy(update={"expected_doc_ids": doc_ids}))
    return resolved


def _resolve_ref(ref: str, corpus_map: dict[str, dict], case_id: str) -> str:
    if not ref.startswith(CORPUS_REF_PREFIX):
        return ref
    stem = ref.removeprefix(CORPUS_REF_PREFIX)
    entry = corpus_map.get(stem)
    if entry is None:
        raise KeyError(
            f"golden case {case_id!r} references unknown corpus doc {stem!r}; "
            "re-run `make eval-seed` or fix the golden line"
        )
    return str(entry["doc_id"])
