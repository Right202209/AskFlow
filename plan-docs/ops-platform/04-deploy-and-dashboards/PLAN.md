# Slice 04 — Deployment Checklist + Ops Dashboards

> Estimate: ~1.5 days. No DB migration. Mostly docs + read-only endpoints.

## Goal

An operator can take AskFlow from `git clone` to a defensible production
deployment by following one checklist, and can then *see* that it is healthy:
a deeper `/health`, ops-grade `/metrics`, and a "System" panel on the admin
dashboard covering documents, index freshness, LLM/webhook failures, and the
quality signals that already exist.

## Current-state anchors

Deployment reality today:

- `main.py:28-37` — `_assert_production_safe_settings`: boot refuses the
  default `SECRET_KEY` (`main.py:23`, `config.py:12`) unless
  `APP_ENV=development`; `config.py:10` defaults `app_env` to `production` as
  the fail-safe. This is the seed of the checklist, currently documented only
  in CLAUDE.md (not shipped to operators).
- `config.py:4-68` — full settings surface: DB/Redis/MinIO/Chroma endpoints,
  LLM + embedding endpoints and keys, `jwt_expire_minutes` (`:56`),
  `rate_limit_per_minute` (`:59`), `ticket_sla_hours` (`:62`),
  `cors_origins` (`:65`), `bm25_index_path` (`:46`). `.env.example` mirrors
  these with dev-only credentials (`minioadmin`, `askflow:askflow`).
- `docker-compose.yml:1-60` — **infra only** (postgres:13-alpine, redis:7.2,
  chroma, minio with hardcoded dev credentials at `:5-6`, `:46-47`); the app
  itself is not composed. A `Dockerfile` exists at the repo root.
- Known multi-worker gaps (checklist must state them, per CLAUDE.md
  "Concurrency and consistency"):
  - `chat/router.py:45` — `_cancel_flags: dict[str, bool] = {}` process-local
    → WS cancel frames only work when they land on the owning worker.
  - `core/metrics.py:12` — per-process `CollectorRegistry`: with
    `--workers N`, `/metrics` returns one random worker's counters.
  - BM25 pickle writes are already multi-worker-safe (`rag/bm25.py`,
    `filelock` + atomic replace) — checklist notes this as *handled*.
- `main.py:130-132` — `/health` returns static `{"status": "ok"}`; it proves
  the event loop is alive and nothing else.
- `core/metrics.py:14-72` — existing metric inventory: `REQUEST_COUNT`/
  `REQUEST_LATENCY` (labels method/path/status via `core/middleware.py`),
  `RAG_QUERY_*`, `LLM_TOKEN_COUNT`, `INTENT_CLASSIFICATION_COUNT`
  (incremented at `agent/intent_classifier.py:80-97`), `TICKET_COUNT`,
  `ORDER_WEBHOOK_FAILURE_COUNT`, `WS_CONNECTIONS`.
- Admin analytics today: `admin/analytics.py:21-117` — `get_analytics`
  (totals, intent distribution, harness fallback/truncate rates from
  `messages.metadata->harness_trace` at `:51-89`, `thumbs_down_rate_7d` at
  `:92-101`); `:120-231` — `get_ticket_dashboard` (SLA breach vs
  `settings.ticket_sla_hours`, priority split, 7-day trend). Exposed at
  `admin/router.py:156-172`. Frontend: `web/src/pages/Admin/DashboardPage.tsx`
  (221 lines) and `TicketDashboard.tsx` (237 lines).
- Migration/runbook primitives: `make migrate` (bare `alembic` — needs venv on
  PATH, per Makefile), `make seed`, `scripts/create_user.py`.

## Design

### 1. `docs/deployment/CHECKLIST.md` (new doc — `docs/` is the sanctioned home)

Ordered, checkbox-style, each item citing the enforcing code:

1. **Secrets** — generate `SECRET_KEY` (boot enforces: `main.py:28-37`);
   replace Postgres/MinIO dev credentials from `docker-compose.yml:5-6,46-47`;
   set `LLM_API_KEY`/`EMBEDDING_API_KEY`; never commit `.env` (already
   git-ignored). Verify no `minioadmin`/`askflow:askflow` in the prod env.
2. **APP_ENV** — leave unset or `production`; confirm the legacy WS URL-token
   route is absent (dev-only mount, per `chat/router.py`) so JWTs stay out of
   access logs.
3. **Migrations** — `alembic upgrade head` before first traffic and on every
   deploy; never `make seed` in production (creates `admin/admin123` —
   create real users via `scripts/create_user.py`).
4. **Workers** — document the supported topologies: `--workers 1` is fully
   supported; `--workers N` is supported *except* WS cancel
   (`chat/router.py:45`) and per-process `/metrics` (`core/metrics.py:12`) —
   both listed as known gaps with their workarounds (sticky sessions for WS;
   §Design 2 for metrics). Async-index consumer (Slice 03) is N-worker-safe.
5. **Persistence** — volumes for `pgdata`/`redisdata`/`chromadata`/
   `miniodata` (`docker-compose.yml:56-60`) plus the `data/` dir for the BM25
   pickle (`config.py:46`); backup = Postgres dump + MinIO bucket; Chroma and
   BM25 are rebuildable (reindex; `_warm_bm25_index`, `main.py:40-63`).
6. **Network** — TLS terminator in front (app serves plain HTTP), CORS origins
   (`config.py:65`), rate limit sizing (`config.py:59`), and **protect
   `/metrics`** — it is unauthenticated (`core/metrics.py:77-82`); restrict it
   to the scrape network at the proxy.
7. **LLM/embedding endpoints** — reachability, `EMBEDDING_DIMENSION` must
   match the collection (384/bge-small, `config.py:43`); changing embedding
   models requires full reindex.
8. **Ops toggles** — `TICKET_SLA_HOURS`, `ORDER_LOOKUP_WEBHOOK_URL` (mock
   fallback semantics), `LOG_MASKING_ENABLED` / `MASK_STORED_MESSAGES`
   (Slice 02, with the handoff-quality trade-off), audit-log retention.
9. **Verify** — hit `/health` (deep, §Design 3), scrape `/metrics`, load
   `/admin/dashboard`, upload a canary doc and watch it reach `active`
   (Slice 03), run one chat turn.

Also: a short `docs/deployment/README.md` pointing at the checklist and the
compose caveat (app not composed; run via the root `Dockerfile` or systemd +
uvicorn). README.md gets a one-line pointer (it already lags; per CLAUDE.md,
docs/ + this file win).

### 2. `/metrics` extension (`core/metrics.py`, 82 lines — headroom)

New instruments (names follow the existing `askflow_*` convention):

```python
DOCUMENT_INDEX_JOBS = Counter("askflow_document_index_jobs_total", ..., ["kind", "outcome"])   # Slice 03 worker
DOCUMENT_INDEX_DURATION = Histogram("askflow_document_index_duration_seconds", ...)
LLM_REQUEST_FAILURES = Counter("askflow_llm_request_failures_total", ..., ["operation"])       # chat/classify/embed
AUDIT_EVENTS = Counter("askflow_audit_events_total", ..., ["action"])                          # Slice 02 record_audit
BUILD_INFO = Gauge("askflow_build_info", ..., ["version", "harness_policy"])                   # set once at lifespan; policy from harness.py:19
```

Increment points: Slice 03 worker `_process_job` outcomes;
`rag/llm_client.py` and `embedding/embedder.py` failure paths;
`core/audit.py::record_audit`. Multi-worker honesty (D8): add a comment +
checklist entry that `prometheus_client.multiprocess` mode (env
`PROMETHEUS_MULTIPROC_DIR`) is required for `--workers N` scraping — we
document rather than default it, because single-worker is the reference
topology. DB-derived health numbers deliberately go to the admin JSON endpoint
(§Design 4) instead of Prometheus gauges, so they are computed per request and
worker-independent.

### 3. Deep `/health`

Replace the static handler (`main.py:130-132`) with a checker in a new
`core/health.py` (keeps `main.py`, 134 lines, from growing logic):

```python
HEALTH_CHECK_TIMEOUT_SECONDS = 2.0     # per dependency, run concurrently
# checks: postgres (SELECT 1), redis (PING), chroma (heartbeat), minio (bucket_exists)
```

Response: `{"status": "ok"|"degraded", "checks": {name: "ok"|"error:<class>"}}`
— HTTP 200 for ok, 503 for degraded (load-balancer friendly). LLM endpoint is
*not* checked (external, slow, and the app degrades gracefully —
`build_fallback_response`, `rag/prompt_builder.py:42-51`). Keep `/health`
unauthenticated but response bodies free of connection strings (security rule:
errors must not leak sensitive data — report exception class only).

### 4. Admin "System" panel

New `GET /api/v1/admin/system/health` (`admin`/`agent`, mirrors
`admin/router.py:156-163`), served by `admin/analytics.py::get_system_health`
(the file is 240 lines; add a new `admin/system_health.py` module instead to
respect the 300 cap):

- document status counts (one `GROUP BY status` — surfaces Slice 03's
  `pending/indexing/failed` backlog) + oldest `pending` age,
- chunks total + last `indexed_at` (index freshness),
- audit events last 24h by action (Slice 02 table),
- deep-health check results (reuse `core/health.py`),
- `harness_policy_version` (`harness.py:19`) and app version.

Existing quality metrics stay where they are (`get_analytics`,
`analytics.py:21-117`) — the panel *adds* system state rather than duplicating
quality state. Frontend: add a "System" section to
`web/src/pages/Admin/DashboardPage.tsx` (221 lines — extract a
`SystemHealthPanel.tsx` component rather than inflating the page): dependency
status lights, document-status tiles with a link to the Documents page
filtered to `failed`, freshness timestamp. `DASHBOARD_REFRESH_MS = 30_000`
polling, matching the page's existing fetch pattern.

## Files touched

| File | Change |
|---|---|
| `docs/deployment/CHECKLIST.md` (new) | §Design 1 checklist. |
| `docs/deployment/README.md` (new) | Entry point; compose/Dockerfile caveat. |
| `README.md` | One-line pointer to the deployment docs. |
| `core/metrics.py` | New instruments (§Design 2); multiprocess note. |
| `core/health.py` (new) | Concurrent dependency checks + timeout constant. |
| `main.py` | `/health` delegates to `core/health.py`; set `BUILD_INFO` in lifespan. |
| `rag/llm_client.py`, `embedding/embedder.py` | `LLM_REQUEST_FAILURES` increments on failure paths. |
| `embedding/index_worker.py` | Job outcome/duration metrics (Slice 03 file). |
| `core/audit.py` | `AUDIT_EVENTS` increment in `record_audit`. |
| `admin/system_health.py` (new) | `get_system_health` aggregation. |
| `admin/router.py` | `GET /system/health` route (or the split router from Slice 01 if `router.py` is near 300). |
| `schemas/admin.py` | `SystemHealthResponse`. |
| `web/src/pages/Admin/DashboardPage.tsx` | Mount the System panel. |
| `web/src/components/admin/SystemHealthPanel.tsx` (new) | Status lights + doc tiles. |
| `web/src/services/admin.ts` | `getSystemHealth()` wrapper. |

## Tests

`tests/unit/test_health.py` (new):
- all deps ok → 200 + all `ok`; one dep raising → 503, that check
  `error:<ClassName>`, others still `ok` (checks run concurrently — a hung
  dep must not block the rest past `HEALTH_CHECK_TIMEOUT_SECONDS`).
- response contains no URLs/credentials even when a check fails with a
  connection-string-bearing exception message.

`tests/unit/test_system_health.py` (new):
- document status aggregation incl. zero-fill for absent statuses (mirror the
  zero-fill idiom at `analytics.py:141-143`);
- role gate: user → 403, agent/admin → 200.

`tests/unit/test_metrics_extension.py` (new):
- failure-path increments for LLM client + embedder (registry inspection);
- `BUILD_INFO` carries `harness_policy = "askflow-cognitive-harness-v1"`.

Docs are reviewed against acceptance below (no automated test).

## Contract sync

No agent behavior change → **no AGENTS.md change** (`BUILD_INFO` merely
*reports* the harness policy version from `harness.py:19`). CLAUDE.md
"Runtime services" + `docs/status/STATUS.md` gain pointers to the deployment
docs and the deep `/health` semantics; `.env.example` comments for any new
toggle.

## Acceptance

- [ ] A fresh operator following only `docs/deployment/CHECKLIST.md` reaches a
      running deployment that passes checklist step 9 end-to-end.
- [ ] Boot with default `SECRET_KEY` and `APP_ENV=production` fails with the
      exact guidance from `main.py:33-37` (checklist step 1 cross-checks it).
- [ ] `/health` returns 503 with a named failing check when Redis is stopped,
      and recovers to 200 without restart; no secrets in any health body.
- [ ] `/metrics` exposes the new series; a canary upload increments
      `askflow_document_index_jobs_total{outcome="success"}`.
- [ ] Admin dashboard System panel shows dependency lights, doc-status tiles
      (a `failed` doc is visible and links to the filtered Documents page),
      and index freshness; refreshes without reload.
- [ ] Multi-worker limitations (`_cancel_flags`, per-process registry) are
      stated in the checklist with workarounds — not silently ignored.
- [ ] `make lint && make test` green; all touched files ≤ 300 lines.
