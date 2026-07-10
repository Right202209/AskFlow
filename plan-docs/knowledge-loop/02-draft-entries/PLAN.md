# Slice 02 — Feedback → Draft Knowledge Entries

> Depends on Slice 01 (`knowledge_gaps` table, `/admin/gaps` page).
> Estimate: ~3 days. One DB migration (`20260709_02_knowledge_drafts`).
> Flagship slice: closes the loop from "gap seen" to "KB answers it".

## Goal

Staff turn a captured gap — plus the material that already contains the answer
(a resolved ticket, a handoff transcript, or their own typing) — into a **draft
knowledge entry**, review it, and on approve it is published into the real
document pipeline (Postgres + MinIO + Chroma) so the next user asking the same
question gets a RAG answer with a citation instead of a refusal.

Success looks like: gap "怎么开发票?" (frequency 12) → staff clicks "draft",
pulls in the resolution text of a related ticket → edits → approve → a
`Document` titled *"[KB] 怎么开发票"* appears on `/admin/documents`, is
retrievable, and the gap flips to `promoted` with `promoted_doc_id` set.

## Current-state anchors

- **The publish pipeline already exists end-to-end.** Upload flow
  `embedding/router.py:35-89`: create `Document` row
  (`document_repo.py:16`) → `put_document_bytes` (`core/minio_client.py:23`,
  storage key `documents/{doc_id}{suffix}`, recorded in `Document.tags`
  `embedding/router.py:52-54`) → `EmbeddingService.index_document`
  (`embedding/service.py:32-89`, add-then-sweep with `generation` epoch ids
  `{doc_id}_g{generation}_c{i}`, `service.py:57-59`) → on
  `EmbeddingProviderError` roll back Chroma → MinIO → Postgres
  (`router.py:75-87`) → `update_status(active, chunk_count)` (`router.py:88`).
  This slice **reuses that exact sequence** — it must not re-implement any of
  the three-store choreography (OVERVIEW constraint #3).
- **Chunk metadata contract.** `embedding/service.py:60-68` — every chunk gets
  `{doc_id, title, source?, indexed_at_epoch, generation, chunk_index}`.
  Passing `source="knowledge-loop"` makes published entries selectable via the
  existing retrieval filter `filters.sources` (`rag/filters.py`) with no schema
  change — this is what Slice 03 uses to eval "KB-loop docs only".
- **Answer material.** Tickets: `models/ticket.py:48-52` (`title`,
  `description`, `content` JSONB, `resolved_at`), fetched via
  `TicketRepo.get_by_id` (`ticket_repo.py:78`) and listed via `list_all`
  (`ticket_repo.py:175`). Handoff transcripts: the conversation's messages,
  `MessageRepo.list_by_conversation` (`message_repo.py:38`), reachable from the
  gap's `example_conversation_id` (Slice 01 §Design 1).
- **LLM access for draft synthesis.** `rag/llm_client.py::LLMClient.chat`
  (`llm_client.py`) — the same client the RAG service uses
  (`rag/service.py:64`); shared instance is wired at lifespan
  (`main.py` app lifespan, per CLAUDE.md "Runtime services").
- **Admin CRUD template.** `admin/router.py:98-133` (create/update/delete
  intents: thin handler → service → `APIResponse`); document deletion pattern
  incl. vector cleanup `admin/router.py:69-85`.
- **Frontend templates.** `web/src/pages/Admin/DocumentsPage.tsx` (197 lines,
  upload + list) and `IntentsPage.tsx` (263 lines, inline edit forms) — the
  review page combines both patterns; services in `web/src/services/admin.ts`
  and `document.ts`.

## Design

### 1. `knowledge_drafts` table (migration `20260709_02_knowledge_drafts`)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `gap_id` | UUID NULL FK `knowledge_gaps.id` | null ⇒ staff-initiated draft without a gap |
| `question` | Text NOT NULL | canonical question (editable copy of gap question) |
| `answer` | Text NOT NULL | markdown body — the reviewed content |
| `status` | Enum `draft_status` | `draft` / `approved` / `rejected`, default `draft` |
| `source_ticket_id` | UUID NULL FK `tickets.id` | provenance |
| `source_conversation_id` | UUID NULL FK `conversations.id` | provenance (handoff transcript) |
| `synthesis` | JSONB NULL | `{model, prompt_version, generated: bool}` when LLM-assisted |
| `created_by` / `reviewed_by` | UUID FK `users.id` (reviewed_by NULL) | author vs approver |
| `published_doc_id` | UUID NULL FK `documents.id` | set on approve |
| `review_note` | Text NULL | reject reason / approve note |
| `created_at` / `updated_at` | TimestampMixin | |

Partial unique index — at most one *pending* draft per gap, mirroring the
`20260519_01` pattern (autogenerate misses `postgresql_where`; no backfill —
table starts empty):

```python
op.create_index(
    "uniq_pending_draft_per_gap",
    "knowledge_drafts",
    ["gap_id"],
    unique=True,
    postgresql_where=sa.text("status = 'draft' AND gap_id IS NOT NULL"),
)
```

`KnowledgeDraftRepo.create` uses `INSERT … ON CONFLICT DO NOTHING` + refetch,
same shape as `ticket_repo.py:24` — two staff members clicking "draft" on the
same gap converge on one row.

### 2. Draft creation (D7 — LLM optional, never blocking)

`src/askflow/knowledge/draft_service.py::DraftService`:

- `create_from_gap(gap_id, source: DraftSource)` where `DraftSource` is a
  dataclass (`ticket_id | conversation_id | manual_answer`) — ≤ 3 positional
  params rule.
- Material assembly: ticket → `title + description + content` text; handoff →
  transcript rendered as `role: content` lines, capped at
  `MAX_TRANSCRIPT_CHARS`; manual → the provided text verbatim.
- If `synthesize=true` (request flag): one `LLMClient.chat` call with a fixed
  prompt (`DRAFT_SYNTHESIS_PROMPT_VERSION = "kb-draft-v1"` recorded in
  `synthesis`) asking for a concise Q&A markdown answer grounded *only* in the
  material, wrapped in `asyncio.wait_for(…, DRAFT_SYNTHESIS_TIMEOUT_S)`. On
  timeout/error: fall back to the raw material as the draft answer, set
  `synthesis.generated=false`, log a warning. The endpoint always returns a
  draft.
- Every draft is human-edited before approve; synthesis is a convenience, not
  a trust boundary — the approve gate (§3) is the trust boundary
  (OVERVIEW out-of-scope: no auto-publish).

### 3. Approve → publish (D6 — ordinary documents, existing pipeline)

`DraftService.approve(draft_id, reviewer)`:

1. Guard: status must be `draft` via a conditional
   `UPDATE knowledge_drafts SET status='approved' … WHERE id=:id AND
   status='draft'` — the race loser gets 409, same conditional-update shape as
   the handoff-claim precedent (agent-real-handoff OVERVIEW D9). Publish work
   happens only for the winner.
2. Render bytes: markdown document `# {question}\n\n{answer}\n` (plus a
   provenance footer with gap/ticket ids), UTF-8, filename
   `kb-{draft_id}.md`.
3. Publish via the **upload sequence**, extracted from
   `embedding/router.py:35-89` into a shared helper
   `src/askflow/knowledge/publisher.py::publish_document_bytes(...)` rather
   than duplicated: `DocumentRepo.create(title=KB_TITLE_PREFIX + question,
   source=KB_DOC_SOURCE, tags={storage_key, kb_draft_id})` →
   `put_document_bytes` → `index_document(..., source=KB_DOC_SOURCE)` → on any
   indexing failure run the same rollback chain (delete Chroma chunks → MinIO
   object → Postgres row) **and revert the draft to `draft` status** so the
   approve can be retried — a failed publish must not strand an "approved but
   unindexed" draft.
4. On success: set `draft.published_doc_id`, `reviewed_by`; flip the gap to
   `promoted` + `promoted_doc_id` (`KnowledgeGapRepo.set_status`, Slice 01).
   Single DB commit for draft+gap so they can't diverge.

Refactor note: `embedding/router.py::upload_document` should be re-pointed at
`publisher.publish_document_bytes` in the same change so there is exactly one
implementation of the three-store sequence (and the file, currently ~140+
lines, stays under 300). Behavior of `/api/v1/embedding/documents` is
unchanged — covered by existing upload tests.

Published entries are ordinary `Document` rows: they show up on
`/admin/documents` (`admin/router.py:58-66`), and delete/reindex
(`admin/router.py:69-85`, `embedding/router.py:92-131`) work with zero new
code. `KB_DOC_SOURCE` in chunk metadata keeps them filterable.

### 4. API surface (`src/askflow/knowledge/router.py`, extends Slice 01's module — split into `router_gaps.py` / `router_drafts.py` if the combined file nears 300 lines)

- `POST /admin/gaps/{gap_id}/draft` — body `{ticket_id? | conversation_id? |
  manual_answer?, synthesize: bool}`; staff (`admin`/`agent`).
- `GET /admin/drafts?status=draft` — paginated review queue; staff.
- `GET /admin/drafts/{id}` — detail incl. material provenance; staff.
- `PUT /admin/drafts/{id}` — edit question/answer while `draft`; staff.
- `POST /admin/drafts/{id}/approve` — **admin only** (write gate matches
  reindex `embedding/router.py:97`); returns the published `DocumentResponse`.
- `POST /admin/drafts/{id}/reject` — body `{review_note}`; admin only; gap
  stays `open` (it is still a real gap).

### 5. Frontend

- `web/src/pages/Admin/KnowledgePage.tsx` (new), route `/admin/knowledge`
  inside the staff guard (`web/src/router/index.tsx:32-36`): review queue list
  → detail drawer with editable question/answer (markdown textarea), material
  panel (ticket text / transcript), Approve (admin-visible only, role from
  `authStore`) / Reject buttons.
- `GapsPage.tsx` (Slice 01) row action "Draft entry" opens a source picker
  (related ticket search via existing `GET /admin/tickets`, or the gap's
  example conversation, or blank) and calls `POST /gaps/{id}/draft`.
- Fetchers in `web/src/services/admin.ts`; state in `adminStore.ts`.

### Constants (no magic numbers — global rule)

```python
# knowledge/draft_service.py / publisher.py
DRAFT_SYNTHESIS_TIMEOUT_S = 8          # matches handoff-summary budget (agent-real-handoff D4)
DRAFT_SYNTHESIS_PROMPT_VERSION = "kb-draft-v1"
MAX_TRANSCRIPT_CHARS = 8000            # transcript material cap fed to synthesis
MAX_DRAFT_ANSWER_CHARS = 20000         # hard cap on stored answer body
KB_DOC_SOURCE = "knowledge-loop"       # Document.source + chunk metadata `source`
KB_TITLE_PREFIX = "[KB] "              # published document title prefix
DEFAULT_DRAFTS_PAGE_SIZE = 20
```

## Files touched

| File | Change |
|---|---|
| `alembic/versions/20260709_02_knowledge_drafts.py` (new) | Table + `draft_status` enum + `uniq_pending_draft_per_gap` partial index. |
| `src/askflow/models/knowledge_draft.py` (new) | `KnowledgeDraft` + `DraftStatus`; export in `models/__init__.py`. |
| `src/askflow/repositories/knowledge_draft_repo.py` (new) | `create` (ON CONFLICT), `list`, `get_by_id`, `update_body`, `transition_status` (conditional UPDATE). |
| `src/askflow/knowledge/draft_service.py` (new) | Material assembly, optional synthesis, approve/reject orchestration. |
| `src/askflow/knowledge/publisher.py` (new) | `publish_document_bytes` — the single three-store publish + rollback implementation. |
| `src/askflow/knowledge/router.py` (extend / split) | Draft endpoints (§Design 4). |
| `src/askflow/schemas/knowledge.py` (extend) | `DraftCreate`, `DraftUpdate`, `DraftResponse`, `DraftReview`. |
| `src/askflow/embedding/router.py` | `upload_document` delegates the store sequence to `publisher.publish_document_bytes` (behavior unchanged). |
| `web/src/pages/Admin/KnowledgePage.tsx` (new), `GapsPage.tsx`, `router/index.tsx`, `services/admin.ts`, `stores/adminStore.ts` | Review UI, draft action, route, fetchers, store. |
| `docs/status/STATUS.md` | Knowledge-loop wave status entry. |

## Tests

`tests/unit/test_draft_service.py` (new):
- create from ticket / transcript / manual — material assembled correctly,
  transcript capped at `MAX_TRANSCRIPT_CHARS`.
- synthesis timeout → draft still created from raw material,
  `synthesis.generated=false`.
- double "draft" click on one gap → single pending draft (conflict path).
- approve: publish helper called with `source=KB_DOC_SOURCE`; draft + gap
  updated in one commit; second concurrent approve gets 409.
- approve with `index_document` raising `EmbeddingProviderError` → rollback
  chain invoked (Chroma, MinIO, PG deletes asserted in order) **and** draft
  reverted to `draft`.
- reject keeps gap `open`.

`tests/unit/test_knowledge_publisher.py` (new):
- happy path store-call ordering: PG create → MinIO put → index → status
  active; failure at each step rolls back everything before it.

`tests/unit/test_embedding_router.py` (extend): upload endpoint still passes
through the shared publisher (regression on the refactor).

Plus `make lint && make test` green.

## Contract sync

No intent/route/tool/harness change — AGENTS.md is untouched by this slice
(the agent's behavior improves only because the KB content improves). The
CLAUDE.md "Document upload / reindex" invariant now has two callers of one
publisher; note the refactor in STATUS.md.

## Acceptance

- [ ] Gap → draft → edit → approve → the question now gets a cited RAG answer
      in chat (manual end-to-end run on the seeded stack).
- [ ] Published entry appears on `/admin/documents` and is deletable /
      reindexable via existing admin endpoints.
- [ ] Chunks carry `source="knowledge-loop"`; `/api/v1/rag/query` with
      `filters.sources=["knowledge-loop"]` retrieves them.
- [ ] Approve is admin-only; drafting/reviewing is staff; user role gets 403.
- [ ] Simulated indexing failure during approve leaves no orphan in any of the
      three stores and the draft returns to the review queue.
- [ ] Gap flips to `promoted` with `promoted_doc_id`; a re-asked promoted
      question that still fails opens a *new* gap (Slice 01 hash-reuse).
- [ ] One publish implementation: upload endpoint and approve path share
      `publisher.publish_document_bytes`.
- [ ] Migration up/down clean; `make lint && make test` green; files within
      code-quality limits.
