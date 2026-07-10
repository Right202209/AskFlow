# Honest RAG

**Spine:** make AskFlow's RAG *solid and honest* — it declines when the knowledge
base can't support an answer, it cites the exact chunk behind every claim, and it
tells the user how confident it is. Trust is the product: a customer-service bot
that confidently hallucinates is worse than one that says "I don't know."

## The three honesty gaps (grounded in current code)

**A. The pipeline always answers.** `rag/service.py::query_stream`
(`service.py:80-91`) retrieves, reranks, builds the prompt and streams —
unconditionally. With zero or junk hits the LLM still gets a near-empty context
and the only guard is a *plea* in `SYSTEM_PROMPT` ("If the context doesn't
contain enough information, say so honestly", `prompt_builder.py:5-12`).
`build_fallback_response` (`prompt_builder.py:42-51`) fires only when the **LLM
call fails**, never when **retrieval** is weak. Nothing deterministic refuses.

**B. Citations are decorative.** The prompt asks for `[Source: title]`
(`prompt_builder.py:10`) but nothing enforces or verifies it; `sources` payloads
(`service.py:82-90`) carry `{title, source, chunk, score}` with no stable index
or `doc_id`, so the frontend footer (`MessageBubble.tsx:103-118`) shows a
numbered list that **no claim in the answer points at** and nothing is clickable.
No step ever checks that the answer is actually backed by the retrieved chunks.

**C. Confidence exists but is the wrong one.** The only confidence surfaced
today is the **intent classifier's** (`chat/service.py:80`, `intent` WS frame at
`chat/service.py:183-193`, `Message.confidence` in `web/src/types/chat.ts`). It
says "I'm 0.9 sure this is a FAQ", not "I'm 0.9 sure this answer is right".
Retrieval scores reach the UI only as a per-source decimal
(`MessageBubble.tsx:113-115`); the answer itself carries no confidence at all.

## Scope

In scope:
- Slice 01 — refusal on weak retrieval (deterministic no-answer path + grounding score).
- Slice 02 — inline clickable `[1]`-style citations + post-answer evidence self-check.
- Slice 03 — answer-confidence in message payloads (REST + WS) and chat UI.

Out of scope (respect the CLAUDE.md product positioning — single-tenant
reference implementation):
- Retraining/replacing the embedding model or reranker; we consume the scores
  the current pipeline produces.
- Claim-level highlighting inside source documents (chunk-level linking only).
- Feedback-loop tuning of thresholds (thresholds are named constants, tuned by hand).

## Sequencing & rationale

```
01-weak-retrieval-refusal ──▶ 02-inline-citations-selfcheck ──▶ 03-confidence-ui
      (~1 day)                       (~2–3 days, flagship)          (~1 day)
```

Slice 01 first: backend-only, no protocol or frontend change, and it produces
the `retrieval_confidence` number that slices 02/03 consume. Slice 02 is the
flagship (prompt contract + verifier + frontend rendering). Slice 03 is a thin
payload + UI slice that needs both upstream scores; doing it last means the
confidence formula ships with real inputs instead of placeholders.

## Cross-cutting constraints (apply to every slice)

1. **Scores are heterogeneous — never threshold them blindly.**
   `RetrievalResult.score` means three different things depending on `source`:
   vector = `1.0 - distance` (`retriever.py:83`), bm25 = raw unbounded BM25
   (`retriever.py:97`), fused = RRF sums bounded by `weight/(k+1)` ≈ 0.016
   (`retriever.py:123,128`). The reranker adds **no** score — it only reorders
   (`reranker.py:68-73`) or passes through (`reranker.py:27-28`). All grounding
   math lives in one module (Slice 01's `rag/grounding.py`) that normalizes per
   channel.
2. **Do not fight the harness.** `wrap_stream` injects
   `policy.fallback_response` if a stream yields nothing (`harness.py:194-195`)
   and truncates at `max_response_chars` (`harness.py:183-191`). A refusal must
   be a *stream that yields the refusal copy*, and every new behavior records a
   flag in `state.harness_trace` — flags are load-bearing for admin analytics.
3. **REST and WS shapes stay in sync.** Any payload change lands in
   `chat/service.py` (persist + WS push), `schemas/message.py` (REST read-back),
   `web/src/types/chat.ts`, `useWebSocket.ts`, `chatStore.ts` together.
4. **Contract-with-code.** Prompt/verifier/trace changes update `AGENTS.md`
   (§4.5 trace vocabulary, §8 source index) in the same commit.
5. **No process-local conversation state**; verification results persist on
   `messages.extra` (`models/message.py:35`), same slot as `harness_trace`.
6. **Hard code-quality limits** (functions ≤ 50 lines, files ≤ 300 lines, no
   magic numbers). `chat/service.py` is already 226 lines and `harness.py` 283 —
   new logic goes in new modules (`rag/grounding.py`, `rag/verifier.py`,
   `chat/confidence.py`), not inflated existing ones.

## Pre-existing drift this initiative must not worsen (fix in Slice 03)

- `chat/router.py:223-371` still contains a **stale inline WS handler**
  (`_run_session`) that duplicates `process_user_message` and unpacks
  `token_stream, sources, intent_result = await agent_service.process(...)`
  (`router.py:303`) — `process` returns a `ProcessResult`, so this path is
  broken drift. Slice 03 must route `_run_session` through
  `chat/service.py::process_user_message` (or delete the inline copy) *before*
  adding new frames, or the new payloads will fork again.
- `chat/router.py:59-83` registers `GET /conversations` **twice** (second wins).
- Frontend `ServerMessageType` union (`web/src/types/chat.ts`) is missing
  `"handoff"` even though the backend sends it (`chat/protocol.py:24`).

## Resolved design decisions (rationale in the slice docs)

| # | Decision | Where |
|---|---|---|
| D1 | Refusal happens **inside RAGService**, not as a route override — retrieval strength is unknowable at `harness.choose_route` time (routing precedes retrieval, `agent/service.py:223-230`). Refusal ≠ `clarify`: clarify = "intent unclear", refusal = "knowledge missing". | 01 §Design 1 |
| D2 | Grounding confidence is computed per retrieval channel (vector score directly; bm25 via logistic squash; fused via the underlying vector hits) in `rag/grounding.py`; a single raw-score threshold is rejected as meaningless across channels. | 01 §Design 2 |
| D3 | `query_stream`'s 2-tuple return grows into a `RAGStreamResult` dataclass (stream, sources, grounding) instead of a 3-tuple — two call sites, one honest shape. | 01 §Design 3 |
| D4 | Citations are **index-based** (`[1]`…`[k]`, k = chunks in prompt order), enforced by prompt + deterministic post-strip of out-of-range markers; title-based `[Source: …]` is retired. | 02 §Design 1 |
| D5 | Self-check is one LLM-judge call **after** the stream completes (the full answer already exists at `chat/service.py:195-199` as `full_response`), bounded by `VERIFY_TIMEOUT_S`; on timeout/error the check is skipped and flagged, never blocking `message_end`. | 02 §Design 3 |
| D6 | Verification result rides `message_end.data` (no new frame type) and persists on `messages.extra.verification` — reusing the exact channel `message_id` already uses (`chat/service.py:95-100`). | 02 §Design 4 |
| D7 | `answer_confidence = RETRIEVAL_WEIGHT × retrieval + VERIFY_WEIGHT × verify_pass_rate`, banded into `high/medium/low` server-side so REST and WS render identically and the formula has one home. | 03 §Design 1 |
| D8 | The existing `messages.confidence` column keeps meaning **intent** confidence (renaming = migration + churn); answer confidence lives in `extra.answer_confidence`. The UI relabels accordingly. | 03 §Design 2 |

## Docs in this initiative

- [`01-weak-retrieval-refusal/PLAN.md`](01-weak-retrieval-refusal/PLAN.md)
- [`02-inline-citations-selfcheck/PLAN.md`](02-inline-citations-selfcheck/PLAN.md)
- [`03-confidence-ui/PLAN.md`](03-confidence-ui/PLAN.md)
