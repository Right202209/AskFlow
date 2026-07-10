# Ops Platform

**Spine:** make AskFlow *operable* — the supporting platform that lets a real
team deploy it, tune it, audit it, and watch it, without touching the code. The
agent/RAG/ticket features are the product; this initiative is the console
around them.

## The four gaps (grounded in current code)

**A. Prompts are compiled in.** Every prompt the system sends to the LLM is a
module-level string constant: the RAG system prompt + context template
(`rag/prompt_builder.py:5-19`), the RAG fallback copy
(`prompt_builder.py:42-51`), and the intent-classifier prompt
(`agent/intent_classifier.py:15-27`). Changing a single sentence of assistant
behavior is a code deploy. Meanwhile the *routing* config already solved this
exact problem — `intent_configs` rows + 60s TTL cache + Redis pub/sub
invalidation + an invalidate-epoch counter (`agent/service.py:27-135`). Prompts
should ride the same rail.

**B. Admin mutations leave no trail.** Document delete
(`admin/router.py:69-85`), intent CRUD (`admin/router.py:98-133`), upload/
reindex (`embedding/router.py:35-130`), and ticket status changes
(`ticket/router.py:65-97`) mutate state with zero record of *who did what
when*. Logs are structured JSON to stdout (`core/logging.py:8-21`) but carry
raw user content (e.g. `chat/service.py:171` traces, question text in
prompts) with no PII masking anywhere.

**C. Upload blocks on embedding.** `embedding/router.py:66-72` calls
`index_document` inline in the request — parse + chunk + **remote embedding
API call** + Chroma write + full BM25 rebuild, all before the HTTP response.
A large PDF against a slow embedding endpoint is a multi-minute request.
There is even a stub worker (`embedding/index_worker.py:12-20`) that **nothing
calls** — the intent existed; the wiring never landed. `DocumentStatus`
(`models/document.py:13-17`) has `indexing/active/archived` but no
`pending`/`failed`, so a failure is only visible as a deleted row.

**D. No deployment story, thin observability.** `/metrics`
(`core/metrics.py:77-82`) exposes request/RAG/intent/ticket counters from a
**per-process** `CollectorRegistry` (`metrics.py:12`) — meaningless the moment
`uvicorn --workers 2` starts. There is a `Dockerfile` and a dev
`docker-compose.yml` (infra only, no app service), but no production checklist
covering the `SECRET_KEY` fail-safe (`main.py:28-37`), migrations, or the
known multi-worker traps (`chat/router.py:45` `_cancel_flags`). The admin
dashboard (`admin/analytics.py`) covers tickets + harness quality but nothing
about system health (index freshness, doc failures, LLM error rate).

## Scope

In scope:
- Slice 01 — prompt template CRUD (DB-backed, versioned, cached like the route map).
- Slice 02 — audit log for admin mutations + PII masking in logs.
- Slice 03 — asynchronous indexing with document status + admin progress.
- Slice 04 — production deployment checklist doc + ops metrics/dashboard extension.

Out of scope (product positioning — "single-tenant, self-hosted reference
implementation", CLAUDE.md; keep ops proportionate):
- Multi-tenant anything, billing, per-tenant quotas.
- External job frameworks (Celery/RQ/arq/Dramatiq) — Redis primitives we
  already run are enough for one queue (Slice 03 §Design 1).
- SIEM export, log shipping, tamper-proof audit chains — the audit log is a
  plain Postgres table an admin can query.
- Grafana/alerting stacks — we expose Prometheus text and one admin JSON
  endpoint; wiring a scraper is the operator's job (documented in the checklist).

## Sequencing & rationale

```
01-prompt-templates ──▶ 02-audit-and-masking ──▶ 03-async-indexing ──▶ 04-deploy-and-dashboards
  (pattern reuse)          (needs 01's CRUD           (largest risk;        (docs + metrics;
                            in the audit list)         status feeds 04)      observes 01–03)
```

- 01 first: it is a near-mechanical transplant of the proven
  `intent_route_mapping` pattern (cache TTL, pub/sub channel, epoch counter),
  so it de-risks the "DB-backed runtime config" muscle before anything novel.
- 02 second: the audit decorator wants the *complete* set of admin mutations,
  which includes 01's new prompt CRUD — landing it after 01 avoids retrofits.
- 03 third: it is the only slice that changes a data-integrity-critical flow
  (three-store invariant); by then slices 01/02 have exercised migrations and
  admin plumbing. Its `pending/failed` statuses are inputs to 04's health panel.
- 04 last: checklists and dashboards should describe the system as it will
  ship, i.e. after 01–03.

## Cross-cutting constraints (apply to every slice)

1. **No process-local state for anything multi-worker-visible.** Caches must
   have a cross-worker invalidation path (the route-map precedent,
   `agent/service.py:79-111`); queues/locks live in Redis or Postgres. Do not
   add another `_cancel_flags`-style dict (`chat/router.py:45`).
2. **Hard code-quality limits** (global rules): functions ≤ 50 lines, files
   ≤ 300 lines, nesting ≤ 3, ≤ 3 positional params, no magic numbers.
   `agent/service.py` is already 316 lines — Slice 01 must *extract* the cache
   machinery, not copy-paste it. `chat/router.py` (427) is off-limits for
   additions.
3. **Contract-with-code.** Slice 01 touches prompt text the harness and
   classifier depend on → AGENTS.md sections move in the same commit. Slices
   02–04 do not change agent behavior (verified per slice under "Contract sync").
4. **Migrations follow the house style.** Files named
   `YYYYMMDD_NN_description.py` under `alembic/versions/` (existing:
   `20260327_01_initial_schema.py`, `20260519_01_ticket_open_unique.py`);
   autogenerate then hand-check enums/partial indexes/backfills.
5. **Every new admin endpoint is role-gated** via
   `require_role(...)` (`core/auth.py:45`) and returns
   `APIResponse`/`PaginatedResponse` (`schemas/common.py`) like the existing
   admin surface.

## Resolved design decisions (rationale in the slice docs)

| # | Decision | Where |
|---|---|---|
| D1 | Extract a generic `core/config_cache.py` (TTL + epoch + pub/sub) and re-base the route map on it, rather than duplicating the pattern for prompts. | 01 §Design 1 |
| D2 | Prompt versioning = append-only `prompt_versions` rows + an `active_version_id` pointer; "rollback" is repointing, never mutating history. | 01 §Design 3 |
| D3 | Harness copy strings (`harness.py:35-41`) stay **code-owned** — they are safety rails, not tunable copy; letting an admin blank the prompt-injection refusal would gut the harness. | 01 §Non-goals |
| D4 | Audit writes are in-transaction with the mutation (same `AsyncSession`) — an audited action and its audit row commit or roll back together; no fire-and-forget. | 02 §Design 2 |
| D5 | Masking is a pure function applied at the logging boundary (structlog processor) + explicitly in audit payloads; raw message storage is untouched by default (`MASK_STORED_MESSAGES=false`). | 02 §Design 3/4 |
| D6 | Async indexing uses a Redis list queue (`BRPOP`) + a claim-by-status Postgres guard, run as an in-app `asyncio` worker task started in lifespan — no new deployable, survives multi-worker because the claim is a conditional UPDATE. FastAPI `BackgroundTasks` rejected (dies with the request cycle, invisible to other workers, no retry). | 03 §Design 1 |
| D7 | The three-store rollback chain moves into the worker *unchanged in order* (Chroma sweep → MinIO delete stays only for terminal failure of a *first* index; re-index failure keeps the old generation live — exactly today's `embedding/router.py:73-86` vs `120-127` split). | 03 §Design 4 |
| D8 | `/metrics` gets a multi-worker warning + `multiprocess` mode is *documented, not defaulted*; DB-derived gauges (doc status counts, SLA breach) are computed per scrape so they are worker-independent. | 04 §Design 2 |

## DB migrations added by this initiative

| Migration | Slice | Contents |
|---|---|---|
| `20260709_01_prompt_templates` | 01 | `prompt_templates` + `prompt_versions` tables |
| `20260709_02_audit_logs` | 02 | `audit_logs` table + indexes |
| `20260709_03_document_index_status` | 03 | extend `document_status` enum (`pending`, `failed`) + `index_error`, `index_started_at` columns + backfill |

## Docs in this initiative

- [`01-prompt-templates/PLAN.md`](01-prompt-templates/PLAN.md)
- [`02-audit-and-masking/PLAN.md`](02-audit-and-masking/PLAN.md)
- [`03-async-indexing/PLAN.md`](03-async-indexing/PLAN.md)
- [`04-deploy-and-dashboards/PLAN.md`](04-deploy-and-dashboards/PLAN.md)
