# AskFlow PRD Audit

> Last reviewed: 2026-04-06

This audit compares the current repository against `PRD.md`. It focuses on what is implemented in code, not on aspirational comments or old roadmap text.

Legend:

- `Complete` - materially implemented in the repository
- `Partial` - some support exists, but the PRD expectation is not fully met
- `Missing` - not implemented or not exposed yet

## Overall Assessment

The repository covers the core MVP loop:

- users can authenticate
- chat can stream over WebSocket
- the agent can classify and route
- RAG can retrieve and answer
- tickets can be created and tracked
- admins can manage documents, intents, and analytics

The biggest remaining gaps are product completeness and production-readiness, not base architecture.

## Requirement Matrix

| PRD Area | Status | Evidence | Notes |
|----------|--------|----------|-------|
| Smart Q&A with hybrid retrieval | Complete | `src/askflow/rag/retriever.py`, `src/askflow/rag/service.py` | BM25 plus vector retrieval is implemented |
| Multi-turn chat context | Complete | `src/askflow/chat/session.py`, `src/askflow/chat/router.py` | session history is passed into processing |
| Source-aware answers | Complete | `src/askflow/rag/service.py`, WebSocket `source` events | sources are returned to the client |
| Retrieval filtering by source/time/tag | Missing | no filter parameters in RAG router/service | PRD requirement not exposed |
| Intent classification | Complete | `src/askflow/agent/intent_classifier.py` | rule plus model path exists |
| Route execution across multiple flows | Complete | `src/askflow/agent/graph.py`, `src/askflow/agent/nodes.py` | rag, ticket, handoff, tool, clarify routes exist |
| Business tool integration | Partial | `src/askflow/agent/tools.py` | tool path exists, but `search_order` is mocked |
| Streaming chat with cancel and heartbeat | Complete | `src/askflow/chat/router.py`, `web/src/hooks/useWebSocket.ts` | implemented on both backend and frontend |
| Automatic ticket creation/handling | Partial | ticket APIs and dialog exist | manual creation flow is implemented; deeper automation remains limited |
| Ticket deduplication and state management | Complete | `src/askflow/ticket/service.py`, `src/askflow/ticket/dedup.py` | implemented in backend |
| Document ingestion and indexing | Complete | `src/askflow/embedding/` | upload, parse, chunk, embed, reindex supported |
| Async indexing via queue/worker | Missing | request-time indexing only | PRD target remains unimplemented |
| Admin document management | Complete | `src/askflow/admin/router.py`, `web/src/pages/Admin/DocumentsPage.tsx` | CRUD subset is exposed |
| Intent config management | Complete | `src/askflow/admin/router.py`, `web/src/pages/Admin/IntentsPage.tsx` | list/create/update exist; frontend delete UI missing |
| Prompt template management | Missing | no prompt admin endpoints or models | key PRD gap |
| Analytics dashboard | Partial | `src/askflow/admin/analytics.py`, `web/src/pages/Admin/DashboardPage.tsx` | basic counts and distributions exist, deeper ops metrics do not |
| RBAC and auth | Complete | `src/askflow/core/auth.py`, `src/askflow/core/security.py` | implemented |
| Request limiting | Complete | `src/askflow/core/rate_limiter.py` | implemented |
| Audit logs and desensitization | Missing | no audit store/query flow, no desensitization layer | PRD gap |
| Health and metrics exposure | Complete | `/health`, `/metrics`, `src/askflow/core/metrics.py` | implemented |
| Frontend application shell | Complete | `web/src/router/index.tsx`, `web/src/components/layout/AppLayout.tsx` | auth/app/admin route groups exist |
| Automated backend tests | Partial | 21 unit test files | integration and E2E suites are empty |
| Automated frontend tests | Missing | no runner/config/tests | PRD quality target not met |
| CI/CD and deployment artifacts | Missing | no workflow or deployment manifests | infra remains local-dev focused |

## Notable Implementation Drift

These items were inconsistent before the doc refresh and are worth keeping explicit:

1. Frontend technology: the repository uses React 19 + Vite, not Vue 3
2. Agent orchestration: the repository uses a custom `AgentGraph`, not LangGraph
3. Queue-based indexing: the PRD still targets async worker flows, but indexing is currently synchronous

## Highest-Priority Gaps

1. Prompt template CRUD and versioning
2. Retrieval metadata filtering
3. Real business integration behind the tool route
4. Document preview/download APIs
5. User-management APIs
6. Integration, E2E, and frontend automated tests
7. CI/CD, dashboards, and production deployment assets

## Recommended Follow-Up

- Treat the current codebase as an MVP-complete foundation
- Prioritize missing operator and admin workflows before expanding new product surface
- Keep `PRD.md`, `docs/status/PROJECT_STATUS.md`, and this audit in sync whenever architecture decisions change
