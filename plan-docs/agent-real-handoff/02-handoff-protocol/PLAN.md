# Slice 02 — Real Handoff Protocol

> Retires tracked task `05-16-handoff-protocol`. The flagship slice.
> Estimate: ~4-6 person-days. One DB migration + a new staff UI route.

## Goal

Turn handoff from a boolean into a workflow: **transfer produces a summary,
lands in a queue a human can see and claim, times out safely, and has a path
back to the user** — delivering on the copy `handoff_node` already promises.

## Current-state anchors

- `agent/nodes.py::handoff_node` `nodes.py:117-138` — sets `should_handoff`,
  flips status to `transferred`, returns fixed copy. No summary, no queue.
- **`chat/service.py::process_user_message` never checks `conversation.status`**
  — after a "transfer", the next user message goes straight back to the AI.
  Today's transfer is cosmetic; §Design 2 adds the gate.
- `chat/manager.py::ConnectionManager` — keeps `_user_connections:
  dict[user_id → set[connection_id]]` and already exposes
  **`send_to_user(user_id, message)`**. Delivery to a live user is one call
  *within a process*; cross-worker needs the pub/sub bridge in §Design 5.
- `agent/service.py:87-111` — `_route_map_invalidate_listener` is the existing
  per-worker Redis-subscriber pattern the bridge mirrors (start/stop in lifespan).
- `chat/protocol.py::ServerMessageType` — currently
  `{token, message_end, error, intent, source, ticket, handoff, pong}`.
- `models/message.py::MessageRole` — `{user, assistant, system}`. **Harness trap**:
  `allowed_history_roles={"user","assistant"}` (AGENTS.md §4.1) silently drops
  any other role from agent history — see §Design 6 for why staff replies must
  be mirrored as `assistant` in the session store.
- `repositories/ticket_repo.py:24` — `TicketRepo.create` with `ON CONFLICT`
  dedup: the mandatory path for timeout escalation.
- `chat/session.py` — Redis history, `MAX_HISTORY=20`, 24h TTL → **not** a
  source for the handoff payload's `recent_messages` (use `MessageRepo`).
- Slice 01 already refactored `_ensure_conversation` to return the
  `Conversation` object — the status gate reads `conv.status` for free.

## Design

### 1. `HandoffPayload` — summary on transfer

In `handoff_node` (summary logic extracted to a new `agent/handoff.py` to keep
`nodes.py` under the 300-line cap):

```python
{
  "summary": str,                    # LLM-generated; see failure policy below
  "recent_messages": list[dict],     # last HANDOFF_RECENT_MESSAGES turns, from MessageRepo (durable)
  "intent_history": list[str],       # intents seen on the path
  "user_meta": {"user_id", "role", "session_start_at"},
  "ticket_refs": list[str],
}
```

**Summary policy (decided):** generate synchronously on the transfer turn with a
hard timeout `HANDOFF_SUMMARY_TIMEOUT_S = 8`; on timeout/LLM error, enqueue a
transcript-only payload (`summary = ""` + flag `summary_failed`). The transfer
must never block or fail on the summary. (Async-summarize-after-enqueue is the
alternative; rejected for v1 — it complicates the inbox's "what do I see when I
claim" contract for marginal latency gain.)

### 2. Message gating while transferred (fixes the cosmetic transfer)

In `process_user_message`, right after `_ensure_conversation`:

```
if conv.status == transferred:
    persist user Message → publish to push channel (staff sees it live if viewing)
    → send lightweight ack frame (handoff_update {status}) → SKIP agent dispatch
```

The user's messages keep landing in the conversation (staff inbox reads history
via MessageRepo), but the AI stays silent while a human owns the session. This
gate is what makes `transferred` mean something.

### 3. `handoff_session` table (the queue)

A handoff is a **live claim**, not an async work item — dedicated table, not a
`tickets` overload (lifecycles diverge: claim/return vs. resolve).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `conversation_id` | UUID FK | one *open* session per conversation (partial unique index, mirroring the `uniq_open_user_title` precedent) |
| `status` | enum | `queued / claimed / resolved / returned / timed_out` |
| `summary` | Text | `""` when summary failed |
| `payload` | JSONB | full `HandoffPayload` |
| `assignee` | String \| null | staff user id when claimed |
| `created_at` / `claimed_at` / `closed_at` | timestamptz | |

**One migration** (`alembic/versions/2026MMDD_01_handoff_session.py`, matching
the `20260519_01_…` naming) containing: the table, the new
`handoff_session_status` enum, the partial unique index, **and**
`ALTER TYPE message_role ADD VALUE 'staff'` (§6). Hand-written — autogenerate
misses enums and partial indexes (CLAUDE.md schema-change workflow; the
`20260519_01` file is the worked example). Note: `ADD VALUE` cannot run inside a
transaction on older Postgres — use alembic's `autocommit_block()`.

### 4. Staff inbox — endpoints + UI

Backend under `/api/v1/admin` (role-gated `agent`/`admin`, mirroring
`admin/router.py` style):

| Endpoint | Behavior |
|---|---|
| `GET /admin/handoffs?status=` | paginated list (pattern: `GET /admin/tickets`) |
| `GET /admin/handoffs/{id}` | session + payload + conversation history (MessageRepo) |
| `POST /admin/handoffs/{id}/claim` | **atomic**: `UPDATE … SET status='claimed', assignee=:me, claimed_at=now() WHERE id=:id AND status='queued' RETURNING *`; 0 rows → 409 Conflict (two staff racing) |
| `POST /admin/handoffs/{id}/reply` | assignee-only (403 otherwise): persist staff Message → mirror to session store → publish push event |
| `POST /admin/handoffs/{id}/resolve` | close session (`resolved`/`returned`) + warm return (§7) |

Frontend: staff-only route `/admin/handoffs` guarded by `RequireRole`
(`agent`/`admin`) in `web/src/router/index.tsx`, following the existing admin
pages + `adminStore` pattern: queue list with claim buttons → detail view with
transcript, summary, reply box, resolve/return actions.

### 5. Delivery — how a staff reply reaches the user's WebSocket

Staff REST request may land on a different worker than the one holding the
user's WS connection. Bridge (new `chat/push.py`, ~40 lines, mirrors
`_route_map_invalidate_listener`):

- Publisher: reply/resolve endpoints publish
  `{user_id, server_message}` to Redis channel `askflow:chat:push`.
- Per-worker subscriber (started/stopped in `main.py` lifespan alongside the
  route-map subscriber): on message → `manager.send_to_user(user_id, msg)`.
  Workers not holding a connection for that user simply no-op — **multi-worker
  correct by construction**, no registry needed.

New `ServerMessageType` members (keep the existing `handoff` frame for
back-compat on the initial transfer):

- `staff_message` — `{content, staff_name}`: a human reply.
- `handoff_update` — `{status: queued|claimed|resolved|returned|timed_out, ticket_id?}`.

Frontend handles both in `web/src/hooks/useWebSocket.ts` + renders in
`chatStore.ts` (staff bubbles styled distinctly; status banners for
claimed/resolved) — the "REST and WS shapes stay in sync" invariant.

### 6. Staff message persistence — role + the harness history trap

- DB truth: `Message(role=MessageRole.staff)` (new enum value, migration §3) so
  rendering, audit, and analytics can distinguish humans from the model.
- **Session-store mirror as `assistant`**: the harness drops history roles
  outside `{user, assistant}` (`history_role_dropped`, AGENTS.md §4.1). If staff
  turns entered agent history as `staff`, the AI would resume after warm return
  **blind to everything the human said**. So `reply` writes the Redis session
  copy with role `assistant` — semantically right (they were answers to the
  user) and no harness policy change needed.

### 7. Timeout fallback + warm return

- **Sweep**: lifespan background task, every `HANDOFF_SWEEP_INTERVAL_S`, claims
  expired rows with `SELECT … WHERE status='queued' AND created_at < now() - :timeout
  FOR UPDATE SKIP LOCKED` — multiple workers can run the sweep without double
  escalation. Each hit: create escalation ticket **via `TicketRepo.create`**
  (constraint #3 — inherits dedup), mark `timed_out`, push
  `handoff_update {status: timed_out, ticket_id}`, increment a
  `HANDOFF_TIMEOUT_COUNT` metric.
- **Warm return**: `resolve` sets `Conversation.status` back to `active` (AI
  resumes, with staff turns visible per §6) or `closed`; `returned` covers
  "human hands back to AI" explicitly. Push `handoff_update` so the UI flips out
  of "human mode".

### Constants (no magic numbers)

```python
HANDOFF_PICKUP_TIMEOUT_MIN = 10    # settings-driven
HANDOFF_RECENT_MESSAGES = 10
HANDOFF_SWEEP_INTERVAL_S = 60
HANDOFF_SUMMARY_TIMEOUT_S = 8
```

## Files touched

| Area | File | Change |
|---|---|---|
| Model | `models/handoff.py` (new) | `HandoffSession` + status enum |
| Model | `models/message.py` | `MessageRole.staff` |
| Migration | `alembic/versions/2026MMDD_01_handoff_session.py` (new) | table + 2 enum ops + partial unique index (hand-written) |
| Repo | `repositories/handoff_repo.py` (new) | create / list / get / claim (conditional) / close / sweep-expired |
| Schema | `schemas/handoff.py` (new) | request/response models |
| Agent | `agent/handoff.py` (new) + `agent/nodes.py` | payload build + summary w/ timeout; `handoff_node` enqueues |
| Chat | `chat/service.py` | transferred-status gate after `_ensure_conversation` |
| Chat | `chat/push.py` (new) | Redis pub/sub bridge → `manager.send_to_user` |
| Protocol | `chat/protocol.py` | `staff_message`, `handoff_update` |
| Admin | `admin/router.py` + `admin/service.py` | 5 handoff endpoints |
| Lifespan | `main.py` | start/stop push subscriber + timeout sweep |
| Frontend | `router/index.tsx`, `pages/admin/Handoffs.tsx` (new), `services/`, `stores/adminStore.ts`, `hooks/useWebSocket.ts`, `stores/chatStore.ts` | inbox UI + staff-bubble/status rendering |
| Contract | `AGENTS.md` §5 | minimal → real protocol |

## Tests

- `tests/unit/test_handoff_repo.py` — transitions; **claim race** (two claims,
  one 409); partial-unique one-open-session rule.
- `tests/unit/test_handoff_node.py` — payload built; summary timeout →
  transcript-only + `summary_failed`; enqueue called.
- `tests/unit/test_chat_transferred_gate.py` — status `transferred` → message
  persisted, agent **not** dispatched, ack frame sent.
- `tests/unit/test_chat_push_bridge.py` — publish → subscriber forwards via
  `send_to_user`; no-op for unknown user.
- `tests/unit/test_handoff_timeout.py` — expired → ticket via `TicketRepo.create`,
  `timed_out`, event pushed.
- `tests/integration/test_handoff_flow.py` — transfer → queued row → claim →
  staff reply (DB role `staff`, session mirror `assistant`) → resolve →
  conversation `active` + warm-return event.
- Gates: `make test`, `make lint`, `cd web && npm run build`.

## Contract sync

Rewrite `AGENTS.md` §5 to the implemented protocol: payload shape + summary
failure policy, session lifecycle (incl. one-open-per-conversation), the
transferred-message gate, staff-role history mirroring, timeout behavior, warm
return. Update STATUS.md §2 Handoff row (🔴 → ✅), §5 risk #6 resolved, §6 task
done.

## Acceptance

- [ ] Transfer generates a summary (or transcript-only fallback) and a `queued` row.
- [ ] While transferred, user messages persist + reach staff, and the AI does **not** answer.
- [ ] Inbox lists/claims/replies/resolves; claim is race-safe (409 loser); reply is assignee-only.
- [ ] Staff reply reaches the user live across workers via the push bridge.
- [ ] Unclaimed past timeout escalates via `TicketRepo.create`, marks `timed_out`, notifies user.
- [ ] Warm return: conversation back to `active`; AI's next answer can see staff turns (session-mirror check).
- [ ] `AGENTS.md` §5 + STATUS.md updated in the same commit; all state in Postgres/Redis.
- [ ] Backend + frontend gates green; touched files within code-quality limits.
