# Slice 03 — Offline Evaluation Framework + Golden Test Set

> No dependency on Slices 01/02 (parallelizable); most valuable after them.
> Estimate: ~2 days. **No DB migration, no agent-behavior change.**

## Goal

A versioned golden QA set plus a `make eval` harness that runs
retrieval + answering over the set against a live local stack and scores:

- **retrieval hit@k** — did the expected doc land in the top-k sources?
- **citation faithfulness** — is the answer grounded in the retrieved chunks?
- **refusal correctness** — does the bot refuse what it *should* refuse (and
  not refuse what it can answer)?

…and appends a timestamped report so any KB change (new doc, reindex, chunking
tweak, a Slice-02 publish) is quantified as a trend, not a vibe.

## Current-state anchors

- **No eval exists.** `tests/e2e/` is empty (CLAUDE.md "Testing notes");
  `Makefile:11-56` has no eval target; nothing under the repo measures
  retrieval quality.
- **The two call surfaces to evaluate.** Non-streaming answer path:
  `rag/service.py:40-69` `RAGService.query` (retrieve `top_k*2` → rerank →
  prompt → LLM, LLM-failure fallback at `service.py:62-67`). Retrieval-only:
  `HybridRetriever.retrieve` (`retriever.py:32-61`) returning
  `RetrievalResult` with `metadata` incl. `doc_id` (`embedding/service.py:60-68`
  chunk metadata contract) — hit@k checks `metadata["doc_id"]`, never chunk
  ids (which rotate every reindex: `{doc_id}_g{generation}_c{i}`,
  `embedding/service.py:59`).
- **Refusal strings are deterministic.** Retrieval-empty refusal
  `prompt_builder.py:42-45` (constant `NO_RESULTS_REFUSAL` after Slice 01's
  extraction; if Slice 01 hasn't landed, this slice performs the same
  extraction) and harness fallback `harness.py:40`. Refusal correctness is a
  string/constant comparison plus a "no sources cited" check — no LLM judge
  needed (OVERVIEW D9).
- **Deterministic embeddings are already supported.**
  `EMBEDDING_PROVIDER=local` runs `fastembed` CPU ONNX in-process (CLAUDE.md
  "Runtime services") — eval runs pin this so scores don't drift with a remote
  embedding endpoint.
- **Wiring precedent for standalone scripts.** `scripts/create_user.py` (used
  by `make create-user`, `Makefile:29`) shows the repo's pattern for CLI entry
  points that bootstrap settings/services outside FastAPI.
- **Score semantics.** Fused scores are RRF rank-based (`retriever.py:109-143`)
  — the harness reports them but must never threshold on them for pass/fail;
  hit@k is membership-based.

## Design

### 1. Golden set format (`eval/golden/*.jsonl`, versioned in git — D8)

One JSON object per line; files are named by suite
(`eval/golden/core_faq.jsonl`, `eval/golden/refusals.jsonl`, …) so PRs review
diffs line-by-line:

```json
{"id": "faq-invoice-001",
 "question": "怎么开发票?",
 "kind": "answerable",
 "expected_doc_ids": ["<uuid-of-invoicing-doc>"],
 "expected_answer_evidence": ["电子发票", "订单详情页"],
 "filters": null,
 "notes": "seeded doc docs/seed/invoicing.md"}

{"id": "refusal-weather-001",
 "question": "明天北京天气怎么样?",
 "kind": "unanswerable",
 "expected_doc_ids": [],
 "expected_answer_evidence": [],
 "notes": "out-of-KB; must refuse, not hallucinate"}
```

Schema is validated by `eval/harness/schema.py` (pydantic) at load time —
`kind` ∈ {`answerable`, `unanswerable`}; `answerable` requires non-empty
`expected_doc_ids`. `expected_doc_ids` reference documents created by a
checked-in fixture corpus `eval/corpus/*.md` + `eval/harness/seed_corpus.py`
(uploads via the API / `EmbeddingService`, records the title→doc_id map to
`eval/reports/corpus_map.json`), so the golden set stays valid across fresh
databases. Seeding gaps captured by Slice 01 and entries published by Slice 02
are the intended source of *new* golden lines over time (add the question +
the promoted doc id).

### 2. Harness (`eval/harness/run_eval.py`, package `eval/harness/`)

CLI: `python -m eval.harness.run_eval --suite all --k 5 --judge off`.

Per case, two measurements against the live local stack (docker services +
seeded corpus; `EMBEDDING_PROVIDER=local` enforced at startup — abort with a
clear error if the running config differs, since scores would not be
comparable):

1. **Retrieval:** `HybridRetriever.retrieve(question, top_k=EVAL_TOP_K)` →
   hit@k over `metadata["doc_id"]`, plus MRR for trend sensitivity.
2. **Answer:** `RAGService.query(question, top_k=EVAL_TOP_K)` → refusal
   detection + faithfulness (§3).

Services are constructed once per run with the same wiring the app lifespan
uses (`agent/service.py:294` `build_agent_service` is the reference for the
embedder/vector-store/retriever/reranker/RAG assembly; the harness builds only
the RAG half). Concurrency capped at `EVAL_CONCURRENCY` to keep a local Ollama
endpoint from thrashing. Every function ≤ 50 lines; the package is split as
`schema.py` / `metrics.py` / `runner.py` / `report.py` / `seed_corpus.py` to
respect the 300-line file cap.

### 3. Metrics (`eval/harness/metrics.py`)

| Metric | Definition | Needs LLM? |
|---|---|---|
| `hit_at_k` | fraction of `answerable` cases where any `expected_doc_ids` ∈ top-k retrieved `doc_id`s | no |
| `mrr` | mean reciprocal rank of the first expected doc | no |
| `refusal_correctness` | `unanswerable`: answer == refusal (constant match `NO_RESULTS_REFUSAL` / `policy.fallback_response`) **or** empty sources; `answerable`: answer is *not* a refusal. Reported per class (over-refusal vs hallucination-risk are different failures). | no |
| `evidence_coverage` | fraction of `expected_answer_evidence` substrings (casefolded) present in the answer — the cheap faithfulness proxy | no |
| `citation_grounding` | fraction of answers whose cited sources include ≥ 1 expected doc (`sources[].title` ↔ corpus map) | no |
| `judged_faithfulness` (optional, `--judge llm`) | LLM judge scores answer-vs-retrieved-chunks support on 0/0.5/1 with a fixed prompt `EVAL_JUDGE_PROMPT_VERSION` | yes |

Core gate (D9): the run must be meaningful with `--judge off` — hit@k +
refusal correctness + evidence coverage carry the trend; the judge is
additive color.

### 4. Reports and trend (`eval/harness/report.py`)

- Each run appends `eval/reports/{ISO-timestamp}.json`:
  `{run_id, git_sha, suite, k, provider_config, per_case: […], summary: {…}}`.
  `eval/reports/` is git-ignored (runtime artifact, like `data/bm25_index.pkl`);
  `eval/golden/` and `eval/corpus/` are versioned (D8).
- `python -m eval.harness.report --last 10` prints a trend table (summary
  metrics per run, delta vs previous) and exits non-zero if the latest run
  regresses any core metric by more than `EVAL_REGRESSION_TOLERANCE` vs the
  previous run — usable as an optional local gate after KB changes (not wired
  into CI: CI has no docker services per `.github/workflows/ci.yml`).
- Per-case failures print `id`, metric, got-vs-expected, and top-3 retrieved
  titles — enough to fix a golden line or spot a chunking bug without rerunning.

### 5. Make targets (`Makefile`)

```make
eval:        ## run offline eval suite against the local stack
	$(PYTHON) -m eval.harness.run_eval --suite all
eval-seed:   ## (re)seed the eval corpus documents
	$(PYTHON) -m eval.harness.seed_corpus
eval-report: ## show quality trend over recent runs
	$(PYTHON) -m eval.harness.report --last 10
```

Uses the same `$(PYTHON)` venv-autodetect convention as `test`/`lint`
(CLAUDE.md "Development commands").

### Constants (no magic numbers — global rule)

```python
# eval/harness/config.py
EVAL_TOP_K = 5                    # matches RAGService default top_k (rag/service.py:44)
EVAL_CONCURRENCY = 4              # parallel cases; protects local LLM endpoints
EVAL_REGRESSION_TOLERANCE = 0.02  # max allowed drop in a core metric between runs
EVAL_JUDGE_PROMPT_VERSION = "kb-eval-judge-v1"
JUDGE_SCORES = (0.0, 0.5, 1.0)    # supported / partial / unsupported
REQUIRED_EMBEDDING_PROVIDER = "local"  # determinism guard (D8)
```

## Files touched

| File | Change |
|---|---|
| `eval/golden/core_faq.jsonl`, `eval/golden/refusals.jsonl` (new) | Initial golden set (~30 answerable + ~10 unanswerable seeded from the fixture corpus). |
| `eval/corpus/*.md` (new) | Fixture knowledge documents the golden set cites. |
| `eval/harness/{__init__,config,schema,seed_corpus,runner,metrics,report}.py` (new) | Loader/validator, corpus seeder, runner, metrics, trend report — each file ≤ 300 lines. |
| `eval/harness/run_eval.py` (new) | CLI entry (`python -m eval.harness.run_eval`). |
| `Makefile` | `eval`, `eval-seed`, `eval-report` targets. |
| `.gitignore` | `eval/reports/`. |
| `src/askflow/rag/prompt_builder.py` | Extract `NO_RESULTS_REFUSAL` constant (no-op if Slice 01 landed first). |
| `docs/status/STATUS.md` | Eval framework status entry. |

No `src/askflow` runtime behavior changes beyond the constant extraction.

## Tests

The harness itself gets unit tests (it is code, subject to the same limits):

`tests/unit/test_eval_metrics.py` (new):
- hit@k: expected doc at rank 1 / rank k / absent; membership by
  `metadata["doc_id"]`, not chunk id (regression: generation-rotated ids).
- MRR arithmetic on fixed fixtures.
- refusal correctness: exact `NO_RESULTS_REFUSAL` match; harness
  `fallback_response` match; answerable case that refuses → counted as
  over-refusal, not pass.
- evidence coverage casefolding; empty-evidence answerable case scores `None`
  (excluded from mean), not `0`.

`tests/unit/test_eval_schema.py` (new):
- golden line validation: unknown `kind` rejected; `answerable` without
  `expected_doc_ids` rejected; the checked-in `eval/golden/*.jsonl` files all
  parse (keeps the versioned set permanently loadable — test fails on a bad PR line).

`tests/unit/test_eval_report.py` (new):
- regression detection: drop > `EVAL_REGRESSION_TOLERANCE` → non-zero;
  improvement / within tolerance → zero.

Plus a documented manual run: `make docker-up && make eval-seed && make eval`
on the seeded stack produces a report with `hit_at_k ≥ 0.9` on the fixture
corpus (the corpus and golden set are authored together, so anything lower
indicates a pipeline bug).

## Contract sync

None — no intent/route/tool/harness change; AGENTS.md untouched. STATUS.md
gains the eval entry; CLAUDE.md "Development commands" should mention
`make eval` in the same change (it is a repo-config doc update, allowed at
top level).

## Acceptance

- [ ] `make eval-seed && make eval` runs green on a fresh local stack and
      writes a timestamped report with all core metrics.
- [ ] Deleting a fixture doc and re-running shows `hit_at_k` drop and the
      affected case ids in the failure output (the framework detects real KB
      regressions).
- [ ] Publishing a Slice-02 entry for a previously-failing golden question
      flips that case to pass on the next run (loop measured end-to-end).
- [ ] `--judge off` (default) completes with no LLM-judge calls; refusal and
      retrieval metrics are fully deterministic across two consecutive runs on
      an unchanged KB (`EMBEDDING_PROVIDER=local` guard enforced).
- [ ] `make eval-report` shows per-run trend and exits non-zero on a
      regression beyond `EVAL_REGRESSION_TOLERANCE`.
- [ ] Golden files are schema-validated by the unit suite; `make lint &&
      make test` green; all harness files within code-quality limits.
