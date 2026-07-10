# Slice 02 — Audit Log + Sensitive-Data Masking

> Estimate: ~1.5 days. One DB migration (`20260709_02_audit_logs`).

## Goal

Every admin-surface mutation writes an `audit_logs` row (who / what / before →
after / when / trace id) in the **same transaction** as the mutation, and a
masking layer redacts PII (phone / email / order id) from structured logs and
from audit payloads. Stored chat messages are untouched by default; an opt-in
setting masks them at persist time.

## Current-state anchors

Mutations to audit (the complete inventory — each row below becomes one
`AUDIT_ACTIONS` entry):

- `embedding/router.py:35-89` — `POST /api/v1/embedding/documents` upload
  (`admin`/`agent`, gate at `:41`); success path `:88`.
- `embedding/router.py:92-130` — `POST .../{doc_id}/reindex` (`admin`, `:96`).
- `admin/router.py:69-85` — `DELETE /api/v1/admin/documents/{doc_id}`
  (`admin`, `:73`); note it also drops chunks via
  `EmbeddingService.delete_document` at `:84`.
- `admin/router.py:98-133` — intent create/update/delete (`admin`).
- Slice 01's prompt update/activate endpoints (land this slice *after* 01 so
  the inventory is complete — see OVERVIEW sequencing).
- `ticket/router.py:65-97` — `PUT /api/v1/tickets/{ticket_id}`: status /
  assignee / priority changes. Any authenticated user can call it, but
  `TicketService.update_ticket` (`ticket/service.py:125`) enforces
  actor-scoped rules; audit **status transitions** here (previous status is
  already captured at `ticket/router.py:77`).

Infrastructure to hook:

- `core/logging.py:8-21` — structlog processor chain
  (`merge_contextvars → add_log_level → TimeStamper → _add_trace_id →
  JSONRenderer`), configured from `setup_middleware`
  (`core/middleware.py:66`). The masking processor slots in **before**
  `JSONRenderer`.
- `core/trace.py` — `get_trace_id()`; audit rows carry it so an audit entry
  joins to its request logs (same mechanism as `core/logging.py:24-32`).
- `core/auth.py:45` — `require_role` yields the acting `User`; every audited
  endpoint already has `user` in scope.
- `models/message.py:35` — `extra: Mapped[dict | None]` (`"metadata"` JSONB)
  — precedent for the JSONB `detail` column; `chat/service.py:74-82` is where
  assistant messages persist (`msg_repo.create(..., extra=message_extra)`), and
  `:48` where user messages persist — the opt-in masking hook point.
- Existing PII-shaped pattern to reuse: `agent/tools.py` defines
  `ORDER_ID_PATTERN = r"\b[A-Z]{2,4}\d{6,}\b"` — masking must use the *same*
  pattern (import it, don't redefine) so masked ids and tool extraction agree.
- Log lines currently carrying user-adjacent data: `chat/service.py:171-178`
  (trace metadata only — safe), but prompts/questions flow through
  `logger.warning` payloads in failure paths; the processor approach covers
  all of them uniformly rather than auditing each call site.

## Design

### 1. Data model (migration `20260709_02_audit_logs`)

```
audit_logs
  id UUID PK, created_at (TimestampMixin's created_at is enough; no updated_at — rows are immutable)
  actor_id     UUID FK -> users.id NOT NULL
  actor_role   VARCHAR(20) NOT NULL          -- denormalized; role at time of action
  action       VARCHAR(50) NOT NULL          -- from AUDIT_ACTIONS
  entity_type  VARCHAR(50) NOT NULL          -- document | intent_config | prompt_template | ticket
  entity_id    UUID NULL
  detail       JSONB NULL                    -- masked before/after diff, request extras
  trace_id     VARCHAR(64) NULL
  INDEX (entity_type, entity_id), INDEX (actor_id, created_at), INDEX (action, created_at)
```

Immutable by convention: the repository exposes `create` and `list` only — no
update/delete methods. (No DB-level tamper-proofing; out of scope per
OVERVIEW.) Retention: `AUDIT_RETENTION_DAYS = 365`; a `scripts/`-style prune
is deferred until it matters — single-tenant volumes are small.

### 2. Write path: explicit service calls, in-transaction (D4)

A decorator/middleware approach was considered and rejected: the interesting
payload (before-status, doc title, version numbers) is only known *inside* the
service, and middleware commits in a separate transaction — an audit row for a
rolled-back mutation is worse than none. Instead:

```python
# core/audit.py (new)
class AuditContext:            # groups params — ≤3-positional rule
    actor: User
    action: str                # e.g. ACTION_DOCUMENT_DELETE
    entity_type: str
    entity_id: uuid.UUID | None
    detail: dict | None

async def record_audit(db: AsyncSession, ctx: AuditContext) -> None:
    # masks ctx.detail via mask_text/mask_dict, adds trace_id, db.add(...)
```

Called from the same `AsyncSession` the endpoint already holds (`get_db`,
`core/database.py`), immediately after the mutation succeeds and **before**
the response — commit/rollback is shared, so the pair is atomic. Call sites:
`admin/service.py` intent + prompt methods, `admin/router.py:76-84` (doc
delete — audit after `service.delete_document` returns `True`),
`embedding/router.py:88` (upload success) and `:129` (reindex success),
`ticket/router.py:90` (inside the `status changed` branch that already exists
for `notify_ticket_update`).

Action vocabulary (named constants in `core/audit.py`):
`document.upload`, `document.reindex`, `document.delete`, `intent.create`,
`intent.update`, `intent.delete`, `prompt.update`, `prompt.activate`,
`ticket.status_change`.

### 3. Masking: pure functions + structlog processor (D5)

`core/masking.py` (new):

```python
PHONE_PATTERN  = r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)|(?<!\d)\+?\d{1,3}[- ]?\d{3}[- ]?\d{3,4}[- ]?\d{4}(?!\d)"
EMAIL_PATTERN  = r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"
# order ids: import ORDER_ID_PATTERN from askflow.agent.tools — single source of truth
MASK_PLACEHOLDER_PHONE = "[PHONE]"
MASK_PLACEHOLDER_EMAIL = "[EMAIL]"
MASK_ORDER_KEEP_CHARS  = 4        # AB12345678 → AB…5678 (keep enough for support lookups)

def mask_text(text: str) -> str
def mask_dict(payload: dict) -> dict   # recursive, depth-capped
MASK_MAX_DEPTH = 6                     # recursion guard for nested JSONB
```

Phone matching is deliberately conservative (CN mobile + international-ish
shapes with boundaries) — false-masking numeric ids is worse than missing an
exotic format; patterns are unit-tested against the corpus in §Tests. Order
ids are **partially** masked (prefix + last `MASK_ORDER_KEEP_CHARS`) so staff
can still correlate audit entries with tickets.

Structlog integration: add `_mask_event_values` to the processor list in
`core/logging.py:9-21`, between `_add_trace_id` and `JSONRenderer`. It applies
`mask_text` to every string value in the event dict (and `mask_dict` to dict
values). Gated by `LOG_MASKING_ENABLED: bool = True` in `config.py` — the
processor is simply not installed when disabled (dev debugging).

### 4. Optional stored-message masking

`MASK_STORED_MESSAGES: bool = False` (new setting, `config.py`). When true,
`chat/service.py` applies `mask_text` to the user content persisted at
`chat/service.py:48` and the assistant content at `:75-82` — *after* the agent
has consumed the raw text (the agent needs the real order id;
`agent/tools.py` extraction runs on the in-flight value, not the stored row).
Default false: masking stored transcripts degrades the handoff/summary
features, so it is an operator choice, documented in Slice 04's checklist.

### 5. Read path (minimal, proportionate)

`GET /api/v1/admin/audit-logs?entity_type=&actor_id=&action=&limit=&offset=`
(`admin`-only), returning `PaginatedResponse` like
`admin/router.py:136-153`. `AUDIT_PAGE_LIMIT_MAX = 100`. No dedicated frontend
page this slice — the endpoint is queryable via the existing admin token; a UI
table can ride a later slice if operators ask (positioning: proportionate ops).

## Files touched

| File | Change |
|---|---|
| `models/audit_log.py` (new) | `AuditLog` model per §Design 1. |
| `alembic/versions/20260709_02_audit_logs.py` (new) | Table + three indexes. |
| `core/audit.py` (new) | `AuditContext`, `record_audit`, `ACTION_*`/entity constants. |
| `core/masking.py` (new) | Patterns, `mask_text`, `mask_dict`, structlog processor. |
| `core/logging.py` | Install masking processor (36 lines today — plenty of headroom). |
| `config.py` | `log_masking_enabled: bool = True`, `mask_stored_messages: bool = False`. |
| `repositories/audit_repo.py` (new) | `create`, `list_filtered`, `count`. |
| `admin/service.py` | Audit calls in intent + prompt mutations. |
| `admin/router.py` | Audit on doc delete (`:76-85`); `GET /audit-logs` endpoint (or in the `admin/prompt_router.py` split from Slice 01 — keep `admin/router.py` ≤ 300). |
| `embedding/router.py` | Audit on upload/reindex success paths (`:88`, `:129`). |
| `ticket/router.py` | Audit inside the status-changed branch (`:90-96`). |
| `chat/service.py` | Opt-in `mask_text` at the two persist points (`:48`, `:75-82`). |
| `schemas/audit.py` (new) | `AuditLogResponse`, list query params. |

## Tests

`tests/unit/test_masking.py` (new):
- corpus table: CN mobile (`13812345678`, `+86 138-1234-5678`), emails,
  `AB12345678` order ids → masked forms; near-misses (UUIDs, timestamps,
  ticket numbers shorter than the pattern) → untouched.
- `mask_dict` recurses, respects `MASK_MAX_DEPTH`, never mutates input.
- structlog processor masks event values end-to-end (capture with
  `structlog.testing`).

`tests/unit/test_audit_log.py` (new):
- each audited action writes a row with correct action/entity/actor and
  **masked** detail (email in a doc title comes out `[EMAIL]`).
- mutation failure → no audit row (shared-transaction property, exercised with
  the mocked session fixtures from `tests/conftest.py`).
- ticket status change audits only when status actually changed (mirrors the
  `notify_ticket_update` guard at `ticket/router.py:90`).
- list endpoint filters + pagination + `admin`-only (403 for `agent`).

`tests/unit/test_feedback_and_harness_trace.py` must stay green —
`messages.extra` semantics are untouched by default.

## Contract sync

No agent behavior change: routes, intents, tools, and harness are untouched
(masking runs at the logging/persistence boundary, after tool extraction —
§Design 4). **No AGENTS.md change.** Add the two new settings to
`.env.example` with comments; note `MASK_STORED_MESSAGES`'s handoff-quality
trade-off there and in Slice 04's checklist.

## Acceptance

- [ ] Uploading, reindexing, deleting a document; intent CRUD; prompt
      update/activate; ticket status change — each produces exactly one
      correct `audit_logs` row, joined to request logs via `trace_id`.
- [ ] A failed mutation (forced repo exception) leaves zero audit rows.
- [ ] A log line containing `user@example.com` / `13812345678` /
      `AB12345678` renders `[EMAIL]` / `[PHONE]` / `AB…5678` on stdout.
- [ ] `MASK_STORED_MESSAGES=true` masks persisted transcripts while
      `search_order` still extracts the raw order id in the same turn.
- [ ] Audit list endpoint paginates, filters, and rejects non-admin.
- [ ] All touched files ≤ 300 lines, functions ≤ 50; no new AGENTS.md drift.
- [ ] `make lint && make test` green.
