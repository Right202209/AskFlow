# Production Deployment Checklist

> AskFlow is a **single-tenant, self-hosted** reference implementation. This
> checklist takes you from `git clone` to a defensible production deployment.
> Each item cites the code that enforces (or fails to enforce) it. Work top to
> bottom; step 9 is the end-to-end verification.

## 1. Secrets

- [ ] Generate a strong random `SECRET_KEY`. Boot **refuses** the default
      placeholder unless `APP_ENV=development`
      (`src/askflow/main.py::_assert_production_safe_settings`,
      `config.py::Settings.secret_key`).
- [ ] Replace all dev credentials from `docker-compose.yml`: Postgres
      `askflow:askflow`, MinIO `minioadmin:minioadmin`. Grep the running
      environment to confirm none survive:
      `env | grep -Ei 'minioadmin|askflow:askflow'` returns nothing.
- [ ] Set real `LLM_API_KEY` / `EMBEDDING_API_KEY` for your endpoints.
- [ ] `.env` is git-ignored — never commit it. Secrets come from the
      environment or a secret manager only.

## 2. APP_ENV

- [ ] Leave `APP_ENV` unset or `production` (it defaults to `production` as a
      fail-safe, `config.py`).
- [ ] Confirm the legacy WebSocket URL-token route is **absent**: it is mounted
      only when `APP_ENV=development` (`chat/router.py`), so in production the
      JWT travels in the first `auth` frame and never lands in access logs or
      browser history.

## 3. Migrations & users

- [ ] Run `alembic upgrade head` before first traffic and on every deploy
      (bare `alembic` needs the venv on `PATH`; see the Makefile).
- [ ] **Never `make seed` in production** — it creates `admin/admin123`.
      Create real accounts with `scripts/create_user.py`
      (`make create-user username=... email=... password=... role=...`).

## 4. Workers

- [ ] `--workers 1` is fully supported and is the reference topology.
- [ ] `--workers N` is supported **except** two known gaps — decide the
      workaround before scaling out:
  - WebSocket cancel frames: `_cancel_flags` is a process-local dict
    (`chat/router.py`), so a `cancel` only works when it lands on the worker
    that owns the socket. Workaround: sticky sessions at the load balancer, or
    stay single-worker.
  - `/metrics`: the Prometheus `CollectorRegistry` is per-process
    (`core/metrics.py`), so a scrape returns one random worker's counters. See
    step 6 for the multiprocess workaround.
- [ ] The async index consumer **is** N-worker-safe: `BRPOP` hands each job to
      exactly one worker and a conditional Postgres status-claim
      (`DocumentRepo.claim_for_indexing`) drops duplicate/stale jobs.
- [ ] BM25 pickle writes **are** N-worker-safe (`rag/bm25.py`, `filelock` +
      atomic `os.replace`) — no action needed.

## 5. Persistence & backup

- [ ] Mount durable volumes for `pgdata` / `redisdata` / `chromadata` /
      `miniodata` (`docker-compose.yml`) **and** the host `data/` dir that
      holds the BM25 pickle (`config.py::bm25_index_path`).
- [ ] Backup = Postgres dump + MinIO bucket. Chroma and BM25 are rebuildable
      (reindex a document, or rely on the lifespan BM25 warm-load/rebuild in
      `main.py::_warm_bm25_index`), so they are not on the critical backup path.

## 6. Network & metrics exposure

- [ ] Terminate TLS in front (the app serves plain HTTP).
- [ ] Set `CORS_ORIGINS` to the real frontend origin(s) (`config.py`).
- [ ] Size `RATE_LIMIT_PER_MINUTE` for your traffic (`config.py`).
- [ ] **Protect `/metrics`** — it is unauthenticated (`core/metrics.py`).
      Restrict it to the scrape network at the proxy.
- [ ] Multi-worker metrics: to aggregate across `--workers N`, run
      `prometheus_client` in multiprocess mode by setting
      `PROMETHEUS_MULTIPROC_DIR`. We document rather than default it because
      single-worker is the reference topology (§Design 2, D8).

## 7. LLM / embedding endpoints

- [ ] Confirm reachability of the chat and embedding endpoints.
- [ ] `EMBEDDING_DIMENSION` must match the collection (`384` for
      `BAAI/bge-small-en-v1.5`, `config.py`). Changing the embedding model
      requires a **full reindex**.

## 8. Ops toggles

- [ ] `TICKET_SLA_HOURS` — SLA-breach threshold on the ticket dashboard.
- [ ] `ORDER_LOOKUP_WEBHOOK_URL` — unset ⇒ `search_order` returns mock data;
      set ⇒ live webhook with mock fallback on timeout/4xx/5xx.
- [ ] `LOG_MASKING_ENABLED` (default on) — mask phone/email/order-id in logs.
- [ ] `MASK_STORED_MESSAGES` (default off) — also mask PII in persisted chat
      messages. **Trade-off:** on = stronger data minimization, but degrades
      human-handoff context and conversation-summary quality (staff/LLM then
      see redacted user text). Operator's call.
- [ ] Audit-log retention: rows are append-only; prune older than
      `AUDIT_RETENTION_DAYS` (365) with your own scheduled job if required.

## 9. Verify (end-to-end)

- [ ] `GET /health` returns `200 {"status":"ok", "checks":{...}}` with every
      dependency `ok` (deep check: Postgres/Redis/Chroma/MinIO, `core/health.py`).
- [ ] Scrape `/metrics` and confirm the `askflow_*` series are present.
- [ ] Load `/admin/dashboard` — the **System** panel shows dependency lights,
      document-status tiles, and index freshness.
- [ ] Upload a canary document and watch it go `pending → indexing → active`
      without a manual refresh; confirm
      `askflow_document_index_jobs_total{outcome="success"}` increments.
- [ ] Run one chat turn end-to-end (retrieval → answer, or a refusal on weak
      retrieval).
