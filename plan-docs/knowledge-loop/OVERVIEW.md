# Knowledge Loop — Self-Evolving Knowledge Base

**Spine:** close the loop between "the bot failed a user" and "the knowledge base
got better." Today AskFlow *emits* every failure signal it needs — clarify
routes, low-confidence overrides, RAG refusals, thumbs-down feedback, handoffs —
and then **drops all of them on the floor**. Nothing aggregates them, nothing
turns them into content, and nothing measures whether a knowledge-base change
actually helped.

## The three missing pieces (grounded in current code)

**A. Failure signals exist but evaporate.** The harness persists a rich
`harness_trace` onto `messages.metadata` (`chat/service.py:74-83`,
`models/message.py:36`) including `route`, `reason`
(`route_override_low_confidence` at `harness.py:122-126`) and `flags`. Negative
feedback lands in the `feedback` table via
`POST /messages/{message_id}/feedback` (`chat/router.py:170-199`,
`models/feedback.py:18-31`). RAG refusals emit fixed copy from
`build_fallback_response` (`prompt_builder.py:42-45`). Handoffs set
`should_handoff` (`nodes.py:117-138`). But the only consumer is
`admin/analytics.py:52-79` — *rates and distributions*, never the **questions
themselves**. Nobody can answer "what are the top 20 things users ask that we
can't answer?"

**B. Staff answers never become knowledge.** Tickets carry resolutions
(`models/ticket.py:49-52` — `description`, `content` JSONB, `resolved_at`) and
handoff conversations carry staff-visible transcripts, but the only way content
enters the KB is a manual file upload on `/admin/documents`
(`embedding/router.py:35-89`). The organization answers the same question in
tickets forever.

**C. KB changes are unmeasurable.** There is no golden QA set and no offline
eval — `tests/e2e/` is empty and `Makefile` has no eval target. After a reindex
or a new document, "did retrieval get better or worse?" is answered by vibes.

## Scope

In scope:
- Slice 01 — knowledge gap radar: capture + dedup unresolved questions into a
  `knowledge_gaps` table, admin list view with frequency and signal breakdown.
- Slice 02 — gap → draft knowledge entry → admin review/approve → publish
  through the existing document pipeline (PG + MinIO + Chroma, add-then-sweep).
- Slice 03 — offline evaluation: versioned golden QA set, `make eval` harness
  scoring hit@k / citation faithfulness / refusal correctness, trend report.

Out of scope (product positioning, CLAUDE.md: single-tenant self-hosted
reference implementation — no SaaS scaffolding):
- Multi-tenant gap namespaces, per-customer KBs, billing/quotas.
- Online A/B testing or interleaving experiments (offline eval only).
- Auto-publish without human approval — a human always gates what enters the KB.
- ML topic-modeling clustering services; dedup is normalization + hash, with
  embedding-similarity *suggestions* only (Slice 01 §Design 4).

## Sequencing & rationale

```
01-gap-radar ──▶ 02-draft-entries ──▶ 03-offline-eval
 (capture)        (flagship: act)      (measure)
```

Slice 01 goes first: it is write-side capture + one table + one read-only admin
page, needs one migration, touches no agent routing, and produces the queue
that Slice 02 consumes. Slice 02 is the flagship — it turns the gap queue into
published knowledge via the *existing* indexing pipeline (no new indexing code
path). Slice 03 is deliberately last so the golden set can seed itself from
real captured gaps and approved entries, and so eval can quantify the loop the
first two slices built. (Slice 03 has no code dependency on 01/02 and may be
built in parallel if staffing allows.)

## Cross-cutting constraints (apply to every slice)

1. **Capture must never break chat.** All gap recording is best-effort:
   wrapped, logged on failure, never raised into
   `process_user_message` (`chat/service.py:25`). A radar outage may lose a
   signal; it may not lose a user message.
2. **No process-local state.** Gap dedup counters live in Postgres (`ON
   CONFLICT` upsert), never an in-memory dict — same trap as the known
   `_cancel_flags` gap (`chat/router.py:45`).
3. **Knowledge enters the KB only via `EmbeddingService.index_document`**
   (`embedding/service.py:32`) with the upload rollback chain
   (`embedding/router.py:75-87`: Chroma → MinIO → Postgres). No slice writes to
   Chroma or MinIO directly.
4. **Contract-with-code.** Slice 01 adds a harness-trace consumer, not a new
   route/tool — agent behavior is unchanged, so AGENTS.md moves only where a
   trace field is formalized (§4.5). Slices 02/03 do not touch agent behavior.
5. **Hard code-quality limits**: functions ≤ 50 lines, files ≤ 300 lines,
   nesting ≤ 3, ≤ 3 positional params, named constants only. `admin/router.py`
   is already 172 lines and `chat/service.py` 226 — both slices add new modules
   (`src/askflow/knowledge/`) instead of inflating existing files.
6. **Migrations follow the repo convention**: `YYYYMMDD_NN_<slug>.py`, hand-
   written partial indexes with `postgresql_where` + backfill where needed —
   `alembic/versions/20260519_01_ticket_open_unique.py` is the worked example.

## Resolved design decisions (rationale in the slice docs)

| # | Decision | Where |
|---|---|---|
| D1 | Gap dedup is a DB-level upsert on `(question_hash)` partial-unique over open gaps, mirroring the `uniq_open_user_title` precedent — frequency increments are race-safe by construction. | 01 §Design 3 |
| D2 | "Low retrieval score" is *not* a raw-score threshold: RRF scores are rank-based (`retriever.py:109-143`, k=60 → max ≈ 0.0164). Signal = empty `sources` OR top fused score < `LOW_RRF_SCORE_THRESHOLD`. | 01 §Design 2 |
| D3 | Refusal detection compares against the two fixed refusal strings (`prompt_builder.py:44`, `harness.py:40`) via constants shared with the code, not substring heuristics. | 01 §Design 2 |
| D4 | Negative-feedback capture hooks the existing `submit_feedback` endpoint (`chat/router.py:174`) — no new client API, no WS protocol change. | 01 §Design 2 |
| D5 | Clustering = normalization+hash dedup at write time; embedding-similarity "related gaps" is a read-time suggestion using the existing `Embedder`, never a blocking write dependency. | 01 §Design 4 |
| D6 | Approved entries publish as ordinary `Document` rows (`source="knowledge-loop"`) — markdown Q&A bytes in MinIO, indexed via `index_document`. They are then listable/deletable/reindexable with zero new admin code. | 02 §Design 3 |
| D7 | LLM-assisted draft synthesis is optional and synchronous with a timeout; on failure the draft is created from raw material (gap question + ticket resolution text). Never block the review flow on the LLM. | 02 §Design 2 |
| D8 | Golden set lives in `eval/golden/*.jsonl` (versioned, reviewed in PRs); reports in `eval/reports/` are git-ignored artifacts. Eval runs against a live local stack (`EMBEDDING_PROVIDER=local` for determinism), not mocks. | 03 §Design 1/4 |
| D9 | Citation faithfulness is judged by `expected_doc_ids` overlap + answer-substring evidence, with LLM-judge as an *optional* second stage — the core metrics must run with no LLM at all (refusal + hit@k). | 03 §Design 3 |

## Docs in this initiative

- [`01-gap-radar/PLAN.md`](01-gap-radar/PLAN.md)
- [`02-draft-entries/PLAN.md`](02-draft-entries/PLAN.md)
- [`03-offline-eval/PLAN.md`](03-offline-eval/PLAN.md)
