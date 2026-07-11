# plan-docs

Planning workspace for AskFlow feature initiatives. Each subfolder is one
initiative, broken into ordered slices. These are **design docs, not status
docs** — implementation status stays in [`docs/status/STATUS.md`](../docs/status/STATUS.md),
and the executable agent contract stays in [`AGENTS.md`](../AGENTS.md).

Where a plan touches agent behavior (intents / routes / tools / harness /
handoff), the code change and `AGENTS.md` must land in the same commit — the
project treats code-without-contract as a violation. Each slice doc calls out
exactly which AGENTS.md section it moves.

## Initiatives

| Folder | Spine | Status |
|---|---|---|
| [`agent-real-handoff/`](agent-real-handoff/) | "Agent + real handoff" — the customer-service story: tools that collect missing info via multi-turn slot-filling, plus a warm human handoff (summary → queue → staff inbox → return) replacing today's flag-and-forget. | Implemented 2026-07-10 (business code; tests deferred) |
| [`honest-rag/`](honest-rag/) | "Honest RAG" — the trust story: deterministic refusal when retrieval is weak, inline clickable `[n]` citations backed by a post-answer evidence self-check, and an answer-confidence badge in the chat UI. | Implemented 2026-07-09 (business code; tests deferred) |
| [`knowledge-loop/`](knowledge-loop/) | "Self-evolving knowledge base" — the closed loop: capture the questions the bot fails (gap radar), turn gaps + staff answers into reviewed knowledge entries published through the document pipeline, and quantify every KB change with an offline golden-set eval. | Implemented 2026-07-09 (business code; tests deferred) |
| [`ops-platform/`](ops-platform/) | "Ops platform" — the deployability story: DB-backed prompt templates with versioned CRUD (route-map cache pattern reused), audit log + PII masking, asynchronous document indexing with visible status, and a production deployment checklist + health dashboards. | Implemented 2026-07-11 (business code; tests deferred) |

## Cross-initiative order

Build in this order: `honest-rag` → `knowledge-loop` → `agent-real-handoff` →
`ops-platform`. Honest RAG is the foundation (the knowledge loop's gap radar
consumes its refusal/low-score signals, and the offline eval scores its
citation/refusal behavior); the ops platform lands last so it hardens the
finished feature set. Note the deliberate coupling: `honest-rag/01`'s weak-
retrieval refusal is one of the signals `knowledge-loop/01`'s gap radar
captures — implement 01 of honest-rag before 01 of knowledge-loop and keep the
refusal constant/trace flags shared, not duplicated.

## Conventions

- One folder per initiative, kebab-cased.
- Numbered slice subfolders (`01-…`, `02-…`) encode build order; lower numbers
  are lower-risk / land first.
- Each initiative has an `OVERVIEW.md` (why, scope, sequencing) and one doc per
  slice (goal, current-state anchors, step-by-step, files touched, tests,
  contract sync, acceptance).
- Reference real code as `path:line` so a reader can jump straight to the anchor.
