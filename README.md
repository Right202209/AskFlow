# AskFlow

Intelligent customer service system powered by RAG (Retrieval-Augmented Generation) and Agent architecture.

AskFlow connects private knowledge bases, intent recognition, workflow routing, and ticket management into an automated loop — reducing repetitive manual work while keeping private knowledge secure and under control.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Clients (Web Chat UI)                  │
└──────────────────────────┬──────────────────────────────┘
                           │ WebSocket / HTTPS
┌──────────────────────────▼──────────────────────────────┐
│                    FastAPI Gateway                        │
│          Auth (JWT) · Rate Limiting · CORS · Trace       │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                       Services                           │
│                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │   Chat     │  │    RAG     │  │   Agent    │        │
│  │  WebSocket │  │  Retrieval │  │  Intent &  │        │
│  │  Streaming │  │  & LLM    │  │  Routing   │        │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘        │
│        │               │               │                │
│  ┌─────┴──────┐  ┌─────┴──────┐  ┌─────┴──────┐        │
│  │  Ticket    │  │ Embedding  │  │   Admin    │        │
│  │  Service   │  │  Service   │  │  Service   │        │
│  └────────────┘  └────────────┘  └────────────┘        │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                     Data Layer                           │
│    PostgreSQL · Redis · ChromaDB · MinIO                 │
└─────────────────────────────────────────────────────────┘
```

## Features

- **RAG Pipeline** — Hybrid retrieval (BM25 + vector search) with Reciprocal Rank Fusion, optional cross-encoder reranking, and LLM-generated answers with source citations
- **Agent System** — Rule + LLM dual intent classification, config-driven routing to RAG / ticket / handoff / clarification
- **Streaming Chat** — WebSocket-based real-time token streaming with heartbeat, cancel, and auto-reconnect
- **Ticket Management** — Automated ticket creation with 24-hour dedup, status tracking, and real-time WebSocket notifications
- **Configurable Embedding** — Protocol-based design supporting local (fastembed, CPU ONNX) and API (OpenAI-compatible) providers
- **Document Processing** — PDF, DOCX, Markdown, HTML parsing with configurable chunking
- **Graceful Degradation** — LLM down: return raw chunks; vector DB down: fallback to BM25; agent error: fallback to RAG
- **Observability** — Structured JSON logs with trace_id, Prometheus metrics (request count/latency, RAG queries, LLM tokens, intent distribution)
- **Admin Panel** — Document/intent/prompt management, analytics dashboard
- **Auth & Security** — JWT authentication, RBAC (user/agent/admin), Redis sliding-window rate limiting (60 req/min)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend Framework | FastAPI (async) |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 (async) |
| Vector Database | ChromaDB |
| Cache | Redis 7 |
| Object Storage | MinIO (S3-compatible) |
| LLM | OpenAI-compatible API (Ollama, vLLM, etc.) |
| Embedding | fastembed (local, CPU ONNX) / OpenAI-compatible API |
| Search | BM25 (rank_bm25 + jieba) + vector search |
| Auth | JWT (PyJWT) + bcrypt |
| Logging | structlog (JSON) |
| Metrics | prometheus-client |
| Migrations | Alembic |
| Chat UI | Vanilla HTML / JS / CSS (esbuild bundled) |

## Project Structure

```
AskFlow/
├── pyproject.toml              # Dependencies & build config
├── docker-compose.yml          # PostgreSQL, Redis, ChromaDB, MinIO
├── Dockerfile
├── Makefile                    # Dev commands
├── package.json                # Frontend tooling (esbuild)
├── alembic.ini
├── .env.example
├── alembic/                    # Database migrations
│   ├── env.py
│   └── versions/
├── static/                     # Admin Console (vanilla JS, modular ES modules)
│   ├── index.html              # SPA shell with sidebar nav
│   ├── style.css
│   ├── src/                    # Source modules (dev: loaded directly; prod: esbuild bundle)
│   │   ├── main.js             # Entry point, initializes all modules
│   │   ├── state.js            # Centralized state + localStorage persistence
│   │   ├── router.js           # SPA view switching with role guards
│   │   ├── auth.js             # Login/register, JWT management
│   │   ├── api.js              # REST API wrapper
│   │   ├── ws.js               # WebSocket client (auto-reconnect, heartbeat)
│   │   ├── toast.js            # Toast notifications + status bar
│   │   ├── dom.js              # DOM utilities
│   │   ├── events.js           # Pub/sub event bus
│   │   └── views/              # One module per page
│   │       ├── chat.js         # Conversation list + streaming chat
│   │       ├── tickets.js      # Ticket CRUD + search/filter
│   │       ├── documents.js    # Document upload + reindex (admin)
│   │       ├── intents.js      # Intent config editor (admin)
│   │       ├── analytics.js    # Metrics dashboard (admin)
│   │       └── tools.js        # RAG & intent debug forms
│   └── dist/                   # esbuild output (gitignored)
├── scripts/
│   ├── seed_data.py            # Initial data seeding
│   └── create_user.py          # User creation utility
├── tests/
│   ├── conftest.py
│   ├── unit/                   # Unit tests
│   ├── integration/
│   └── e2e/
└── src/askflow/
    ├── main.py                 # App factory + lifespan
    ├── config.py               # Pydantic Settings
    ├── dependencies.py         # DI providers
    ├── core/                   # Shared infrastructure
    │   ├── database.py         # SQLAlchemy async engine + session
    │   ├── redis.py            # Redis client pool
    │   ├── minio_client.py     # MinIO wrapper
    │   ├── security.py         # JWT + password hashing
    │   ├── auth.py             # get_current_user, require_role
    │   ├── rate_limiter.py     # Redis sliding window
    │   ├── logging.py          # structlog JSON + trace_id
    │   ├── trace.py            # contextvars trace_id
    │   ├── exceptions.py       # Custom exceptions + handlers
    │   ├── middleware.py       # CORS, trace, logging
    │   └── metrics.py          # Prometheus counters/histograms
    ├── models/                 # SQLAlchemy ORM models
    │   ├── base.py             # Base, UUID mixin, Timestamp mixin
    │   ├── user.py
    │   ├── conversation.py
    │   ├── message.py
    │   ├── ticket.py
    │   ├── document.py
    │   └── intent_config.py
    ├── schemas/                # Pydantic request/response schemas
    │   ├── common.py           # APIResponse, PaginatedResponse
    │   ├── auth.py
    │   ├── conversation.py
    │   ├── message.py
    │   ├── ticket.py
    │   ├── document.py
    │   ├── intent.py
    │   └── admin.py
    ├── repositories/           # Data access layer
    │   ├── user_repo.py
    │   ├── conversation_repo.py
    │   ├── message_repo.py
    │   ├── ticket_repo.py
    │   ├── document_repo.py
    │   └── intent_config_repo.py
    ├── chat/                   # WebSocket + session management
    │   ├── protocol.py         # Message types & serialization
    │   ├── manager.py          # Connection manager
    │   ├── session.py          # Redis-backed session store
    │   └── router.py           # WS endpoint + REST endpoints
    ├── rag/                    # Retrieval-Augmented Generation
    │   ├── llm_client.py       # OpenAI-compatible streaming client
    │   ├── vector_store.py     # ChromaDB wrapper
    │   ├── bm25.py             # BM25 index (jieba tokenization)
    │   ├── retriever.py        # Hybrid retriever + RRF fusion
    │   ├── reranker.py         # Optional cross-encoder reranker
    │   ├── prompt_builder.py   # System prompt + context template
    │   ├── service.py          # RAG query orchestration
    │   └── router.py
    ├── agent/                  # Intent classification + routing
    │   ├── intent_classifier.py # Rule + LLM dual classification
    │   ├── state.py            # Agent state dataclass
    │   ├── graph.py            # Agent graph (classify → route)
    │   ├── nodes.py            # RAG, ticket, handoff, clarify nodes
    │   ├── tools.py            # Business tools (order search, etc.)
    │   ├── service.py          # Agent orchestration service
    │   └── router.py
    ├── ticket/                 # Ticket lifecycle
    │   ├── service.py          # CRUD + status transitions
    │   ├── dedup.py            # 24h deduplication
    │   ├── notifier.py         # WebSocket notifications
    │   └── router.py
    ├── embedding/              # Document processing + vectorization
    │   ├── embedder.py         # Embedder protocol + implementations
    │   ├── parser.py           # PDF, DOCX, HTML, MD parsers
    │   ├── chunker.py          # Text chunking with overlap
    │   ├── service.py          # Index orchestration
    │   ├── router.py
    │   └── index_worker.py
    └── admin/                  # Management + analytics
        ├── service.py          # Document/intent management
        ├── analytics.py        # Aggregated statistics
        └── router.py           # Auth + admin endpoints
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- An OpenAI-compatible LLM (e.g., Ollama with `qwen2.5:7b`)

### 1. Clone & Configure

```bash
git clone <repo-url> AskFlow
cd AskFlow
cp .env.example .env
# Edit .env to configure LLM endpoint, secret key, etc.
```

### 2. Start Infrastructure

```bash
make docker-up
# Starts PostgreSQL, Redis, ChromaDB, MinIO
```

### 3. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
make install
```

### 4. Run Migrations & Seed Data

```bash
make migrate
make seed
# Creates admin user (admin / admin123) and default intent configs
```

### 5. Start the Server

```bash
make dev
# Server runs at http://localhost:8000
```

### 6. Open Chat UI

Visit `http://localhost:8000/static/index.html`, log in with `admin / admin123`, and start chatting.

## API Endpoints

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/admin/auth/register` | Register new user |
| POST | `/api/v1/admin/auth/login` | Login, get JWT token |

### Chat

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/chat/conversations` | Create conversation |
| GET | `/api/v1/chat/conversations/{id}/messages` | Get message history |
| WS | `/api/v1/chat/ws/{token}` | WebSocket chat endpoint |

### RAG

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/rag/query` | Query knowledge base |

### Agent

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/agent/classify` | Classify intent |

### Tickets

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/tickets` | Create ticket |
| GET | `/api/v1/tickets/{id}` | Get ticket |
| PUT | `/api/v1/tickets/{id}` | Update ticket |
| GET | `/api/v1/tickets` | List user tickets |

### Embedding

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/embedding/documents` | Upload & index document |
| POST | `/api/v1/embedding/documents/{id}/reindex` | Reindex document |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/admin/documents` | List documents |
| DELETE | `/api/v1/admin/documents/{id}` | Delete document |
| GET | `/api/v1/admin/intents` | List intent configs |
| POST | `/api/v1/admin/intents` | Create intent config |
| PUT | `/api/v1/admin/intents/{id}` | Update intent config |
| GET | `/api/v1/admin/analytics` | Analytics dashboard |

### Observability

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |

## WebSocket Protocol

**Client -> Server:**

```json
{
  "type": "message | cancel | ping",
  "conversation_id": "uuid",
  "content": "user input text",
  "timestamp": 1710000000
}
```

**Server -> Client:**

```json
{
  "type": "token | message_end | error | intent | source | ticket | pong",
  "conversation_id": "uuid",
  "data": {
    "content": "streaming token or full message",
    "sources": [{"title": "...", "chunk": "...", "score": 0.92}],
    "label": "faq",
    "confidence": 0.95,
    "ticket_id": "uuid"
  },
  "timestamp": 1710000000
}
```

## Degradation Strategy

| Scenario | Fallback |
|----------|----------|
| LLM unavailable | Return raw retrieved chunks with note |
| Vector DB unavailable | Fallback to BM25 keyword search |
| Agent routing error | Default to RAG pipeline |
| WebSocket disconnect | Client auto-reconnect, server restores session |

## Development

```bash
make dev         # Start dev server with hot reload
make test        # Run tests with coverage
make lint        # Run ruff linter
make format      # Auto-format code
make clean       # Clean build artifacts
make docker-up   # Start infrastructure
make docker-down # Stop infrastructure
make seed        # Seed initial data
make migrate     # Run database migrations
make build-ui    # Bundle frontend (esbuild)
make watch-ui    # Bundle frontend with file watcher
make create-user # Create user via CLI
```

## Environment Variables

See [.env.example](.env.example) for all configurable options:

- `LLM_BASE_URL` / `LLM_MODEL` — LLM endpoint configuration
- `EMBEDDING_PROVIDER` — `api` (OpenAI-compatible, default) or `local` (fastembed, CPU ONNX)
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `CHROMA_HOST` / `CHROMA_PORT` — ChromaDB connection
- `SECRET_KEY` — JWT signing key (change in production!)
- `RATE_LIMIT_PER_MINUTE` — Per-user rate limit (default: 60)

## License

MIT
