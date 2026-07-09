# AskFlow Project Structure

> Last updated: 2026-05-20

This document describes the repository as it exists today and records where future files should live.

## Top-Level Layout

| Path | Purpose | Notes |
|------|---------|-------|
| `src/askflow/` | Backend source | FastAPI app and domain modules |
| `web/` | Frontend app | React 19 + Vite 6 + Tailwind 4 + Zustand 5 + react-router 7 |
| `alembic/` | Database migrations | Alembic environment and version files |
| `tests/` | Backend tests | `unit/`, `integration/`, `e2e/` (e2e is empty) |
| `scripts/` | Developer scripts | seed data, create user, local runner |
| `docs/` | Project documentation | status, audits, structure, architecture notes |
| `web/docs/` | Frontend docs | route, page, and stack notes |
| `static/` | Build output area | not a source directory |
| `.trellis/` | Trellis task tracking | per-task PRD / brainstorm / research |
| `.github/workflows/` | CI workflows | `ci.yml` (lint + test + web build), `codeql.yml` |

Root-level files should be limited to:

- entry docs: `README.md`, `README_zh.md`, `PRD.md`, `AGENTS.md`, `CLAUDE.md`, `TRELLIS.md`, `LICENSE`
- repository config: `pyproject.toml`, `Makefile`, `Dockerfile`, `docker-compose.yml`, `alembic.ini`
- environment template: `.env.example`

## Backend Layout

`src/askflow/` is organized around shared infrastructure plus business domains.

| Path | Responsibility |
|------|----------------|
| `src/askflow/main.py` | app factory, lifespan (Redis / BM25 warm / route-map subscriber / httpx / AgentService singleton), route mounting |
| `src/askflow/config.py` | Pydantic Settings loading from `.env` |
| `src/askflow/dependencies.py` | dependency helpers |
| `src/askflow/core/` | auth (JWT + RBAC), database (async session), logging (structlog), metrics (Prometheus), middleware, Redis pool, MinIO helpers, rate limiter, exceptions |
| `src/askflow/models/` | SQLAlchemy models (`user`, `conversation`, `message`, `ticket`, `document`, `feedback`, `intent_config`) |
| `src/askflow/schemas/` | Pydantic request/response models |
| `src/askflow/repositories/` | persistence access layer; `TicketRepo.create` carries the `ON CONFLICT` dedup |
| `src/askflow/chat/` | conversation REST, WebSocket dispatcher, per-message lifecycle (`service.py`), session store, protocol schemas, connection manager |
| `src/askflow/rag/` | hybrid retriever, BM25 (`bm25.py` — immutable-snapshot pattern), vector store (Chroma wrapper), reranker, LLM service, retrieval filters |
| `src/askflow/agent/` | intent classifier, graph, routing nodes, tools (`search_order` + `search_knowledge`), Cognitive Harness, agent state, orchestrator (`service.py`) |
| `src/askflow/ticket/` | ticket lifecycle and notifications |
| `src/askflow/embedding/` | parser, chunker, embedder abstraction (`api` / `local`), indexing service (`service.py` — add-then-swap-then-delete) |
| `src/askflow/admin/` | admin APIs (auth admin / documents / intents CRUD / tickets / analytics + ticket dashboard) |

Placement rules:

- cross-cutting infrastructure goes in `core/`
- domain-specific service logic stays inside its own domain package
- database models stay in `models/`
- API contracts stay in `schemas/`
- data-access logic goes into `repositories/`
- intent CRUD MUST go through `admin/service.AdminService` so the route-map cache invalidation publishes (see [`AGENTS.md`](../AGENTS.md) §2.3)
- new ticket-creation paths MUST go through `repositories/ticket_repo.py::TicketRepo.create` to inherit the partial-unique-index dedup

## Frontend Layout

`web/` contains both the runnable frontend and its implementation notes.

| Path | Responsibility |
|------|----------------|
| `web/src/pages/Auth/` | `LoginPage`, `RegisterPage` |
| `web/src/pages/App/` | `ChatPage`, `TicketsPage`, `TicketDetailPage` |
| `web/src/pages/Admin/` | `DashboardPage`, `DocumentsPage`, `IntentsPage`, `TicketsOverviewPage`, `TicketDashboard` |
| `web/src/components/` | reusable UI components (layout, chat, ticket, dashboard widgets) |
| `web/src/router/` | `index.tsx` + `guards.tsx` (`RequireAuth`, `RequireRole`) |
| `web/src/services/` | thin HTTP wrappers (`api`, `auth`, `chat`, `ticket`, `document`, `admin`, `jwt`) |
| `web/src/stores/` | Zustand stores (`authStore`, `chatStore`, `ticketStore`, `adminStore`, `toastStore`) |
| `web/src/hooks/` | `useWebSocket` (auth-frame protocol, reconnect, heartbeat) |
| `web/src/lib/` | small utilities (e.g. `cn` for Tailwind class merge) |
| `web/src/types/` | TypeScript interfaces and API types |
| `web/src/styles/` | global styles and design tokens |
| `web/docs/` | frontend-only documentation |

Placement rules:

- page containers go under `pages/`
- reusable UI fragments go under `components/`
- request code stays in `services/`
- app state stays in `stores/`
- WebSocket lifecycle logic stays in `hooks/useWebSocket.ts` (not in stores)
- frontend documentation stays in `web/docs/`

## Testing and Scripts

| Path | Purpose |
|------|---------|
| `tests/unit/` | ≈25 unit test files covering auth, agent (graph / nodes / harness / tools), bm25 (concurrency + persistence), chat router (REST + auth), chunker, config, conversation repo, embedder, embedding pipeline + router, feedback + harness trace, intent, order webhook, parser, prompt builder, protocol, rag service, retriever, route-map cache + epoch, schemas, security, ticket repo (conflict path) + service, trace |
| `tests/integration/` | `test_chat_websocket.py`, `test_intent_invalidation.py`, `test_rag_pipeline.py`, `test_ticket_flow.py` (DB sessions still mocked with `AsyncMock` rather than real Postgres) |
| `tests/e2e/` | placeholder — empty package |
| `scripts/seed_data.py` | create default users and intent configs |
| `scripts/create_user.py` | CLI user creation (`make create-user`) |
| `scripts/run.sh` | local helper script |

## Documentation Placement

Use these locations for future documentation:

- `docs/README.md` — documentation index
- `docs/PROJECT_STRUCTURE.md` — structure and placement rules (this file)
- `docs/AGENT_HARNESS.md` — Cognitive Harness explainer
- `docs/USAGE_GUIDE_zh.md` — end-to-end walkthrough（中文）
- `docs/status/STATUS.md` — current implementation snapshot
- `docs/status/<dated>.md` — historical snapshots (immutable once committed)
- `docs/audits/<dated>.md` — audits, gap analyses, reviews (immutable once committed)
- `web/docs/` — frontend-only notes

The old flat `docs/PROJECT_STATUS.md` location stays retired in favor of `docs/status/STATUS.md`.

## Build Output and Local Artifacts

These paths are generated output or machine-local state, not source:

- `web/dist/`
- `static/dist/`
- `web/tsconfig.tsbuildinfo`
- `.pytest_cache/`
- `.coverage`
- `.venv/`
- `data/bm25_index.pkl` (BM25 persisted snapshot; recreated on lifespan warm-up if missing)

When cleaning or reorganizing the repository, prefer keeping generated files out of git and keeping durable documentation under `docs/` or `web/docs/`.
