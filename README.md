# AskFlow

[中文](README_zh.md)

AskFlow is an intelligent customer support system built around FastAPI, RAG, and an intent-routing agent layer. This repository contains both the backend application under `src/askflow/` and the React frontend under `web/`.

## Current Snapshot

- Backend: FastAPI app with domain modules for chat, RAG, agent routing, tickets, embeddings, and admin APIs
- Frontend: React 19 + Vite app for login/register, chat, tickets, dashboard, document management, and intent management
- Infrastructure: Docker Compose stack for PostgreSQL, Redis, ChromaDB, and MinIO
- Documentation: project docs in `docs/`, frontend-specific notes in `web/docs/`

Project status and gaps are tracked in [docs/status/PROJECT_STATUS.md](docs/status/PROJECT_STATUS.md).

## Architecture

```
React Web UI
    |
    | HTTPS / WebSocket
    v
FastAPI API
    |
    +-- chat
    +-- rag
    +-- agent
    +-- tickets
    +-- embedding
    +-- admin
    |
    +-- PostgreSQL
    +-- Redis
    +-- ChromaDB
    +-- MinIO
```

## Implemented Capabilities

- JWT authentication and role-aware backend/frontend access control
- WebSocket chat with streaming tokens, ping/pong heartbeat, cancel, and reconnect handling
- Hybrid retrieval with BM25 plus Chroma vector search
- Intent classification and route execution for `rag`, `ticket`, `handoff`, `tool`, and `clarify`
- Ticket creation, updates, user-scoped listing, and admin/agent views
- Document upload, indexing, reindexing, deletion, and MinIO-backed storage
- Admin analytics, document management, and intent configuration endpoints
- `/health` and `/metrics` endpoints for operational visibility

## Current Gaps

- Prompt template CRUD and versioning are not implemented yet
- Retrieval metadata filtering by source/time/tag is not implemented
- `order_query` still uses a mocked tool implementation
- No user-management API exists yet
- Integration, E2E, and frontend automated tests are still missing

## Repository Layout

| Path | Purpose |
|------|---------|
| `src/askflow/` | Backend source code |
| `web/src/` | React frontend source code |
| `alembic/` | Database migrations |
| `tests/` | Backend test suite |
| `scripts/` | Seed and local helper scripts |
| `docs/` | Project docs, status, and audits |
| `web/docs/` | Frontend planning and implementation notes |

For a fuller directory map, see [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md).

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker with Compose support
- An OpenAI-compatible LLM endpoint for chat and, optionally, embeddings

### 1. Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
make install
make install-web
```

### 3. Configure the Environment

```bash
cp .env.example .env
```

`.env.example` contains the full set of application defaults. The main values you will usually adjust are:

- `DATABASE_URL`
- `REDIS_URL`
- `CHROMA_HOST` / `CHROMA_PORT`
- `MINIO_*`
- `LLM_*`
- `EMBEDDING_*`
- `CORS_ORIGINS`

### 4. Start Local Infrastructure

```bash
make docker-up
```

This starts:

- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`
- ChromaDB on `localhost:8100`
- MinIO API on `localhost:9000`
- MinIO console on `localhost:9001`

### 5. Apply Migrations and Seed Data

```bash
make migrate
make seed
```

Seed data creates:

- `admin / admin123`
- `user1 / user123`

### 6. Run the Backend

```bash
make dev
```

Backend URLs:

- API: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`
- Metrics: `http://localhost:8000/metrics`

### 7. Run the Frontend

```bash
make dev-web
```

Frontend URL:

- App: `http://localhost:5173`

## Common Commands

| Command | Description |
|---------|-------------|
| `make install` | Install backend dependencies in editable mode |
| `make install-web` | Install frontend dependencies |
| `make docker-up` | Start PostgreSQL, Redis, ChromaDB, and MinIO |
| `make docker-down` | Stop local infrastructure |
| `make migrate` | Apply Alembic migrations |
| `make migrate-create msg="..."` | Create a new migration |
| `make seed` | Seed default users and intents |
| `make dev` | Start the FastAPI dev server |
| `make dev-web` | Start the Vite dev server |
| `make test` | Run backend tests |
| `make lint` | Run Ruff checks |
| `make format` | Format backend code with Ruff |
| `make build-web` | Build the frontend for production |

## API Surface

The backend mounts these route groups:

| Area | Prefix |
|------|--------|
| RAG | `/api/v1/rag` |
| Embedding | `/api/v1/embedding` |
| Chat | `/api/v1/chat` |
| Agent | `/api/v1/agent` |
| Tickets | `/api/v1/tickets` |
| Admin | `/api/v1/admin` |

Representative endpoints:

- `POST /api/v1/admin/auth/login`
- `GET /api/v1/chat/conversations`
- `WS /api/v1/chat/ws/{token}`
- `POST /api/v1/rag/query`
- `POST /api/v1/tickets`
- `GET /api/v1/admin/analytics`
- `POST /api/v1/embedding/documents`

Use `/docs` for the complete schema.

## Verification Notes

- `npm run build` in `web/` passes as of 2026-04-06
- `make test` assumes project dependencies are available on your shell `PATH`; activate `.venv` or install the project first with `make install`
- a direct virtualenv pytest run surfaced backend test failures, so the backend suite should not currently be treated as green

## Documentation

- [docs/README.md](docs/README.md) - project documentation index
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) - repository layout and file placement rules
- [docs/status/PROJECT_STATUS.md](docs/status/PROJECT_STATUS.md) - current implementation status
- [docs/audits/PRD_AUDIT.md](docs/audits/PRD_AUDIT.md) - PRD-to-code audit
- [web/docs/README.md](web/docs/README.md) - frontend documentation index
- [PRD.md](PRD.md) - product requirements document

## License

MIT
