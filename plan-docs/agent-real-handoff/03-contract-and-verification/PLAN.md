# Slice 03 — Contract Sync & End-to-End Verification

> Not a code feature — the closeout slice that keeps the repo's contracts honest
> and proves the flows work together. Runs after 01 and 02 land.

## Goal

Ensure the two behavior changes are reflected everywhere the project treats as
canonical, and verify the combined agent+handoff journey end to end (not just
per-slice unit tests).

## Why this is its own slice

CLAUDE.md and AGENTS.md make documentation a **gating constraint**, not an
afterthought: a change to intents/routes/tools/harness/handoff "without updating
the other is a contract violation." Slices 01 and 02 each sync their own AGENTS.md
section, but three repo-level sources still need reconciliation, and the
cross-slice journey (slot-fill → still stuck → handoff) is only exercised when
both exist.

## Checklist — canonical docs

- [ ] **`AGENTS.md`** — §3.3 (slot-filling decision table + `pending_tool` key),
      §4.5 (`slot_resume` trace flag), and §5 (handoff protocol incl. the
      transferred-message gate and staff-role history mirroring) reflect shipped
      behavior; §1.2 `out_of_scope` note untouched (separate task);
      "最后核对" date bumped.
- [ ] **`docs/status/STATUS.md`** — §2 Tools row (🟡 → note slot-filling done),
      Handoff row (🔴 Partial → ✅); §5 risk #6 (handoff black hole) resolved;
      §6 mark `05-16-search-order-clarify-fallback` and `05-16-handoff-protocol` done.
- [ ] **`PRD.md`** — §4.3 routing table + §4.5/§4.6 still accurate; note handoff
      now has queue/summary/return (PRD governs scope, so keep it truthful).
- [ ] **`docs/AGENT_HARNESS.md`** — confirm no harness rail was bypassed: the
      resume path still passes `choose_route`/`wrap_stream`, and the
      `allowed_history_roles` filter behavior (staff mirrored as `assistant`)
      is documented, not weakened.
- [ ] **`CLAUDE.md` "Chat behavior change" section** — new WS event types
      (`staff_message`, `handoff_update`) noted in the REST/WS-sync guidance,
      since future edits must keep both entry points aligned.

## Checklist — end-to-end journeys

Drive the real flows (per the repo's verify discipline — exercise behavior, not
just tests):

1. **Order slot-fill happy path** — ambiguous order question → ask → id on next
   turn → resolved lookup, no re-classification, harness trace shows
   `slot_resume` (not a `clarify` override).
2. **Slot give-up → handoff** — user never supplies the id → after
   `MAX_SLOT_TURNS` → clarify → user asks for a human → handoff enqueued with
   summary. (This is the cross-slice seam.)
3. **Handoff full loop** — transfer → staff inbox claim → reply → resolve →
   conversation back to `active` with warm-return event.
4. **Transferred gate** — while a session is queued/claimed, user messages are
   persisted and visible in the staff inbox, and the **AI does not answer**;
   staff reply arrives on the user's WebSocket (run backend with 2 uvicorn
   workers to exercise the push bridge cross-worker).
5. **Handoff timeout** — transfer, no claim → timeout sweep → ticket created via
   `TicketRepo.create` → session `timed_out` → user notified.
6. **Warm-return memory** — after resolve, ask the AI a question that depends on
   what the staff member said; the answer must reflect it (verifies the
   staff→`assistant` session mirror survived the harness history filter).
7. **Multi-worker sanity** — confirm pending-slot and handoff-session state are
   read back from Postgres (not a process dict), so a second worker sees them.

## Commands

```bash
make lint            # ruff check + format check (backend gate)
make test            # pytest + coverage (backend gate)
cd web && npm run build   # tsc -b + vite build (frontend's only type-check gate)
```

Then drive the app (`make dev` + `make dev-web`) through journeys 1–4 manually,
or via the `verify` skill if a project verify flow is bootstrapped.

## Acceptance

- [ ] All four canonical docs reconciled; dates bumped.
- [ ] Two Trellis tasks marked done in STATUS.md §6.
- [ ] Journeys 1–4 pass by observation, not just unit assertions.
- [ ] Journey 5 confirms state is DB-backed (multi-worker safe).
- [ ] `make lint && make test` and `npm run build` all green.
- [ ] Commits use `<type>: <description>` (feat/fix/docs), no `Co-Authored-By` trailer.
