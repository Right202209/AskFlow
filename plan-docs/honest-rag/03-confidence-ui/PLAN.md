# Slice 03 — Answer Confidence on the UI

> Estimate: ~1 day. Depends on Slice 01 (`retrieval_confidence`) and Slice 02
> (`verification`). No migration (`messages.extra` JSONB again).

## Goal

Every RAG answer carries a single, honest **answer confidence** — derived from
retrieval strength and the evidence self-check — delivered identically over WS
(live) and REST (history), and rendered as a badge in the chat UI. Users see at
a glance whether an answer is solid or shaky.

Success looks like:

```
Bot:  退货需在签收后 7 天内发起[1]。      ● 高置信 (0.86)
Bot:  关于这一点资料较少，可能是……        ◐ 低置信 (0.41) — 建议核实或转人工
```

## Current-state anchors

- **The only confidence today is intent confidence.** It is pushed on the
  `intent` frame (`chat/service.py:183-193`), persisted to
  `messages.confidence` (`chat/service.py:80`, column at
  `models/message.py:30`), exposed on `MessageResponse`
  (`schemas/message.py:19`), and stored on the frontend message
  (`chatStore.ts:156`, type at `web/src/types/chat.ts::Message.confidence`).
  It answers "how sure was the classifier", not "how likely is this answer
  correct" — a naming trap this slice must not deepen.
- Slice 01 leaves `retrieval_confidence` in `state.harness_trace`, persisted at
  `chat/service.py:74-83` into `extra.harness_trace`.
- Slice 02 leaves `verification` (`supported/total`, `verdict`) in
  `extra.verification` and on `message_end.data`.
- `chat/service.py:95-100` — `message_end` already carries `message_id`; the
  confidence payload rides the same frame (no new `ServerMessageType`,
  `chat/protocol.py:17-25` unchanged).
- `useWebSocket.ts:111-142` — the `onmessage` switch; `message_end` case at
  `useWebSocket.ts:119-126`.
- `chatStore.ts:146-170` — `finalizeMessage` assembles the finalized assistant
  message from buffered stream state; the natural attach point.
- `MessageBubble.tsx:103-118` — sources footer; the badge sits above it.
- **Pre-existing drift to clear first** (OVERVIEW "Pre-existing drift"):
  - `chat/router.py:223-371` — stale inline WS handler duplicating
    `process_user_message`; `router.py:303` unpacks a 3-tuple from
    `agent_service.process(...)`, which returns a `ProcessResult` — broken
    copy. Adding confidence to only the service path would fork the protocol
    again. Fix: `_run_session`'s `message` branch delegates to
    `chat/service.py::process_user_message` (deleting `router.py:257-365`),
    which also removes the un-imported `check_rate_limit` reference at
    `router.py:262` and shrinks `router.py` (427 lines — **over the 300-line
    file cap**) back under the limit.
  - `chat/router.py:59-83` — duplicate `GET /conversations` registration; keep
    the `Query`-validated one (`router.py:59-68`), delete the other.
  - `web/src/types/chat.ts::ServerMessageType` — add the missing `"handoff"`
    member (backend sends it, `chat/protocol.py:24`).

## Design

### 1. One formula, one home (`chat/confidence.py`, new — decision D7)

```python
@dataclass(frozen=True)
class AnswerConfidence:
    score: float           # 0..1
    band: str              # "high" | "medium" | "low"
    retrieval: float       # input: Slice 01 retrieval_confidence
    verify_pass_rate: float | None   # input: supported/total, None when skipped
```

`compute_answer_confidence(harness_trace, verification) -> AnswerConfidence | None`:

- returns `None` for non-`rag` turns (no `retrieval_confidence` in the trace) —
  ticket/handoff/clarify/tool answers show no badge; a confidence on "已为您创建
  工单" would be noise.
- `score = RETRIEVAL_WEIGHT * retrieval + VERIFY_WEIGHT * verify_pass_rate`;
  when verification was skipped, `score = retrieval` and the badge is annotated
  "未自检" (weights must not silently inflate a half-checked answer).
- refusal turns (Slice 01 flag): `band="low"` by construction — the honest floor.
- banding server-side: `band = "high" if score >= HIGH_CONFIDENCE_THRESHOLD
  else "medium" if score >= MEDIUM_CONFIDENCE_THRESHOLD else "low"` — REST and
  WS consumers render the same band without duplicating thresholds in TS.

### 2. Naming discipline (decision D8)

`messages.confidence` keeps meaning **intent** confidence — renaming means a
migration plus touching every reader for zero behavior. Answer confidence lives
at `extra.answer_confidence` (asdict of the dataclass). The UI relabels: the
intent chip (if shown) says 意图置信度, the new badge says 回答置信度.

### 3. Payload plumbing (REST + WS in lockstep — cross-cutting rule 3)

- `chat/service.py::process_user_message`: compute after verification, persist
  in `extra`, include in `message_end.data` (same helper Slice 02 introduced
  for the `message_end` payload — one construction site).
- `schemas/message.py::MessageResponse`: expose `answer_confidence` (via the
  `extra` passthrough added in Slice 02).
- `web/src/types/chat.ts`: `AnswerConfidence` type; `Message.answer_confidence?`.
- `useWebSocket.ts` `message_end` case: read `msg.data.answer_confidence` into
  the store (`setPendingAnswerConfidence`, mirroring
  `setPendingAssistantMessageId` at `useWebSocket.ts:122-124`).
- `chatStore.ts::finalizeMessage`: attach it; `resetStreaming`
  (`chatStore.ts:197-204`) clears it; history load path
  (`selectConversation` → `chatService.getMessages`, `chatStore.ts:61-74`)
  maps it off the REST response so old messages get badges too.

### 4. UI rendering

`web/src/components/chat/ConfidenceBadge.tsx` (new): small pill —
`● 高置信` / `◐ 中置信` / `○ 低置信` with the numeric score in a tooltip; low
band appends "建议核实或转人工". Rendered by `MessageBubble` above the sources
footer for assistant messages with a non-null confidence; hidden while
streaming (`MessageList.tsx:61-66` streaming bubble passes none — confidence
only exists at `message_end`).

### Constants (no magic numbers — global rule)

```python
RETRIEVAL_WEIGHT = 0.6
VERIFY_WEIGHT = 0.4                  # must sum to 1.0 with RETRIEVAL_WEIGHT
HIGH_CONFIDENCE_THRESHOLD = 0.75
MEDIUM_CONFIDENCE_THRESHOLD = 0.5
```

## Files touched

| File | Change |
|---|---|
| `chat/confidence.py` (new) | `AnswerConfidence`, `compute_answer_confidence`, constants. |
| `chat/service.py` | Compute + persist + push on `message_end`. |
| `chat/router.py` | **Drift fix**: `_run_session` delegates to `process_user_message` (delete `router.py:257-365` inline copy); remove duplicate `GET /conversations` (`router.py:71-83`). Brings the file back under 300 lines. |
| `schemas/message.py` | Expose `answer_confidence`. |
| `web/src/types/chat.ts` | `AnswerConfidence` type; add missing `"handoff"` to `ServerMessageType`. |
| `web/src/hooks/useWebSocket.ts` | `message_end` reads `answer_confidence`. |
| `web/src/stores/chatStore.ts` | Buffer, attach in `finalizeMessage`, clear in `resetStreaming`, map on history load. |
| `web/src/components/chat/ConfidenceBadge.tsx` (new) | Band pill. |
| `web/src/components/chat/MessageBubble.tsx` | Render badge. |
| `AGENTS.md` | §4.5: `answer_confidence` in the persisted-extra vocabulary. |

## Tests

`tests/unit/test_answer_confidence.py` (new):
- weighted formula and band boundaries (exact `HIGH_/MEDIUM_CONFIDENCE_THRESHOLD` edges).
- verification skipped → score = retrieval only, `verify_pass_rate=None`.
- refusal trace → `band="low"`.
- non-rag trace (no `retrieval_confidence`) → `None`.

`tests/unit/test_chat_message_end_payload.py` (extend Slice 02's file):
- `message_end.data.answer_confidence` present and equal to persisted
  `extra.answer_confidence`.

`tests/integration/test_chat_websocket.py` (existing): update for the
`_run_session` delegation — the WS path must now exercise
`process_user_message` (patch `askflow.chat.service`, per CLAUDE.md testing
notes). This doubles as the regression test for the drift fix.

Frontend: `npm run build` type gate + manual checklist.

## Contract sync

`AGENTS.md` §4.5 only (`answer_confidence` joins the persisted-extra
vocabulary). No intent/route/tool/harness-policy change. Also worth one line in
`docs/status/STATUS.md` noting the `chat/router.py` WS drift fix, since the
"REST and WS shapes stay in sync" invariant was violated before this slice.

## Acceptance

- [ ] `message_end` carries `answer_confidence`; REST history returns the identical object; badge renders in both live and reloaded conversations.
- [ ] Non-rag turns and streaming-in-progress bubbles show no badge; refusal turns show `low`.
- [ ] Verification-skipped answers show the "未自检" annotation, not an inflated score.
- [ ] Intent confidence and answer confidence remain distinct in DB, API, and UI labels.
- [ ] Drift fixed: WS message path delegates to `process_user_message`; duplicate `GET /conversations` removed; `chat/router.py` back under 300 lines; frontend `ServerMessageType` includes `"handoff"`.
- [ ] `AGENTS.md` §4.5 updated in the same commit.
- [ ] `make lint && make test` and `npm run build` green; touched files within code-quality limits.
