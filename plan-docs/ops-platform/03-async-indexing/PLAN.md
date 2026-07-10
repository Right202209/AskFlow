# Slice 03 — Asynchronous Indexing

> Estimate: ~2.5 days. One DB migration (`20260709_03_document_index_status`).
> Highest-risk slice: it moves the three-store invariant into a worker.

## Goal

`POST /api/v1/embedding/documents` returns in milliseconds with the document
in `pending`; an in-app worker indexes it (`indexing` → `active`, or `failed`
with a stored error), the admin Documents page shows live status, and the
three-store invariant — add-then-swap-then-delete, rollback chain, BM25
refresh — is preserved *exactly*, just off the request path.

## Current-state anchors

- `embedding/router.py:43` — `content_bytes = await file.read()`; `:46-51` —
  Postgres row created (status defaults to `indexing`,
  `models/document.py:25-29`); `:61-65` — bytes to MinIO under
  `storage_key` (`_build_storage_key`, `:30-32`, key also stashed in
  `doc.tags` at `:54`); `:66-72` — **the synchronous `index_document` call**
  this slice removes from the request; `:73-86` — the rollback chain on
  failure (Chroma chunks → MinIO object → Postgres row, in that order);
  `:88` — success flips to `DocumentStatus.active` with `chunk_count`.
- `embedding/router.py:92-130` — reindex: reads bytes back from MinIO
  (`get_document_bytes`, `:111`), sets `indexing` (`:112`), and on failure
  restores `active` with the *old* `chunk_count` (`:122`, `:126`) — i.e. a
  failed reindex keeps the previous generation live. The worker must keep
  this asymmetry (first-index failure destroys; reindex failure preserves).
- `embedding/service.py:32-89` — `index_document`: parse (`:49`) → chunk
  (`:50`) → embed (`:55`) → add new generation (`:71-76`) → sweep old via
  `delete_doc_chunks_except` (`:79`) → BM25 refresh + pickle persist
  (`:81`, `:97-113`). Chunk ids `{doc_id}_g{generation}_c{i}` (`:59`).
  **This function does not change.** The slice changes only *who calls it*.
- `embedding/index_worker.py:12-20` — `run_index_worker`: an orphaned stub
  (grep confirms zero callers) that already assembles
  embedder/vector_store/service. It becomes the real worker module.
- `models/document.py:13-17` — `DocumentStatus = {indexing, active, archived}`
  — missing `pending` and `failed`; no error/progress fields on `Document`.
- `repositories/document_repo.py:40` — `update_status(doc_id, status,
  chunk_count=...)` — the claim primitive extends from here.
- Queue substrate: Redis is initialized in lifespan (`main.py:70`,
  `core/redis.py:12-17`, `redis:7.2-alpine` in `docker-compose.yml:18-28`);
  the route-map subscriber (`agent/service.py:114-135`, started `main.py:73`)
  is the precedent for a lifespan-owned background task.
- Frontend: `web/src/pages/Admin/DocumentsPage.tsx` — one-shot
  `fetchDocuments()` on mount (`:33`) and after upload/reindex/delete
  (`:45`, `:61`, `:75`); status badges already rendered
  (`STATUS_COLORS`/`STATUS_LABELS`, `:161-162`);
  `web/src/services/document.ts:8-16` upload/reindex wrappers.
- `admin/router.py:58-66` — `GET /admin/documents?status=` already filters by
  status — the polling endpoint exists.

## Design

### 1. Job transport: Redis list + Postgres status claim (D6)

**Evaluated options:**

| Option | Verdict |
|---|---|
| FastAPI `BackgroundTasks` | **Rejected.** Runs in the same worker's event loop after the response with no persistence: a worker restart mid-index silently loses the job, there is no retry, and with `--workers N` no other process can observe or resume it. It would also keep the CPU-ish parse/chunk on the serving loop. |
| Dedicated queue framework (Celery/arq/RQ) | **Rejected.** A new broker/deployable/config surface for exactly one job type — disproportionate for a single-tenant reference implementation (OVERVIEW scope). |
| **Redis `LPUSH`/`BRPOP` + status-claim in Postgres, worker task in lifespan** | **Chosen.** Redis already runs; the queue is ~30 lines; the worker is an `asyncio.Task` per process (route-map-subscriber precedent), so no new deployable. Redis loss is tolerated because Postgres status is the source of truth: a startup sweep re-enqueues `pending`/stale-`indexing` docs. |

Queue constants (`embedding/queue.py`, new):

```python
INDEX_QUEUE_KEY = "askflow:index:queue"          # Redis list of JSON jobs
INDEX_JOB_KIND_UPLOAD = "upload"
INDEX_JOB_KIND_REINDEX = "reindex"
QUEUE_POP_TIMEOUT_SECONDS = 5                    # BRPOP timeout → loop heartbeat
STALE_INDEXING_REQUEUE_MINUTES = 30              # startup sweep: 'indexing' older than this is orphaned
MAX_INDEX_ATTEMPTS = 3                           # then → failed
```

Job payload: `{"doc_id": str, "kind": str, "attempt": int}` — bytes are *not*
in the job; the worker reads them from MinIO via the `storage_key` in
`doc.tags` (`embedding/router.py:54`), same as reindex does today (`:111`).

**Multi-worker safety (cross-cutting constraint #1):** every process runs a
consumer, and `BRPOP` gives each job to exactly one. The belt-and-braces guard
is a *conditional claim* in Postgres — new
`DocumentRepo.claim_for_indexing(doc_id)` issuing
`UPDATE documents SET status='indexing', index_started_at=now() WHERE id=:id
AND status IN ('pending','failed')` and returning whether a row changed; a
duplicate or stale job that loses the claim is dropped. No process-local
bookkeeping anywhere.

### 2. Status model (migration `20260709_03_document_index_status`)

- Extend the `document_status` Postgres enum with `pending` and `failed`
  (**hand-written** `ALTER TYPE ... ADD VALUE` — autogenerate misses enum
  changes, per CLAUDE.md "Schema change" and the `20260519_01` precedent).
- New columns: `index_error TEXT NULL`, `index_started_at TIMESTAMPTZ NULL`.
- Backfill: any existing row stuck in `indexing` (only possible from a crash
  under the old sync flow) → `failed` with
  `index_error = 'orphaned by pre-async migration'`.

Lifecycle:

```
upload:  pending ──claim──▶ indexing ──▶ active
                                └──▶ failed (attempt < MAX → re-enqueued; else terminal, index_error set)
reindex: active ──▶ indexing ──▶ active   (failure → back to active, old chunks intact — mirrors router.py:122)
```

Reindex keeps `active` as its failure-restore state, so the enum transition
for reindex jobs is tracked via the job `kind`, not a separate status — the
old generation is still serving queries, which is truthful.

### 3. Endpoint changes

`upload_document` (`embedding/router.py:35-89`) becomes: read bytes → create
row with `status=pending` → `put_document_bytes` → `LPUSH` job → return 202
semantics (`APIResponse` with the `pending` document). If the **MinIO write or
enqueue** fails, roll back what exists so far (delete MinIO object if written,
delete Postgres row) — a shrunken version of today's `:73-86` chain; no Chroma
involvement because nothing indexed yet. `EmbeddingProviderError` handling
moves entirely to the worker.

`reindex_document` (`:92-130`) becomes: validate + `LPUSH` reindex job →
return the document (still `active`; status flips when the worker claims it).

### 4. Worker: `embedding/index_worker.py` grows up (D7)

```python
async def index_queue_consumer() -> None      # BRPOP loop; started/stopped in lifespan
async def _process_job(job: IndexJob) -> None # claim → load bytes → index → finalize
async def requeue_orphans() -> None           # startup sweep (pending + stale indexing)
```

`_process_job` per kind:

- **upload**: claim → `get_document_bytes(storage_key)` →
  `EmbeddingService.index_document(...)` (unchanged add-then-sweep,
  `service.py:71-81`) → `update_status(active, chunk_count)`. On failure with
  `attempt >= MAX_INDEX_ATTEMPTS`: run today's terminal rollback in today's
  order — `service.delete_document(doc_id)` (Chroma) →
  `delete_document_bytes` (MinIO) → **keep the Postgres row as `failed` with
  `index_error`** instead of deleting it (`router.py:78` deletes today; a
  visible `failed` row is the whole point of the status column — the admin UI
  gains retry/delete affordances instead of a vanishing act).
- **reindex**: claim (from `active` — the claim SQL for reindex jobs allows
  `active`) → same flow; on terminal failure restore `active` + old
  `chunk_count` and set `index_error`, exactly `router.py:122-127`. Old
  generation was never touched (add-then-sweep guarantees it).

Each worker constructs its own `EmbeddingService` per job (as
`run_index_worker` already does, `index_worker.py:13-15`) and opens its own
`async_session_factory()` session — the request session is gone by the time
the job runs. Lifespan wiring: start after `init_http_client()`
(`main.py:75`), run `requeue_orphans()` once, cancel on shutdown beside
`stop_route_map_subscriber()` (`main.py:86`). BM25 note: the sweep's
`_refresh_bm25_index` (`service.py:97-113`) already rebuilds from Chroma and
persists under `filelock` (`rag/bm25.py`), so concurrent workers indexing
different docs stay correct — last rebuild wins, both include both docs.

### 5. Admin UI: status + polling

`DocumentsPage.tsx`: after upload/reindex, poll `fetchDocuments()` while any
document is `pending`/`indexing` (`POLL_INTERVAL_MS = 3000`,
`POLL_MAX_MINUTES = 30`; stop when none in-flight — no WebSocket, plain
polling is proportionate). Add `pending`/`failed` to
`STATUS_LABELS`/`STATUS_COLORS` (`:161-162`); show `index_error` as a tooltip
on `failed` rows; add a "Retry" button on `failed` calling the reindex
endpoint. `DocumentResponse` (`schemas/document.py`) gains
`index_error`.

## Files touched

| File | Change |
|---|---|
| `models/document.py` | Enum + `pending`/`failed`; `index_error`, `index_started_at`. |
| `alembic/versions/20260709_03_document_index_status.py` (new) | Hand-written enum extension + columns + orphan backfill. |
| `repositories/document_repo.py` | `claim_for_indexing`, `mark_failed`, `list_stale_indexing`. |
| `embedding/queue.py` (new) | Job schema, constants, `enqueue_index_job`, `pop_index_job`. |
| `embedding/index_worker.py` | Stub (`:12-20`) → consumer loop, `_process_job`, `requeue_orphans`, terminal rollback (keep ≤ 300 lines; split `embedding/job_handlers.py` if needed). |
| `embedding/router.py` | Upload → enqueue (sync index call `:66-72` and rollback `:73-86` removed); reindex → enqueue. File shrinks. |
| `embedding/service.py` | **Unchanged** (`index_document` contract stays). |
| `main.py` | Start/stop consumer task + startup orphan sweep in lifespan. |
| `schemas/document.py` | `index_error` on `DocumentResponse`. |
| `core/audit.py` call sites | Slice 02's `document.upload` audit now records "accepted/enqueued"; add `document.index_failed` action from the worker. |
| `web/src/pages/Admin/DocumentsPage.tsx` | New badges, polling, error tooltip, retry. |
| `web/src/services/document.ts` | No shape change beyond `index_error` typing. |

## Tests

`tests/unit/test_index_queue.py` (new):
- upload endpoint returns `pending` fast, enqueues one job, and does **not**
  call `index_document` (patch `askflow.embedding.router` deps).
- MinIO put failure during upload → row deleted, nothing enqueued.
- claim: second claim for same doc no-ops (conditional-UPDATE semantics via
  mocked repo, mirroring `test_ticket_repo_conflict.py`'s style).
- consumer happy path: job → claim → index → `active` + chunk_count.
- retry: failure with `attempt < MAX_INDEX_ATTEMPTS` re-enqueues with
  `attempt+1`; at max → `failed`, `index_error` set, Chroma+MinIO rollback
  called **in that order**, Postgres row retained.
- reindex failure → status restored `active`, old `chunk_count` kept, no
  `delete_document` call (the generation-preservation regression case —
  extends `test_embedding_pipeline_crash.py`).
- `requeue_orphans` re-enqueues `pending` and stale `indexing` (older than
  `STALE_INDEXING_REQUEUE_MINUTES`), skips fresh `indexing`.

Existing invariants must stay green: `test_embedding_pipeline_crash.py`,
`test_bm25_concurrency.py`, `test_bm25_persistence.py`.

## Contract sync

No intent/route/tool/harness change → **no AGENTS.md change**. Docs that do
move: CLAUDE.md's "Document upload / reindex" workflow paragraph and
`docs/status/STATUS.md` (upload is now async; failure is a visible `failed`
status, not a deleted row). Slice 04's checklist documents the worker
(one consumer per process; safe with `--workers N` via BRPOP + claim).

## Acceptance

- [ ] Upload of a multi-MB document returns < 1s with `pending`; the admin
      page shows `pending → indexing → active` without manual refresh.
- [ ] Killing the process mid-index and restarting resumes the job (orphan
      sweep), and the document ends `active` with correct `chunk_count`.
- [ ] Terminal failure shows `failed` + error in the UI; Chroma has zero
      chunks for the doc; MinIO object gone (first index) — but a failed
      *reindex* leaves the old generation fully retrievable.
- [ ] Two app processes + simultaneous uploads: every doc indexed exactly
      once (claim guard), BM25 contains all docs afterwards.
- [ ] `EmbeddingService.index_document` diff is empty.
- [ ] Enum migration applies on a DB with existing rows; stuck `indexing`
      rows land in `failed` with the backfill message.
- [ ] `make lint && make test` green; all touched files ≤ 300 lines.
