# Slice 01 — Order-Slot Filling

> Retires tracked task `05-16-search-order-clarify-fallback`.
> Estimate: ~1 day. No DB migration.

## Goal

When a tool needs a parameter it can't extract (today: the order id), the agent
**asks for it, remembers it is waiting, and resumes** when the user replies —
instead of hard-returning guidance text and forgetting.

Success looks like:

```
User: 我的订单到哪了?
Bot:  没能识别到订单号，请提供形如 AB12345678 的订单号。   ← asks, sets pending slot
User: AB12345678
Bot:  订单 AB12345678 当前状态：shipped …               ← resumes tool, no re-classify
```

## Current-state anchors

- `agent/tools.py::execute_tool` `tools.py:221-234` — the dead-end. On no
  `ORDER_ID_PATTERN` match it returns guidance text with `raw: None` and no memory.
- `agent/tools.py:22` — `ORDER_ID_PATTERN = r"\b[A-Z]{2,4}\d{6,}\b"` (reused for extraction).
- `agent/graph.py:67` — **wiring gap**: `tool_node(state, rag_service=...)` is
  called *without* `conversation_repo`, so today `tool_node` has no way to
  persist anything conversation-scoped. Must be threaded through.
- `agent/service.py::process` `service.py:215-224` — classify → load route map →
  `route_by_intent` → `harness.choose_route`. The resume check inserts before
  `classify_node`.
- `agent/harness.py:122-128` — `choose_route` **force-overrides to `clarify`
  when `intent.confidence < 0.5`** and sets `state.route`; `graph.py:51` honors
  `state.route` if set. The resume path must carry a confidence above the
  threshold or the harness will eat it (see Design §4).
- `chat/service.py::_ensure_conversation` `service.py:116-139` — already fetches
  the `Conversation` row but returns only the UUID. Refactored here to return
  the object, giving a **query-free hook** for reading `metadata_` (and, in
  Slice 02, `status`).
- `models/conversation.py:31` — `metadata_: Mapped[dict | None]` mapped to the
  `metadata` JSONB column. Slot state lives here — no migration.
- `agent/state.py` `AgentState` — gains a `pending_tool` field.

### Why `conversations.metadata`, not the Redis session store

`chat/session.py::SessionStore` keeps history in Redis with `MAX_HISTORY=20`
trim and a 24h TTL — fine for prompt context, wrong for control state: a
pending slot silently evaporating on TTL/trim would resurrect the dead-end bug
intermittently. The JSONB column is durable, already exists, and is read on the
same row fetch `_ensure_conversation` already performs. (Cross-cutting
constraint #1: no process-local state either.)

## Design

### 1. Pending-slot record

Stored on `conversations.metadata` under a reserved key:

```json
{
  "pending_tool": {
    "tool": "search_order",
    "slot": "order_id",
    "intent": "order_query",
    "turns_waited": 0
  }
}
```

Concurrent updates are last-write-wins; acceptable — one user, one conversation,
and the worst case is an extra ask.

### 2. Read path (no new queries)

`_ensure_conversation` returns the `Conversation` object. `process_user_message`
reads `conv.metadata_.get("pending_tool")` and passes it into
`agent_service.process(...)`, which places it on `state.pending_tool`. `process`
itself never loads the conversation — chat service already has the row.

### 3. Resume-before-classify decision table

Guard at the top of `process` (extracted to `_resume_pending_tool(state)` to
keep `process` within the 50-line limit). With a pending slot:

| Incoming message | Decision |
|---|---|
| Matches `ORDER_ID_PATTERN` | **Resume**: skip `classify_node`; set `state.intent = IntentResult(pending.intent, RESUME_SLOT_CONFIDENCE)`; candidate route `"tool"`; pass extracted id via state. Clear pending on tool success. |
| No match → classify normally, intent **same as pending** (still on-topic, still no id) | Increment `turns_waited`; route to `tool` which re-asks. At `turns_waited >= MAX_SLOT_TURNS`: clear pending, route `clarify` (no infinite ask loop). |
| No match → classified intent **differs** with `confidence >= ABANDON_CONFIDENCE` (e.g. user pivots to `handoff` or `complaint`) | **Abandon**: clear pending, proceed with the normal route for the new intent. `handoff` naturally wins here via `HANDOFF_PATTERNS`. |

Regex-first matters: a bare `"AB12345678"` reply has no keyword hits and the
LLM classifier could label it anything — extraction must not depend on
classification.

### 4. Harness interplay (do not bypass, do not get eaten)

- The resume path still calls `harness.choose_route(state, "tool")` and
  `wrap_stream`/`finalize_state` — rails stay on.
- `RESUME_SLOT_CONFIDENCE = 0.9` (> `low_confidence_threshold=0.5`) so the
  `choose_route` override at `harness.py:122` doesn't rewrite the resume to
  `clarify`. `"tool"` is already in `allowed_routes`.
- Record `slot_resume` in `state.harness_trace` flags on the resume turn so the
  admin harness-flag distribution can count resumes. This is a trace-vocabulary
  addition → sync `AGENTS.md` §4.5.
- `AgentGraph.run` re-classifies only `if not state.intent` (`graph.py:48`) —
  the resume path sets intent, so no double classification.

### 5. Set/clear path

- `execute_tool` miss branch (`tools.py:223-231`) returns
  `{"needs_slot": "order_id", "tool": "search_order", "display": <ask copy>}`
  instead of the dead-end dict.
- `tool_node` (now receiving `conversation_repo` — fix `graph.py:67`) persists
  the pending record on `needs_slot`, increments `turns_waited` when one already
  exists, and clears it on a successful tool result.
- Clearing = merge-patch that removes the `pending_tool` key, never overwrite
  the whole `metadata` blob (it may carry other keys later).

### Constants (no magic numbers — global rule)

```python
MAX_SLOT_TURNS = 3               # give up asking after N turns → clarify
RESUME_SLOT_CONFIDENCE = 0.9     # resumed intent confidence; must clear harness threshold
ABANDON_CONFIDENCE = 0.7         # pivot to a different intent abandons the slot
PENDING_TOOL_METADATA_KEY = "pending_tool"
```

## Files touched

| File | Change |
|---|---|
| `agent/tools.py` | Miss branch returns `needs_slot`; extract ask-copy helper (≤ 50-line functions). |
| `agent/nodes.py` | `tool_node(state, conversation_repo=None, ...)` persists/increments/clears the pending record. |
| `agent/graph.py` | `graph.py:67`: pass `conversation_repo` into `tool_node`. |
| `agent/service.py` | `_resume_pending_tool(...)` guard before classify; `process` signature gains `pending_tool` (or reads it off a prepared state). |
| `agent/state.py` | Add `pending_tool: dict | None = None`. |
| `agent/slots.py` (new, if needed) | Pending-record read/merge/clear helpers — keeps `nodes.py` (215) and `tools.py` (242) under the 300-line cap. |
| `chat/service.py` | `_ensure_conversation` returns `Conversation`; pass `conv.metadata_["pending_tool"]` into `process`. |
| `repositories/conversation_repo.py` | Add `update_metadata(conv_id, patch)` (merge-patch semantics). |
| `AGENTS.md` | §3.3 rewrite (dead-end → slot-filling, decision table, metadata key); §4.5 add `slot_resume` flag. |

## Tests

`tests/unit/test_agent_slot_filling.py` (new):
- miss → `needs_slot` + pending record written via repo.
- valid id next turn → tool resumes; assert `classify_node` **not** called; assert
  harness trace has `slot_resume` and route `tool` (not `clarify` — the
  confidence-override regression case).
- same-intent non-answer → `turns_waited` incremented, re-ask.
- `turns_waited >= MAX_SLOT_TURNS` → pending cleared, route `clarify`.
- pivot to `handoff` phrasing → pending cleared, handoff route wins.
- clear is a merge-patch: unrelated metadata keys survive.

Plus: `make test` + `make lint` green.

## Contract sync

Rewrite `AGENTS.md` §3.3 ("工具入参未提取兜底") to the slot-filling behavior
(decision table + `pending_tool` key + constants); add `slot_resume` to the §4.5
trace vocabulary; mark `05-16-search-order-clarify-fallback` done in STATUS.md §6.

## Acceptance

- [ ] Missing order id asks once, remembers, and resumes on the next turn.
- [ ] Resume turn is **not** rewritten to `clarify` by the harness (confidence ≥ 0.9 carried).
- [ ] Slot state survives a simulated worker switch (read back from `conversations.metadata`).
- [ ] Give-up after `MAX_SLOT_TURNS` routes to `clarify`; intent pivot abandons the slot.
- [ ] Harness trace recorded on ask + resume turns, including `slot_resume`.
- [ ] `AGENTS.md` §3.3 + §4.5 updated in the same commit; STATUS.md task marked done.
- [ ] `make lint && make test` green; touched files within code-quality limits.
