# Slice 01 — Knowledge Gap Radar

> Estimate: ~2 days. One DB migration (`20260709_01_knowledge_gaps`).
> Agent behavior unchanged — capture is a passive consumer of existing signals.

## Goal

Every time the bot fails a user — clarify, low-confidence override, RAG
refusal, thumbs-down, handoff — the *question* is captured into a deduplicated
`knowledge_gaps` table with a frequency counter and a signal breakdown, and an
admin page lists the top open gaps so staff can see **what the KB can't answer,
ranked by how often it happens**.

Success looks like: ask "怎么开发票?" three times (no invoicing doc indexed) →
one gap row, `frequency=3`, `signals={"rag_refusal": 3}` → visible at the top
of `/admin/gaps`.

## Current-state anchors

Signals that already exist and where they surface:

- **Clarify / low-confidence.** `harness.py:122-126` — `choose_route` overrides
  to `clarify` when `intent.confidence < low_confidence_threshold` (`0.5`,
  `harness.py:24`) and sets `reason="route_override_low_confidence"`. The trace
  (route, reason, flags) is persisted per assistant message at
  `chat/service.py:74-83` onto `messages.metadata` (`models/message.py:36`,
  ORM attribute `extra`). `clarify_node` fixed copy: `nodes.py:176-182`.
- **RAG refusal.** Two fixed refusal strings: retrieval-empty refusal in
  `build_fallback_response` (`prompt_builder.py:42-45` — *"Sorry, I couldn't
  find relevant information…"*) and the harness fallback
  (`harness.py:40` `fallback_response`). The streaming path yields the fallback
  on LLM failure (`rag/service.py:93-100`); empty `sources` after
  retrieve+rerank (`rag/service.py:80-90`) is the retrieval-miss case.
- **Low retrieval score.** `sources` entries carry `score`
  (`rag/service.py:82-90`); scores are **RRF-fused ranks**, not similarities —
  `retriever.py:109-143`, `k=60`, weights `0.6/0.4` (`retriever.py:36-37`), so
  the theoretical max is `(0.6+0.4)/61 ≈ 0.0164`. Any threshold must be stated
  in RRF units (see §Design 2, D2).
- **Negative feedback.** `POST /messages/{message_id}/feedback`
  (`chat/router.py:170-199`) upserts into `feedback`
  (`repositories/feedback_repo.py:16`, `models/feedback.py:18-31`,
  `rating IN (-1, 1)`). The user's *question* is the preceding `user` message in
  the same conversation (`message_repo.py:38` `list_by_conversation`).
- **Handoff.** `nodes.py:117-138` sets `should_handoff=True`;
  `chat/service.py:211-218` pushes the `handoff` frame. The question that
  triggered it is `state.question`.
- **Aggregation precedent.** `admin/analytics.py:52-79` already does JSONB
  path extraction + `GROUP BY` over `messages.metadata->'harness_trace'` — but
  only rates/distributions, never question text.
- **Dedup precedent.** `alembic/versions/20260519_01_ticket_open_unique.py` —
  hand-written partial unique index + backfill;
  `ticket_repo.py:24` `INSERT … ON CONFLICT DO NOTHING` + refetch.
- **Admin surface patterns.** Router: `admin/router.py:88-133` (intent CRUD:
  thin handlers + `AdminService`, `require_role(UserRole.admin, UserRole.agent)`
  for reads / `admin` for writes). Frontend: `web/src/router/index.tsx:32-36`
  staff routes, `web/src/pages/Admin/TicketsOverviewPage.tsx` (179 lines) is
  the closest list-page template, thin fetchers in `web/src/services/admin.ts`,
  state in `web/src/stores/adminStore.ts`.

### Why a table, not a derived query

Everything above *could* be reconstructed by SQL over `messages` + `feedback`
JSONB — but dedup/frequency requires normalization + grouping of free text,
gap lifecycle (open → promoted → dismissed) requires mutable status, and Slice
02 needs a stable `gap_id` to hang drafts off. A query can't hold state. The
table is written best-effort at signal time and is *reconstructible* (a
backfill script can replay history), so losing a write is cheap.

## Design

### 1. `knowledge_gaps` table (migration `20260709_01_knowledge_gaps`)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | `UUIDMixin` (`models/base.py`) |
| `question` | Text NOT NULL | most recent raw phrasing |
| `question_norm` | Text NOT NULL | normalized form (§Design 3) |
| `question_hash` | String(64) NOT NULL | sha256 of `question_norm` |
| `status` | Enum `gap_status` | `open` / `promoted` / `dismissed`, default `open` |
| `frequency` | Integer NOT NULL default 1 | bumped on dedup hit |
| `signals` | JSONB NOT NULL | per-signal counters, e.g. `{"clarify": 2, "negative_feedback": 1}` |
| `last_intent` | String(100) NULL | from `state.intent` when available |
| `example_conversation_id` | UUID NULL FK `conversations.id` | jump-to-context link |
| `example_message_id` | UUID NULL FK `messages.id` | the failing assistant message |
| `promoted_doc_id` | UUID NULL FK `documents.id` | set by Slice 02 on publish |
| `created_at` / `updated_at` | TimestampMixin | |

Partial unique index (hand-written — autogenerate misses `postgresql_where`,
same as the `20260519_01` worked example):

```python
op.create_index(
    "uniq_open_gap_question_hash",
    "knowledge_gaps",
    ["question_hash"],
    unique=True,
    postgresql_where=sa.text("status = 'open'"),
)
```

Open gaps dedup; promoted/dismissed gaps free the hash so a recurring question
can reopen as a fresh gap (evidence the promoted doc didn't fix it). No
backfill needed — the table starts empty.

### 2. Signal capture points (all best-effort, constraint #1)

One new module `src/askflow/knowledge/gap_recorder.py` exposing
`async def record_gap(db, signal: GapSignal) -> None` where `GapSignal` is a
frozen dataclass (`kind`, `question`, `conversation_id`, `message_id`,
`intent`). Callers:

| Signal kind | Hook point | Trigger condition |
|---|---|---|
| `clarify` | `chat/service.py` after the assistant `msg_repo.create` (`service.py:75-83`) — the trace and `message_id` are both in hand | `harness_trace["route"] == "clarify"` (covers both the mapping default `nodes.py:205` and the override `harness.py:122-126`) |
| `rag_refusal` | same hook | route `rag` AND (`sources` empty OR `response_text` equals `NO_RESULTS_REFUSAL` / `HARNESS_FALLBACK` — D3) |
| `low_retrieval_score` | same hook | route `rag`, sources non-empty, `max(s["score"]) < LOW_RRF_SCORE_THRESHOLD` |
| `handoff` | same hook | `result.should_handoff` is truthy (threaded through `_stream_agent_response`'s return, `service.py:142-153`, which gains a `should_handoff` element) |
| `negative_feedback` | `chat/router.py::submit_feedback` (`router.py:174-199`), after the upsert, before commit | `body.rating == -1`; question = latest prior `user` message in the conversation (new `MessageRepo.get_preceding_user_message(message_id)`) |

The chat-side hook is a single call
`await maybe_record_gap_from_turn(db, turn_ctx)` extracted into
`gap_recorder.py` so `process_user_message` stays within the 50-line limit.
Failures are caught and logged (`logger.warning("gap_record_failed", …)`) —
never re-raised. The gap insert shares the request's DB session/commit; if the
turn's commit fails the gap is lost with it, which is acceptable (best-effort).

To make refusal detection non-heuristic (D3), the two refusal strings are
extracted into named constants that the *existing* code imports back:
`prompt_builder.py:44` copy becomes `NO_RESULTS_REFUSAL` and
`CognitiveHarnessPolicy.fallback_response` (`harness.py:40`) stays the policy
field but is compared via `policy.fallback_response` — no string duplication.

### 3. Dedup upsert (D1 — race-safe like tickets)

Normalization in `gap_recorder.py::normalize_question`: NFKC → lowercase →
strip → collapse whitespace → truncate to `MAX_GAP_QUESTION_CHARS`. Then
`question_hash = sha256(question_norm)`.

`KnowledgeGapRepo.record` (new `repositories/knowledge_gap_repo.py`) uses a
single statement — mirroring `ticket_repo.py:24` but with `DO UPDATE` because
we want the counter bump, not a no-op:

```sql
INSERT INTO knowledge_gaps (…)
VALUES (…)
ON CONFLICT (question_hash) WHERE status = 'open'
DO UPDATE SET
    frequency  = knowledge_gaps.frequency + 1,
    question   = EXCLUDED.question,
    signals    = knowledge_gaps.signals
                 || jsonb_build_object(:kind,
                    COALESCE((knowledge_gaps.signals->>:kind)::int, 0) + 1),
    updated_at = now()
```

Concurrent workers hitting the same hash both land on the row — no
check-then-insert race, no process-local counter (constraint #2).

### 4. Admin surface

Backend — handlers live in a new `src/askflow/knowledge/router.py` mounted at
`/api/v1/admin/gaps` from `main.py::create_app` (keeps `admin/router.py`, 172
lines, under the 300 cap):

- `GET /admin/gaps?status=open&order=frequency&limit&offset` — paginated list
  (`PaginatedResponse`, same shape as `admin/router.py:136-153`). Read access:
  `require_role(UserRole.admin, UserRole.agent)`.
- `GET /admin/gaps/{gap_id}` — detail incl. example conversation/message ids.
- `GET /admin/gaps/{gap_id}/related` — embedding-similarity suggestions (D5):
  embed `question_norm` with the existing `Embedder`
  (`embedding/embedder.py::create_embedder`), cosine against other open gaps'
  questions embedded on the fly for the top `RELATED_GAPS_CANDIDATES` most
  frequent gaps. Read-time only; if the embedder is down, return `[]`.
- `PATCH /admin/gaps/{gap_id}` — status transition `open → dismissed`
  (admin-only; `promoted` is set exclusively by Slice 02's publish path).

Frontend — `web/src/pages/Admin/GapsPage.tsx` (template:
`TicketsOverviewPage.tsx`), route `/admin/gaps` added inside the staff guard
block (`web/src/router/index.tsx:32-36`), nav entry alongside
Documents/Intents, fetchers in `web/src/services/admin.ts`, list state in
`web/src/stores/adminStore.ts`. Columns: question, frequency, signal chips,
last intent, updated_at; row actions: dismiss, view conversation
(`/app/chat/:conversationId` deep link), and (after Slice 02) "draft entry".

### Constants (no magic numbers — global rule)

```python
# knowledge/gap_recorder.py
LOW_RRF_SCORE_THRESHOLD = 0.008   # top fused score below ~half of single-source
                                  # rank-1 (1/61*0.5≈0.008) ⇒ weak-consensus hit (D2)
MAX_GAP_QUESTION_CHARS = 500      # normalized question cap (< harness 2000-char input cap)
GAP_SIGNAL_KINDS = ("clarify", "rag_refusal", "low_retrieval_score",
                    "handoff", "negative_feedback")
RELATED_GAPS_CANDIDATES = 50      # open gaps considered for similarity suggestions
RELATED_GAPS_TOP_N = 5            # suggestions returned
DEFAULT_GAPS_PAGE_SIZE = 20       # matches admin tickets list default (admin/router.py:139)
```

## Files touched

| File | Change |
|---|---|
| `alembic/versions/20260709_01_knowledge_gaps.py` (new) | Table + `gap_status` enum + partial unique index (hand-written `postgresql_where`). |
| `src/askflow/models/knowledge_gap.py` (new) | `KnowledgeGap` model + `GapStatus` enum; export in `models/__init__.py`. |
| `src/askflow/repositories/knowledge_gap_repo.py` (new) | `record` (upsert), `list_gaps`, `count`, `get_by_id`, `set_status`. |
| `src/askflow/knowledge/__init__.py` (new) | Package init. |
| `src/askflow/knowledge/gap_recorder.py` (new) | `GapSignal`, `normalize_question`, `record_gap`, `maybe_record_gap_from_turn`, constants. |
| `src/askflow/knowledge/router.py` (new) | `/admin/gaps` list/detail/related/patch. |
| `src/askflow/schemas/knowledge.py` (new) | `GapResponse`, `GapUpdate`, `RelatedGapResponse`. |
| `src/askflow/main.py` | Mount knowledge router under `/api/v1/admin/gaps`. |
| `src/askflow/chat/service.py` | `_stream_agent_response` returns `should_handoff`; one `maybe_record_gap_from_turn` call after `service.py:83` (file is 226 lines — the hook must stay a single call, logic lives in `gap_recorder.py`). |
| `src/askflow/chat/router.py` | `submit_feedback` (`router.py:174`): on `rating == -1`, record `negative_feedback` gap before `db.commit()`. |
| `src/askflow/repositories/message_repo.py` | Add `get_preceding_user_message(message_id)`. |
| `src/askflow/rag/prompt_builder.py` | Extract refusal copy to `NO_RESULTS_REFUSAL` constant (behavior identical). |
| `web/src/pages/Admin/GapsPage.tsx` (new) | Gap list + dismiss + deep links. |
| `web/src/router/index.tsx`, `web/src/services/admin.ts`, `web/src/stores/adminStore.ts` | Route, fetchers, store slice. |
| `AGENTS.md` | §4.5: note `harness_trace` is now consumed by the gap radar and `route` / `reason` / `flags` keys are a stable read contract. |

## Tests

`tests/unit/test_gap_recorder.py` (new):
- clarify trace → gap recorded with `signals={"clarify": 1}`.
- same normalized question twice → one row, `frequency=2` (assert the upsert
  SQL path, mock-execute like `test_ticket_repo_conflict.py`).
- rag route + empty sources → `rag_refusal`; sources with top score `0.005` →
  `low_retrieval_score`; top score `0.012` → no gap.
- recorder raising → `process_user_message` still completes (best-effort).
- normalization: NFKC/case/whitespace variants hash equal; >500 chars truncated.

`tests/unit/test_gap_router.py` (new):
- list pagination + status filter; dismiss transition; non-staff 403;
  `related` returns `[]` when embedder unavailable.

`tests/unit/test_chat_router.py` (extend):
- `rating=-1` feedback records a `negative_feedback` gap with the preceding
  user question; `rating=1` records nothing.

Plus `make lint && make test` green.

## Contract sync

No new intent/route/tool — routing behavior is untouched. AGENTS.md §4.5
(harness trace vocabulary) gains one paragraph declaring the trace keys read by
the gap radar (`route`, `reason`, `flags`) as a consumer contract, per §7's
change rules. STATUS.md gains the knowledge-loop wave entry.

## Acceptance

- [ ] Each of the five signal kinds produces/increments a gap row (manual run:
      ask an unanswerable question, thumbs-down an answer, trigger a handoff).
- [ ] Same question re-asked increments `frequency` on one row; concurrent
      double-fire does not create duplicates (partial unique index holds).
- [ ] A gap-recorder exception never surfaces to the chat user (WS turn
      completes normally, warning logged).
- [ ] `/admin/gaps` lists open gaps ordered by frequency with signal chips;
      dismiss works; page is staff-gated (user role gets 403 / no nav entry).
- [ ] Dismissed gap's hash is reusable — the question re-opens a new gap.
- [ ] Migration up/down clean on a seeded DB; `make lint && make test` green;
      all touched files within code-quality limits.
