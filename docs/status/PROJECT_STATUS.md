# AskFlow Project Status

> Last updated: 2026-04-06

## Executive Summary

AskFlow has moved beyond scaffolding. The repository now contains a usable FastAPI backend, a working React frontend, Docker-based local infrastructure, and a meaningful unit-test baseline. The main outstanding work is in completeness and production hardening rather than basic application shape.

## Verified Snapshot

### Repository Shape

- Backend source files under `src/askflow/`: 78
- Frontend source files under `web/src/`: 40
- Backend unit test files under `tests/unit/`: 21
- `tests/integration/` and `tests/e2e/` are still placeholders

### Verification Run on 2026-04-06

| Command | Result | Notes |
|---------|--------|-------|
| `npm run build` in `web/` | Passed | Vite build succeeded; bundle warning remains for a large JS chunk |
| `make test` | Failed in this shell | `pytest` resolved outside the project environment; command assumes activated virtualenv or editable install |
| `.venv/bin/pytest tests/ -q --cov=src/askflow --cov-report=term-missing` | Failed | the virtualenv run surfaced failing backend tests and did not produce a clean pass during this refresh |

## Status by Area

| Area | Status | Notes |
|------|--------|-------|
| Authentication | Working | register, login, current-user endpoints; JWT-based frontend session |
| Chat | Working | conversation CRUD, history retrieval, WebSocket streaming |
| RAG | Working | BM25 + vector retrieval, answer generation, optional rerank hook |
| Agent routing | Working | classify and route to rag, ticket, handoff, tool, clarify |
| Tickets | Working | create, update, list, role-aware access |
| Embedding/documents | Working with gaps | upload, index, reindex, delete; no preview/download flow |
| Admin APIs | Working | analytics, documents, intents |
| Frontend | Working MVP | auth, chat, tickets, dashboard, documents, intents |
| Tests | Partial | unit tests exist; no integration, E2E, or frontend tests |
| DevOps/ops | Partial | compose stack exists; no CI/CD, Grafana, or deployment manifests |

## Backend Detail

### Implemented

- FastAPI app factory with versioned route groups in `src/askflow/main.py`
- Core infrastructure in `src/askflow/core/`:
  - async database session setup
  - JWT auth and password hashing
  - Redis-backed rate limiting
  - structured logging and metrics exposure
  - MinIO helpers
- Chat flows in `src/askflow/chat/`:
  - conversation create/list/rename/archive/delete
  - message history retrieval
  - WebSocket chat loop with ping, cancel, and token streaming
- RAG flows in `src/askflow/rag/`:
  - BM25 index
  - vector store integration
  - retrieval orchestration
  - LLM client and fallback behavior
- Agent flows in `src/askflow/agent/`:
  - intent classifier
  - route graph
  - mocked tool dispatch for order queries
- Ticket flows in `src/askflow/ticket/`:
  - create/read/update/list
  - notification helper for status changes
- Embedding flows in `src/askflow/embedding/`:
  - parser, chunker, embedder abstraction
  - indexing and reindexing
- Admin flows in `src/askflow/admin/`:
  - analytics aggregation
  - document and intent management

### Highest-Value Missing Backend Work

1. Prompt template CRUD and versioning
2. Retrieval metadata filtering by source, time, and tags
3. Real tool integration for `order_query`
4. User-management endpoints
5. Document preview/download endpoints
6. Async indexing pipeline via queue/worker

## Frontend Detail

### Implemented

- Auth pages:
  - `web/src/pages/Auth/LoginPage.tsx`
  - `web/src/pages/Auth/RegisterPage.tsx`
- App shell:
  - `web/src/components/layout/AppLayout.tsx`
  - role-aware sidebar navigation
- Chat workspace:
  - `web/src/pages/App/ChatPage.tsx`
  - `ConversationList`, `MessageList`, `ChatComposer`, `ChatInfoPanel`, `CreateTicketDialog`
  - `useWebSocket` with heartbeat and reconnect logic
- Ticket pages:
  - list and detail screens
  - user self-close path plus staff status updates
- Admin pages:
  - dashboard
  - document management
  - intent management

### Known Frontend Gaps

1. No toast/notification system
2. No frontend automated test runner
3. No chat conversation actions for rename/archive/delete
4. No admin ticket overview page
5. No code splitting; production build warns on chunk size
6. Document UI types do not match backend document status/schema exactly and need alignment

## Quality and Testing

### Present

- Unit coverage exists across agent, auth, chat router, chunker, config, repositories, embedding, parser, prompt builder, protocol, RAG, security, ticket service, and trace handling

### Missing

- Integration coverage for route/database boundaries
- End-to-end workflow tests
- Frontend component/hook/page tests

## Operations and Tooling

### Present

- `docker-compose.yml` for PostgreSQL, Redis, ChromaDB, and MinIO
- `Makefile` for install, dev, migrate, test, lint, and build commands
- Alembic initial migration in `alembic/versions/20260327_01_initial_schema.py`

### Missing

- CI/CD workflows
- production compose or Kubernetes manifests
- prebuilt dashboards/alerts on top of existing metrics

## Recommended Next Steps

1. Fix test execution ergonomics so `make test` reliably uses the project environment
2. Add integration tests for admin, chat WebSocket, and repository flows
3. Align frontend document types with backend document responses
4. Implement prompt template management and document preview/download APIs
5. Replace mocked tool logic with a real business integration
