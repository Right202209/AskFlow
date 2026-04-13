# AskFlow Project Structure

> Last updated: 2026-04-06

This document describes the repository as it exists today and records where future files should live.

## Top-Level Layout

| Path | Purpose | Notes |
|------|---------|-------|
| `src/askflow/` | Backend source | FastAPI app and domain modules |
| `web/` | Frontend app | React + Vite project |
| `alembic/` | Database migrations | Alembic environment and version files |
| `tests/` | Backend tests | `unit/`, `integration/`, `e2e/` |
| `scripts/` | Developer scripts | seed data, create user, local runner |
| `docs/` | Project documentation | status, audits, structure, future architecture notes |
| `web/docs/` | Frontend docs | route, page, and stack notes |
| `static/` | Build output area | not a source directory |
| `skills/` | Repository-local Codex skills | not application runtime code |

Root-level files should be limited to:

- entry docs: `README.md`, `README_zh.md`, `PRD.md`
- repository config: `pyproject.toml`, `Makefile`, `Dockerfile`, `docker-compose.yml`, `alembic.ini`
- environment template: `.env.example`

## Backend Layout

`src/askflow/` is organized around shared infrastructure plus business domains.

| Path | Responsibility |
|------|----------------|
| `src/askflow/main.py` | app factory and route mounting |
| `src/askflow/config.py` | settings loading |
| `src/askflow/dependencies.py` | dependency helpers |
| `src/askflow/core/` | auth, database, logging, metrics, middleware, Redis, MinIO helpers |
| `src/askflow/models/` | SQLAlchemy models |
| `src/askflow/schemas/` | Pydantic request/response models |
| `src/askflow/repositories/` | persistence access layer |
| `src/askflow/chat/` | conversation APIs, WebSocket handling, session management |
| `src/askflow/rag/` | retriever, vector store, reranker, LLM service |
| `src/askflow/agent/` | intent classifier, graph, routing nodes, tools |
| `src/askflow/ticket/` | ticket lifecycle and notifications |
| `src/askflow/embedding/` | parsing, chunking, embedding, document indexing |
| `src/askflow/admin/` | admin APIs and analytics |

Placement rules:

- cross-cutting infrastructure goes in `core/`
- domain-specific service logic stays inside its own domain package
- database models stay in `models/`
- API contracts stay in `schemas/`
- data-access logic goes into `repositories/`

## Frontend Layout

`web/` contains both the runnable frontend and its implementation notes.

| Path | Responsibility |
|------|----------------|
| `web/src/pages/` | route-level screens |
| `web/src/components/` | reusable UI components |
| `web/src/router/` | router definition and guards |
| `web/src/services/` | HTTP API wrappers and JWT helpers |
| `web/src/stores/` | Zustand stores |
| `web/src/hooks/` | custom hooks such as WebSocket integration |
| `web/src/types/` | TypeScript interfaces and API types |
| `web/src/styles/` | global styles and design tokens |
| `web/docs/` | frontend-only documentation |

Placement rules:

- page containers go under `pages/`
- reusable UI fragments go under `components/`
- request code stays in `services/`
- app state stays in `stores/`
- frontend documentation stays in `web/docs/`

## Testing and Scripts

| Path | Purpose |
|------|---------|
| `tests/unit/` | current backend unit coverage |
| `tests/integration/` | reserved for DB/API integration tests |
| `tests/e2e/` | reserved for end-to-end tests |
| `scripts/seed_data.py` | create default users and intent configs |
| `scripts/create_user.py` | CLI user creation |
| `scripts/run.sh` | local helper script |

## Documentation Placement

Use these locations for future documentation:

- `docs/README.md` - documentation index
- `docs/PROJECT_STRUCTURE.md` - structure and placement rules
- `docs/status/` - status snapshots, milestones, rollout notes
- `docs/audits/` - audits, reviews, gap analyses
- `web/docs/` - frontend-only notes

The old flat `docs/PROJECT_STATUS.md` location should stay retired in favor of `docs/status/PROJECT_STATUS.md`.

## Build Output and Local Artifacts

These paths are generated output or machine-local state, not source:

- `web/dist/`
- `static/dist/`
- `web/tsconfig.tsbuildinfo`
- `.pytest_cache/`
- `.coverage`
- `.venv/`

When cleaning or reorganizing the repository, prefer keeping generated files out of git and keeping durable documentation under `docs/` or `web/docs/`.
