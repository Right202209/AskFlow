# Slice 02 — Inline Clickable Citations + Evidence Self-Check

> Estimate: ~2–3 days (flagship). Depends on Slice 01's `RAGStreamResult` shape.
> No migration (verification persists on the existing `messages.extra` JSONB,
> `models/message.py:35`).

## Goal

Every claim in a RAG answer points at the chunk that backs it — `[1]`, `[2]`
markers that are **clickable** in the chat UI and open the matching source — and
a post-answer self-check verifies the claims are actually supported, flagging
answers that aren't. Citations stop being decoration and become checkable.

Success looks like:

```
Bot:  退货需在签收后 7 天内发起[1]，运费由平台承担[2]。
      ── Sources ──────────────────
      [1] 退换货政策 · 点击展开原文    ← click scrolls/opens the chunk
      [2] 运费说明   · 点击展开原文
      ✓ 自检通过：2/2 条引用有据可依
```

## Current-state anchors

**Backend**

- `rag/prompt_builder.py:10` — prompt asks for `[Source: title]`; free-text
  titles are unparseable and un-linkable. `build_rag_prompt` renders chunks as
  `[Source: {title}]\n{document}` (`prompt_builder.py:27-28`) — the chunk order
  here **is** the citation numbering we need; it just isn't numbered.
- `rag/service.py:82-90` — `sources` dicts are `{title, source, chunk, score}`:
  no index, no `doc_id`, nothing stable to link against. Chroma chunk metadata
  *does* carry `{doc_id, title, source?, indexed_at_epoch, generation,
  chunk_index}` (CLAUDE.md "Embedding pipeline"; written by
  `embedding/service.py::index_document`) — the ids exist, they're just dropped
  at this mapping.
- `chat/service.py:195-199` — the full answer is accumulated in `full_response`
  during streaming, so **the complete text exists server-side after the stream**
  — the natural hook for a post-answer check without buffering the stream.
- `chat/service.py:74-83` — assistant message persists with
  `sources={"sources": sources}` and `extra={"harness_trace": ...}`; the
  verification verdict joins `extra`.
- `chat/service.py:87-100` — `source` frame then `message_end` (which already
  carries `message_id`). Verification rides `message_end.data` — no new
  `ServerMessageType` needed (`chat/protocol.py:17-25` unchanged).
- `agent/harness.py:183-191` — `wrap_stream` may truncate long answers; a
  truncated answer can lose trailing citations. The verifier must tolerate a
  claim count of zero and flag rather than fail.

**Frontend**

- `web/src/components/chat/MessageBubble.tsx:16-61` — `renderContent` returns a
  plain `<p>` (except the LLM-fallback special case at lines 17-58); no marker
  parsing.
- `MessageBubble.tsx:103-118` — the sources footer already renders `index + 1`
  badges — the visual numbering to align `[n]` markers with.
- `web/src/components/chat/SourceCard.tsx:3-15` — chunk-preview card, currently
  unused by `MessageBubble`; becomes the click target (popover/expand).
- `web/src/types/chat.ts` — `Source { title; chunk; score }`; needs `index`,
  `doc_id`, `chunk_index`.
- `web/src/components/chat/MessageList.tsx:61-66` — the streaming bubble renders
  `streamingTokens` through the same `MessageBubble`, so `[n]` markers must
  render sanely mid-stream (a bare `[` may be the start of a marker).

## Design

### 1. Numbered-citation prompt contract (decision D4)

`build_rag_prompt` renders chunks as `[{i}] {title}\n{document}` with `i`
starting at `CITATION_BASE_INDEX = 1`, and `SYSTEM_PROMPT` is rewritten to:
cite with bare `[n]` markers immediately after the supported claim; use only
provided numbers; **do not answer beyond the context**. The `[Source: title]`
convention is retired in the same commit (grep confirms no other consumer).

Deterministic post-guard, streaming-safe: markers can't be validated mid-stream,
so validation happens on the persisted text (see §3) — out-of-range markers
(`[7]` with 5 sources) are recorded as `invalid_citations`, not silently
rewritten (the persisted text must equal what the user saw stream past).

### 2. Sources carry identity

The source-building helper (single helper after Slice 01's dedup of
`service.py:52-60` / `82-90`) adds:

```python
{"index": i + CITATION_BASE_INDEX, "doc_id": ..., "chunk_index": ...,
 "title": ..., "source": ..., "chunk": ..., "score": ...}
```

`doc_id` / `chunk_index` come straight from chunk metadata. Pre-2026-04-17
chunks lacking fields degrade gracefully (`doc_id` may be parsed from the chunk
id prefix `{doc_id}_g{generation}_c{i}`; absent → link disabled, never broken).

### 3. Post-answer evidence self-check (`rag/verifier.py`, new — decision D5)

Called from a new `chat/service.py` helper after the token loop and **before**
persist + `message_end`:

```python
@dataclass(frozen=True)
class VerificationResult:
    checked: bool                  # False when skipped (timeout/error/refusal/no sources)
    supported: int
    total: int                     # cited claims found in the answer
    invalid_citations: list[int]   # markers with no matching source
    verdict: str                   # "pass" | "partial" | "fail" | "skipped"
```

Two layers:
1. **Deterministic:** regex-extract `[n]` markers; out-of-range → `invalid_citations`.
2. **LLM judge:** one call — answer + numbered chunks in, strict JSON verdict out
   (`{"claims": [{"citation": n, "supported": true|false}]}`), `temperature=0`,
   bounded by `VERIFY_TIMEOUT_S` via `asyncio.wait_for`. Any failure ⇒
   `verdict="skipped"`, flag `verify_skipped` — the check must never delay or
   break `message_end` beyond the timeout.

`verdict` mapping: `pass` = all supported; `partial` = `supported/total ≥
VERIFY_PARTIAL_THRESHOLD`; `fail` below. Refusal turns (Slice 01 flag present)
and non-`rag` routes skip verification entirely.

### 4. Persistence + push (decision D6)

- Persist: `extra` gains `"verification": asdict(result)` alongside
  `harness_trace` (`chat/service.py:74-83`).
- Push: `message_end.data` gains `"verification": {...}` next to the existing
  `message_id` (extend `manager.send_message_end`, keeping ≤ 3 positional
  params — pass a payload object).
- REST read-back: `schemas/message.py::MessageResponse` gains
  `extra: dict | None` passthrough (or a typed `verification` field) so history
  reload shows the same badge — REST/WS sync rule.

### 5. Frontend rendering

- `web/src/lib/citations.tsx` (new): split content on `CITATION_MARKER_RE =
  /\[(\d{1,2})\]/g` into text + `<CitationChip n>` elements. Mid-stream: a
  trailing unmatched `[` or `[1` renders as plain text (no flicker heuristics).
- `MessageBubble.tsx`: `renderContent` uses the splitter; chips are buttons that
  open the matching `SourceCard` in a popover (and highlight the footer row).
  Footer rows for cited sources become clickable too. Verification badge under
  the answer: ✓ pass / ⚠ partial / ✗ fail / nothing when skipped.
- `types/chat.ts`: extend `Source`; add `Verification` type; `Message` gains
  `verification?: Verification | null`.
- `useWebSocket.ts:119-126`: `message_end` case also stores
  `msg.data.verification`; `chatStore.ts::finalizeMessage`
  (`chatStore.ts:146-170`) attaches it to the finalized message.

### Constants (no magic numbers — global rule)

```python
CITATION_BASE_INDEX = 1
CITATION_MARKER_RE = r"\[(\d{1,2})\]"
VERIFY_TIMEOUT_S = 8.0
VERIFY_PARTIAL_THRESHOLD = 0.5     # supported/total below this → "fail"
VERIFY_MAX_CHUNK_CHARS = 800       # per-chunk budget in the judge prompt
```

## Files touched

| File | Change |
|---|---|
| `rag/prompt_builder.py` | Numbered chunks + rewritten citation rules in `SYSTEM_PROMPT` (`prompt_builder.py:5-12,27-28`). |
| `rag/service.py` | Source helper adds `index` / `doc_id` / `chunk_index`. |
| `rag/verifier.py` (new) | `VerificationResult`, marker extraction, LLM judge, constants. New module keeps `chat/service.py` (226) under the 300 cap. |
| `chat/service.py` | Post-stream verify hook; persist `extra.verification`; extended `message_end` payload (helper extraction to respect the 50-line function limit — `process_user_message` is already 75 lines and must shed weight, not gain it). |
| `chat/manager.py` | `send_message_end` carries the verification payload (object param). |
| `schemas/message.py` | `MessageResponse` exposes verification (REST/WS sync). |
| `web/src/lib/citations.tsx` (new) | Marker splitter + `CitationChip`. |
| `web/src/components/chat/MessageBubble.tsx` | Citation chips, clickable footer, verification badge. |
| `web/src/components/chat/SourceCard.tsx` | Expandable chunk view (click target). |
| `web/src/types/chat.ts` | `Source` + `Verification` types. |
| `web/src/hooks/useWebSocket.ts` | `message_end` verification handling (`useWebSocket.ts:119-126`). |
| `web/src/stores/chatStore.ts` | Buffer + attach verification in `finalizeMessage`. |
| `AGENTS.md` | §4.5 flags (`verify_skipped`, `invalid_citations`); §8 add `rag/verifier.py`. |

## Tests

`tests/unit/test_prompt_citations.py` (new):
- chunks numbered from `CITATION_BASE_INDEX` in retrieval order; system prompt
  contains the `[n]` contract and no `[Source:` remnant.

`tests/unit/test_verifier.py` (new):
- marker extraction incl. out-of-range → `invalid_citations`.
- judge JSON parsed → correct `supported/total` and verdict banding
  (`VERIFY_PARTIAL_THRESHOLD` boundary).
- judge timeout (mock sleep > `VERIFY_TIMEOUT_S`) → `verdict="skipped"`,
  `message_end` still sent.
- refusal turn (Slice 01 flag) → verification skipped.

`tests/unit/test_chat_message_end_payload.py` (new, patches
`askflow.chat.service` per the CLAUDE.md testing note):
- `message_end.data` carries `message_id` + `verification`; persisted
  `extra.verification` matches the pushed payload.

Frontend has no test runner (CLAUDE.md) — `npm run build` (tsc) is the type
gate; manual checklist in Acceptance.

## Contract sync

`AGENTS.md` §4.5: add `verify_skipped` flag and the `verification` trace/extra
vocabulary; §8: add `rag/verifier.py`. Citation prompt rules live in RAG, not
the agent contract, but note the new answer format in §4.4 (stream output
constraints) since truncation can now sever citations.

## Acceptance

- [ ] RAG answers carry `[n]` markers matching the numbered chunks; sources payload carries `index`/`doc_id`/`chunk_index`.
- [ ] Clicking a citation chip opens the matching chunk; markers render cleanly mid-stream (trailing `[1` doesn't flicker).
- [ ] Self-check verdict pushed on `message_end`, persisted on `extra.verification`, and identical on REST history reload.
- [ ] Judge timeout/failure never blocks or breaks `message_end` (flag `verify_skipped`).
- [ ] Out-of-range markers surface as `invalid_citations`, text untouched.
- [ ] `AGENTS.md` §4.4/§4.5/§8 updated in the same commit.
- [ ] `make lint && make test` and `npm run build` green; touched files within code-quality limits.
