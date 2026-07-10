# Slice 01 — Refusal on Weak Retrieval

> Estimate: ~1 day. Backend-only; no migration, no protocol change, no frontend.

## Goal

When retrieval can't support an answer, AskFlow **says so deterministically**
instead of handing the LLM an empty-ish context and hoping the system prompt's
honesty plea holds. The refusal is a first-class outcome: honest copy, a
harness-trace flag, and a `retrieval_confidence` number that slices 02/03 build on.

Success looks like:

```
User: 你们支持量子加密传输吗?            ← knowledge base has nothing relevant
Bot:  这个问题我在知识库中没有找到足够可靠的依据，
      为避免误导就不猜测了。您可以换个说法再问，
      或者我可以为您转接人工客服。        ← refusal, no fabricated answer
```

## Current-state anchors

- `rag/service.py::query_stream` `service.py:80-91` — retrieve (`top_k * 2`,
  `service.py:80`) → rerank (`service.py:81`) → build sources → prompt → stream.
  **No branch inspects result quality.** Same shape in `query` (`service.py:50-64`).
- `rag/prompt_builder.py:5-12` — `SYSTEM_PROMPT` asks the model to be honest;
  that is the *only* current defense against answering from nothing.
- `rag/prompt_builder.py:42-51` — `build_fallback_response` fires on **LLM
  failure** (`service.py:65-67`, `service.py:97-100`), not weak retrieval; with
  `results == []` it already has honest no-info copy worth reusing.
- `rag/retriever.py:83` — vector score is `1.0 - distance` (≈ 0..1).
  `retriever.py:97` — bm25 score is raw and unbounded. `retriever.py:122-133` —
  fused score is an RRF sum `Σ weight/(k+rank+1)` with `k=60`, so the *best
  possible* fused score is ≈ `0.6/61 + 0.4/61 ≈ 0.0164`. **Three incomparable
  scales under one `score` field** — the core trap this slice must not fall into.
- `rag/reranker.py:27-28` — default assembly passes `Reranker()` with
  `model_name=None` (`agent/service.py:303`), i.e. **passthrough**: reranking
  neither filters nor scores. `reranker.py:68-73` — even the LLM path only
  reorders. No reranker score exists to threshold on.
- `agent/nodes.py::rag_stream_node` `nodes.py:54-61` — returns
  `(stream, sources)` from `query_stream`; consumed at `agent/service.py:230`.
- `agent/service.py:228-236` — the `rag` branch wraps the stream with
  `harness.wrap_stream` and passes `state.harness_trace` along. This is where
  the refusal flag must be written **before** the ProcessResult is built.
- `agent/harness.py:194-195` — `wrap_stream` yields `policy.fallback_response`
  if the inner stream produced nothing: a refusal implemented as an *empty*
  stream would get silently rewritten. The refusal must yield its copy as tokens.
- `agent/harness.py:122-126` — low intent-confidence already overrides to
  `clarify`. Distinct concern: clarify = "I don't understand you"; refusal =
  "I understand you, but I don't know". Both copies should offer handoff.
- `rag/router.py:68-80` — REST `/rag/query` returns `RAGAnswer(answer, sources)`;
  gets the same refusal for free once `RAGService.query` refuses.
- `AGENTS.md` §1.2 — a pending `out_of_scope` *intent* is tracked there. This
  slice is complementary, not a replacement: `out_of_scope` is pre-retrieval
  (classifier), refusal is post-retrieval (evidence-based).

## Design

### 1. Refuse inside RAGService, not the router (decision D1)

Routing happens before retrieval (`agent/service.py:223-230`), so the harness
cannot see retrieval strength when it picks a route. The refusal is therefore an
outcome of the `rag` route: `query` / `query_stream` assess grounding after
rerank and, on `grounded=False`, skip the LLM entirely and return
`REFUSAL_RESPONSE` (as a single-token stream in the streaming path — never an
empty stream, per the `harness.py:194-195` anchor). Weak-but-nonzero sources are
still returned (capped at `REFUSAL_MAX_SOURCES`) so the user sees *why* the bot
declined — honesty includes showing the weak evidence.

### 2. Channel-aware grounding (`rag/grounding.py`, new — decision D2)

```python
@dataclass(frozen=True)
class GroundingAssessment:
    confidence: float          # 0..1, normalized across channels
    grounded: bool             # confidence >= GROUNDED_CONFIDENCE_THRESHOLD and hits >= MIN_GROUNDED_RESULTS
    top_score: float           # raw top score, for the trace
    channel: str               # "vector" | "bm25" | "fused" | "empty"
```

`assess_grounding(results: list[RetrievalResult]) -> GroundingAssessment`:

| `results[0].source` | Confidence formula |
|---|---|
| (empty list) | `0.0`, `channel="empty"` |
| `vector` | top score directly (already ≈ 0..1, `retriever.py:83`) |
| `bm25` | logistic squash `1 / (1 + exp(-(top - BM25_MIDPOINT) / BM25_SCALE))` — raw BM25 is unbounded |
| `fused` | max **vector-channel** score among the top `FUSED_LOOKBACK` fused hits; RRF magnitudes are rank artifacts, not relevance. Requires `_rrf_fuse` to preserve the original per-channel score on the result (new `RetrievalResult` field `raw_scores: dict[str, float]`, populated at `retriever.py:122-131`; falls back to bm25 squash if no vector hit survived fusion) |

All constants live in `grounding.py`; no formula fragments elsewhere.

### 3. Return-shape change (decision D3)

`query_stream` currently returns a 2-tuple (`service.py:102`). It becomes:

```python
@dataclass
class RAGStreamResult:
    token_stream: AsyncIterator[str]
    sources: list[dict]
    grounding: GroundingAssessment
```

Call sites: `agent/nodes.py:54-61` (`rag_stream_node` — passes it through) and
`agent/service.py:230` (unpacks it). `RAGResult` (`service.py:18-24`) gains
`grounding: GroundingAssessment | None = None`; `rag/router.py:74-80` surfaces
`grounded` + `confidence` on `RAGAnswer`.

### 4. Harness-trace integration (rails stay on)

In the `rag` branch (`agent/service.py:228-236`), before building
`ProcessResult`:

- append `weak_retrieval_refusal` to `state.harness_trace["flags"]` when
  `grounding.grounded is False`;
- record `retrieval_confidence` and `retrieval_channel` in the trace
  unconditionally (slice 03 reads them from `messages.extra.harness_trace`).

The stream still goes through `harness.wrap_stream` (`agent/service.py:232`) —
the refusal copy is well under `max_response_chars`, so rails are a no-op but
remain on. Trace-vocabulary addition → sync `AGENTS.md` §4.5.

### Constants (no magic numbers — global rule)

```python
GROUNDED_CONFIDENCE_THRESHOLD = 0.35   # below this → refuse
MIN_GROUNDED_RESULTS = 1               # refusing on zero hits is unconditional
BM25_MIDPOINT = 8.0                    # logistic center for raw BM25 scores
BM25_SCALE = 4.0                       # logistic spread
FUSED_LOOKBACK = 3                     # fused hits inspected for a vector score
REFUSAL_MAX_SOURCES = 2                # weak evidence still shown to the user
REFUSAL_RESPONSE = (
    "这个问题我在知识库中没有找到足够可靠的依据，为避免误导就不猜测了。"
    "您可以换个说法再问，或者我可以为您转接人工客服。"
)
```

`GROUNDED_CONFIDENCE_THRESHOLD` / `BM25_MIDPOINT` / `BM25_SCALE` are tuning
knobs, not truths — the acceptance step includes a manual sweep against the
seeded knowledge base before freezing them.

## Files touched

| File | Change |
|---|---|
| `rag/grounding.py` (new) | `GroundingAssessment`, `assess_grounding`, all constants. Keeps `service.py` (102 lines) well under the 300 cap. |
| `rag/service.py` | `query` / `query_stream` call `assess_grounding` post-rerank; refusal short-circuit; return `RAGStreamResult` / extended `RAGResult`. Extract shared source-building (`service.py:52-60` vs `82-90` is already duplicated — fold into one helper). |
| `rag/retriever.py` | `RetrievalResult` gains `raw_scores: dict[str, float]`; `_rrf_fuse` populates it (`retriever.py:122-131`). |
| `agent/nodes.py` | `rag_stream_node` returns `RAGStreamResult` (`nodes.py:54-61`). |
| `agent/service.py` | `rag` branch unpacks the new shape; writes `weak_retrieval_refusal` flag + `retrieval_confidence` into `state.harness_trace` (`service.py:228-236`). |
| `rag/router.py` | `RAGAnswer` gains `grounded` / `confidence`. |
| `AGENTS.md` | §4.5: add `weak_retrieval_refusal` flag + `retrieval_confidence` trace field; §8: add `rag/grounding.py` to the source index. |

## Tests

`tests/unit/test_rag_grounding.py` (new):
- empty results → `confidence=0.0`, `grounded=False`.
- vector top score above / below `GROUNDED_CONFIDENCE_THRESHOLD`.
- bm25 squash: very low and very high raw scores map near 0 / 1.
- fused results with and without a surviving vector `raw_scores` entry.

`tests/unit/test_rag_refusal.py` (new):
- weak retrieval → `query_stream` yields exactly `REFUSAL_RESPONSE`, LLM client
  **not called** (assert mock), sources capped at `REFUSAL_MAX_SOURCES`.
- refusal stream survives `harness.wrap_stream` unchanged (the
  empty-stream-fallback regression case, `harness.py:194-195`).
- `agent/service.process` on weak retrieval → harness trace contains
  `weak_retrieval_refusal` and `retrieval_confidence`.
- strong retrieval → no flag, LLM called, behavior unchanged.

Plus: existing `tests/integration/test_rag_pipeline.py` updated for the new
return shape; `make test` + `make lint` green.

## Contract sync

`AGENTS.md` §4.5 (trace vocabulary: `weak_retrieval_refusal`,
`retrieval_confidence`, `retrieval_channel`) and §8 (source index) in the same
commit. No intent/route/tool change — §1/§2/§3 untouched (refusal is not a new
route; note the relationship to pending §1.2 `out_of_scope` in one sentence).

## Acceptance

- [ ] Zero-hit and below-threshold retrieval produce `REFUSAL_RESPONSE`; the LLM is never called on refusal.
- [ ] Refusal is not rewritten by `wrap_stream` (yields tokens, under length cap).
- [ ] `harness_trace` carries `weak_retrieval_refusal` + `retrieval_confidence` and lands on `messages.extra` via the existing persist path (`chat/service.py:74-83`).
- [ ] REST `/rag/query` returns `grounded=false` + refusal copy for the same inputs.
- [ ] Thresholds swept manually against seeded docs; values recorded in `grounding.py` comments.
- [ ] `AGENTS.md` §4.5 + §8 updated in the same commit.
- [ ] `make lint && make test` green; touched files within code-quality limits.
