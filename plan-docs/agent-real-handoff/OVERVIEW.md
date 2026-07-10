# Agent + Real Handoff

**Spine:** make AskFlow unmistakably good at the customer-service loop — the
agent collects what it needs across turns, and when it can't help, it performs a
*warm* human handoff instead of dropping the user into a black hole.

This initiative fixes the two halves that are broken today, in dependency order.

## The two broken halves (grounded in current code)

**A. The agent can't hold a slot.** `agent/tools.py::execute_tool`
(`tools.py:221-234`) regex-matches an order id via `ORDER_ID_PATTERN`
(`tools.py:22`) and, when it's missing, **hard-returns guidance text and
forgets**. The user replies `AB12345678` on the next turn and it is
re-classified from scratch — nothing remembers a tool was waiting on that value.
Real users rarely paste a clean id up front, so the order flow routinely
dead-ends on turn one.

**B. Handoff is a black hole.** `agent/nodes.py::handoff_node`
(`nodes.py:117-138`) sets `should_handoff=True`, flips the conversation to
`transferred` via `ConversationRepo.update_status`, and returns fixed copy
promising *"your summary and transcript will be handed to an agent."* But **no
summary is generated, no queue exists, no staff UI can see it, and there is no
path back**. `chat/service.py` (`service.py:211-217`) just pushes a
`handoff {transferred: true}` frame. STATUS.md risk #6 calls it a "black hole";
the promised copy is a claim the code does not back up.

**B′. Worse: the transfer is cosmetic.** `process_user_message` never checks
`conversation.status` — after a "transfer", the **next user message goes
straight back to the AI**. `transferred` changes a DB field and nothing else.
Slice 02 §Design 2 adds the message gate that makes the status mean something.

## Scope

In scope:
- Slice 01 — order-slot filling (multi-turn tool parameter collection).
- Slice 02 — real handoff protocol (summary → queue → staff inbox → timeout → return).
- Slice 03 — AGENTS.md contract sync + end-to-end verification.

Out of scope (deliberately — respect the product positioning in CLAUDE.md,
"single-tenant, self-hosted reference implementation … do not add multi-tenant
scaffolding"):
- SLA-per-priority engine (separate `05-16-sla-engine` task).
- Agent presence/routing algorithms, skill-based assignment.
- Real-time agent↔user WebSocket chat channel beyond a minimal reply path.

## Sequencing & rationale

```
01-slot-filling ──▶ 02-handoff-protocol ──▶ 03-contract-and-verification
   (~1 day)              (flagship)              (sync + e2e)
```

Slice 01 goes first on purpose: it is small, self-contained, needs **no DB
migration** (reuses the existing `conversations.metadata` JSONB column,
`conversation.py:31`), retires a tracked task
(`05-16-search-order-clarify-fallback`), and delivers a visible win (multi-turn
order lookup) before the larger handoff investment. It also establishes the
conversation-scoped-state pattern (persist in Postgres/Redis, never a process
dict) that Slice 02 reuses.

Slice 02 is the flagship — it turns "handoff" from a boolean into a workflow and
is the `05-16-handoff-protocol` task.

## Cross-cutting constraints (apply to every slice)

1. **No process-local conversation state.** Anything conversation-scoped goes in
   Postgres or Redis. A process dict breaks under multiple workers — the same
   trap as the known `_cancel_flags` gap (CLAUDE.md "Concurrency and consistency").
2. **Contract-with-code.** Every tool/route/harness/handoff change updates
   `AGENTS.md` in the same commit (§3 tools, §4 harness, §5 handoff).
3. **Tickets only via `TicketRepo.create`.** Any new path that creates a ticket
   (e.g. handoff-timeout escalation) must go through `TicketRepo.create`
   (`ticket_repo.py:24`) to inherit `INSERT … ON CONFLICT` dedup — never raw
   `db.add(Ticket(...))`.
4. **Hard code-quality limits** (global rules): functions ≤ 50 lines, files
   ≤ 300 lines, nesting ≤ 3, ≤ 3 positional params, no magic numbers. `nodes.py`
   is already 215 lines and `tools.py` 242 — Slice 01/02 must extract helpers
   rather than inflate these files.

## Resolved design decisions (rationale in the slice docs)

| # | Decision | Where |
|---|---|---|
| D1 | Slot state lives on `conversations.metadata` JSONB — durable, no migration; Redis session store rejected (24h TTL + 20-entry trim would silently drop control state). | 01 §anchors |
| D2 | `_ensure_conversation` returns the `Conversation` object — one refactor gives both the pending-slot read (01) and the status gate (02) with zero extra queries. | 01 §Design 2 |
| D3 | Resume path carries `RESUME_SLOT_CONFIDENCE=0.9` so the harness low-confidence override (`harness.py:122`) can't rewrite the resume to `clarify`; rails stay on otherwise. | 01 §Design 4 |
| D4 | Handoff summary is generated synchronously with an 8s timeout; on failure the transfer proceeds transcript-only. Never block the transfer on the LLM. | 02 §Design 1 |
| D5 | While `transferred`, user messages persist and reach staff but do **not** dispatch to the agent. | 02 §Design 2 |
| D6 | Dedicated `handoff_session` table (live claim ≠ async ticket); one open session per conversation via partial unique index, mirroring the `uniq_open_user_title` precedent. | 02 §Design 3 |
| D7 | Cross-worker delivery via Redis channel `askflow:chat:push` + per-worker forwarder into the existing `manager.send_to_user`; non-owning workers no-op — correct by construction. | 02 §Design 5 |
| D8 | Staff replies persist as new `MessageRole.staff` but mirror into the Redis session as `assistant` — otherwise the harness's `allowed_history_roles` filter would make the AI resume blind to everything the human said. | 02 §Design 6 |
| D9 | Claim is a conditional `UPDATE … WHERE status='queued'` (409 for the race loser); timeout sweep uses `FOR UPDATE SKIP LOCKED` so multi-worker sweeps can't double-escalate. | 02 §Design 4/7 |

## Docs in this initiative

- [`01-slot-filling/PLAN.md`](01-slot-filling/PLAN.md)
- [`02-handoff-protocol/PLAN.md`](02-handoff-protocol/PLAN.md)
- [`03-contract-and-verification/PLAN.md`](03-contract-and-verification/PLAN.md)
