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
| Chat UI | React 19 + Vite + shadcn/ui (under construction in `web/`) |

> **Note**: The frontend is being rebuilt with React 19 + Vite + shadcn/ui in the `web/` directory. The legacy vanilla JS frontend has been removed. API docs are available at `/docs`.

## Project Structure

```
AskFlow/
├── pyproject.toml              # Dependencies & build config
├── docker-compose.yml          # PostgreSQL, Redis, ChromaDB, MinIO
├── Dockerfile
├── Makefile                    # Dev commands
├── alembic.ini
├── .env.example
├── alembic/                    # Database migrations
│   ├── env.py
│   └── versions/
├── web/                       # Frontend (React 19 + Vite, under construction)
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
# API docs at http://localhost:8000/docs
```

## API Endpoints

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/admin/auth/register` | Register new user |
| POST | `/api/v1/admin/auth/login` | Login, get JWT token |
| GET | `/api/v1/admin/auth/me` | Get current user info |

### Chat

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/chat/conversations` | Create conversation |
| GET | `/api/v1/chat/conversations` | List conversations |
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
| DELETE | `/api/v1/admin/intents/{id}` | Delete intent config |
| GET | `/api/v1/admin/tickets` | List all tickets (admin/agent) |
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
  "type": "token | message_end | error | intent | source | ticket | handoff | pong",
  "conversation_id": "uuid",
  "data": {
    "content": "streaming token or full message",
    "sources": [{"title": "...", "chunk": "...", "score": 0.92}],
    "label": "faq",
    "confidence": 0.95,
    "ticket_id": "uuid",
    "transferred": true
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

<!-- AUTO-GENERATED from Makefile — do not edit manually -->

| Command | Description |
|---------|-------------|
| `make dev` | Start dev server with hot reload (port 8000) |
| `make test` | Run tests with coverage |
| `make lint` | Run ruff linter + format check |
| `make format` | Auto-format code with ruff |
| `make clean` | Clean build artifacts and caches |
| `make install` | Install Python dependencies (editable) |
| `make docker-up` | Start infrastructure (PostgreSQL, Redis, ChromaDB, MinIO) |
| `make docker-down` | Stop infrastructure |
| `make migrate` | Run database migrations |
| `make migrate-create msg="..."` | Create new migration |
| `make seed` | Seed initial data |
| `make create-user` | Create user via CLI |
| `make install-web` | Install frontend dependencies |
| `make dev-web` | Start frontend dev server (port 5173) |
| `make build-web` | Build frontend for production |

<!-- /AUTO-GENERATED -->

## Environment Variables

<!-- AUTO-GENERATED from .env.example — do not edit manually -->

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| **Application** | | | |
| `APP_NAME` | No | `AskFlow` | Application display name |
| `APP_ENV` | No | `development` | Environment (`development` / `production`) |
| `DEBUG` | No | `true` | Enable debug mode |
| `SECRET_KEY` | **Yes** | — | JWT signing key (change in production!) |
| **Database** | | | |
| `DATABASE_URL` | **Yes** | — | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| **Redis** | | | |
| `REDIS_URL` | **Yes** | — | Redis connection string |
| **MinIO** | | | |
| `MINIO_ENDPOINT` | **Yes** | — | MinIO endpoint (`host:port`) |
| `MINIO_ACCESS_KEY` | **Yes** | — | MinIO access key |
| `MINIO_SECRET_KEY` | **Yes** | — | MinIO secret key |
| `MINIO_BUCKET` | No | `askflow-docs` | MinIO bucket name |
| `MINIO_SECURE` | No | `false` | Use HTTPS for MinIO |
| **ChromaDB** | | | |
| `CHROMA_HOST` | **Yes** | — | ChromaDB host |
| `CHROMA_PORT` | No | `8100` | ChromaDB port |
| **LLM** | | | |
| `LLM_BASE_URL` | **Yes** | — | OpenAI-compatible API base URL |
| `LLM_API_KEY` | **Yes** | — | LLM API key |
| `LLM_MODEL` | No | `qwen2.5:7b` | LLM model name |
| `LLM_MAX_TOKENS` | No | `2048` | Max tokens per response |
| `LLM_TEMPERATURE` | No | `0.7` | Sampling temperature |
| **Embedding** | | | |
| `EMBEDDING_PROVIDER` | No | `api` | `api` (OpenAI-compatible) or `local` (fastembed, CPU ONNX) |
| `EMBEDDING_MODEL` | No | `BAAI/bge-small-en-v1.5` | Embedding model name |
| `EMBEDDING_API_URL` | No | — | Embedding API base URL (when provider=api) |
| `EMBEDDING_API_KEY` | No | — | Embedding API key (when provider=api) |
| `EMBEDDING_DIMENSION` | No | `384` | Embedding vector dimension |
| **Auth** | | | |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | No | `1440` | Token expiration (minutes) |
| **Rate Limiting** | | | |
| `RATE_LIMIT_PER_MINUTE` | No | `60` | Per-user rate limit |
| **CORS** | | | |
| `CORS_ORIGINS` | No | `["http://localhost:5173"]` | Allowed origins (JSON array) |

<!-- /AUTO-GENERATED -->

## License

MIT
