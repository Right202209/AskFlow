# AskFlow Docs

> Last updated: 2026-05-20

This directory is the long-lived documentation hub for the repository. Use it for project-wide structure, status, audits, and architecture notes. Frontend-only notes stay under `web/docs/`.

## Index

- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) — repository layout and placement rules
- [AGENT_HARNESS.md](AGENT_HARNESS.md) — Cognitive Harness design and policy fields
- [USAGE_GUIDE_zh.md](USAGE_GUIDE_zh.md) — end-to-end walkthrough（中文）
- [status/STATUS.md](status/STATUS.md) — **canonical** current implementation status (2026-05-20)
- [status/](status/) — historical status snapshots (dated, superseded; do not update)
- [audits/IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md](audits/IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md) — implicit business constraints + concurrency invariants
- [audits/CLOSURE_SOP_REVIEW_2026-05-16.md](audits/CLOSURE_SOP_REVIEW_2026-05-16.md) — SOP review for the "ship-it" gate
- [audits/DUAL_ROLE_REVIEW_2026-05-14.md](audits/DUAL_ROLE_REVIEW_2026-05-14.md) — dual-role review of user-management surface
- [audits/PRD_AUDIT.md](audits/PRD_AUDIT.md) — PRD-to-code audit
- [../README.md](../README.md) — English repository overview and quick start
- [../README_zh.md](../README_zh.md) — Chinese repository overview and quick start
- [../AGENTS.md](../AGENTS.md) — Agent business contract (intents/routes/tools/harness/handoff)
- [../CLAUDE.md](../CLAUDE.md) — engineering guide for Claude Code agents
- [../PRD.md](../PRD.md) — product requirements document
- [../TRELLIS.md](../TRELLIS.md) — Trellis task/spec workflow
- [../web/docs/README.md](../web/docs/README.md) — frontend documentation index

## Documentation Split

| Location | Purpose |
|----------|---------|
| Repository root README files | onboarding, quick start, command reference |
| Repo-root `AGENTS.md` / `PRD.md` / `CLAUDE.md` / `TRELLIS.md` | canonical contracts (agent behavior / product scope / engineering practice / process) |
| `docs/` | project-wide status, structure, architecture, audits, walkthroughs |
| `docs/status/` | dated status snapshots (live + superseded) |
| `docs/audits/` | dated audits, reviews, gap analyses |
| `web/docs/` | frontend routes, page notes, stack conventions |
| `.trellis/tasks/` | active task tracking (PRD / brainstorm / research per task) |

## Conventions

- Do not add new loose project-analysis Markdown files at the repository root.
- Put status and milestone tracking under `docs/status/`. `STATUS.md` is the only living status doc; everything else there is a dated snapshot and should not be updated.
- Put audits, gap analyses, and review notes under `docs/audits/`. Audit filenames carry a date and are immutable once committed.
- Put frontend-only planning or implementation notes under `web/docs/`.
- Keep the root README files high-level; detailed operational notes belong here.
- When in doubt about which doc to update: `AGENTS.md` governs agent behavior, `PRD.md` governs product scope, `CLAUDE.md` governs how AI agents should edit this repo, `docs/status/STATUS.md` captures current implementation snapshot.
