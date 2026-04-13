# AskFlow Docs

> Last updated: 2026-04-06

This directory is the long-lived documentation hub for the repository. Use it for project-wide structure, status, and audit material. Frontend-only notes stay under `web/docs/`.

## Index

- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - repository layout and placement rules
- [status/PROJECT_STATUS.md](status/PROJECT_STATUS.md) - current implementation snapshot and verified gaps
- [audits/PRD_AUDIT.md](audits/PRD_AUDIT.md) - PRD-to-code audit
- [../README.md](../README.md) - English repository overview and quick start
- [../README_zh.md](../README_zh.md) - Chinese repository overview and quick start
- [../PRD.md](../PRD.md) - product requirements document
- [../web/docs/README.md](../web/docs/README.md) - frontend documentation index

## Documentation Split

| Location | Purpose |
|----------|---------|
| Repository root README files | onboarding, quick start, command reference |
| `docs/` | project-wide status, structure, audits, architecture notes |
| `web/docs/` | frontend routes, page notes, stack conventions |

## Conventions

- Do not add new loose project-analysis Markdown files at the repository root
- Put status and milestone tracking under `docs/status/`
- Put audits, gap analyses, and review notes under `docs/audits/`
- Put frontend-only planning or implementation notes under `web/docs/`
- Keep the README files high-level; detailed operational notes belong here
