# Slice 01 — Prompt Template CRUD

> Estimate: ~2 days. One DB migration (`20260709_01_prompt_templates`).

## Goal

Every operator-tunable prompt loads from a DB-backed, versioned template with
admin CRUD — edits take effect on all workers within seconds (pub/sub) or 60s
worst-case (TTL), and a bad edit rolls back by repointing to a prior version.
The mechanism is the *same* one `intent_route_mapping` already uses, extracted
into a reusable helper instead of duplicated.

## Current-state anchors

Hardcoded prompts (the migration inventory — these five become seeded rows):

- `rag/prompt_builder.py:5-12` — `SYSTEM_PROMPT` ("You are AskFlow … Answer …
  based ONLY on the provided context"). Consumed at `prompt_builder.py:30`.
- `rag/prompt_builder.py:14-19` — `CONTEXT_TEMPLATE` with `{chunks}` /
  `{question}` placeholders, formatted at `prompt_builder.py:36`.
- `rag/prompt_builder.py:44` — no-results fallback copy; `:45-51` — LLM-down
  fallback preamble in `build_fallback_response`.
- `agent/intent_classifier.py:15-27` — `INTENT_PROMPT`, the six-intent
  classifier prompt with a `{message}` placeholder (JSON-only response
  contract at `:24-25`), formatted at `intent_classifier.py:113`.
- `agent/nodes.py:178-181` — `clarify_node` fixed copy (two tokens).

The pattern to mirror (read these before writing any code):

- `agent/service.py:27-29` — `ROUTE_MAP_INVALIDATE_CHANNEL =
  "askflow:route_map:invalidate"`, `ROUTE_MAP_CACHE_TTL_SECONDS = 60.0`.
- `agent/service.py:40-68` — `_load_route_map`: TTL check (`:44`), snapshot
  `pre_load_seq = _route_map_invalidate_seq` **before** the DB query (`:48`),
  refuse the cache write when the counter advanced during the load (`:61-67`).
  This epoch guard is the whole point — a concurrent invalidate must never be
  overwritten by an in-flight loader's stale snapshot.
- `agent/service.py:71-84` — `invalidate_route_map_cache` (bumps the epoch) +
  `publish_route_map_invalidation` (best-effort; Redis-down is swallowed
  because the 60s TTL is the backstop).
- `agent/service.py:87-135` — pub/sub listener + `start/stop` wired in
  `main.py:73` (lifespan, after `redis_client.initialize()` at `:70`) and
  `main.py:86` (shutdown).
- `admin/service.py:32-50` — the write path: every intent CRUD op calls
  `invalidate_route_map_cache()` **and** `await
  publish_route_map_invalidation()`. Prompt CRUD must do the same pair.
- `admin/router.py:88-133` — the intent endpoints to mirror (list is
  `admin`/`agent`, mutations `admin`-only via `require_role`, `core/auth.py:45`).
- `models/intent_config.py:10-21` + `models/base.py:11-25` — model house style
  (`Base, UUIDMixin, TimestampMixin`).
- Frontend precedent: `web/src/pages/Admin/IntentsPage.tsx` (263 lines) +
  `web/src/services/admin.ts` + `adminStore.ts`.

### Non-goals (explicit)

- **Harness copy stays in code.** `harness.py:35-41`
  (`empty_input_response`, `prompt_control_response`, `fallback_response`,
  `response_truncated_notice`) are deterministic safety rails on
  `CognitiveHarnessPolicy` — making them admin-editable would let a config
  mistake blank the prompt-injection refusal. Out of scope by decision D3.
- No prompt A/B testing, no per-user prompts, no template language beyond
  `str.format` named placeholders (single-tenant reference implementation).

## Design

### 1. Extract the cache machinery first: `core/config_cache.py` (new)

`agent/service.py` is 316 lines — over the 300 cap already — so this slice
*starts* by extracting, not adding. New `ConfigCache` generic:

```python
class ConfigCache[T]:
    def __init__(self, *, channel: str, loader: Callable[[], Awaitable[T]],
                 ttl_seconds: float = CONFIG_CACHE_TTL_SECONDS) -> None: ...
    async def get(self) -> T                 # TTL check → epoch-guarded load
    def invalidate(self) -> None             # clear + bump epoch
    async def publish_invalidation(self) -> None
    def start_subscriber(self) -> asyncio.Task
    async def stop_subscriber(self) -> None
```

Semantics are a verbatim lift of `agent/service.py:40-135` (including the
`pre_load_seq` guard and the swallow-on-Redis-failure publish). The route map
re-bases onto one instance (`channel="askflow:route_map:invalidate"` —
unchanged, so nothing external breaks); prompts get a second instance on
`PROMPT_INVALIDATE_CHANNEL = "askflow:prompts:invalidate"`. Both subscribers
start/stop in `main.py` lifespan next to the existing call (`main.py:73`,
`:86`). Net effect: `agent/service.py` *shrinks* by ~90 lines.

### 2. Data model (migration `20260709_01_prompt_templates`)

```
prompt_templates
  id UUID PK, created_at/updated_at (mixins)
  key           VARCHAR(100) UNIQUE NOT NULL   -- e.g. "rag.system"
  description   TEXT
  variables     JSONB NOT NULL                 -- declared placeholders, e.g. ["chunks","question"]
  active_version_id UUID NULL FK -> prompt_versions.id
  is_active     BOOLEAN NOT NULL DEFAULT true

prompt_versions
  id UUID PK, created_at (mixin)
  template_id   UUID FK -> prompt_templates.id, NOT NULL
  version       INTEGER NOT NULL               -- 1..n per template
  content       TEXT NOT NULL
  created_by    UUID FK -> users.id NULL
  comment       TEXT
  UNIQUE (template_id, version)
```

Seeded keys (data migration inserts version 1 = today's constants):
`rag.system`, `rag.context`, `rag.fallback_no_results`, `rag.fallback_llm_down`,
`intent.classifier`, `agent.clarify`. The FK cycle
(`active_version_id` ↔ `template_id`) is broken the usual way: insert template,
insert version, `UPDATE` the pointer — `use_alter=True` on the FK.

### 3. Versioning semantics (D2)

- Editing never mutates: `PUT /admin/prompts/{key}` appends a new
  `prompt_versions` row (`version = max+1`) and repoints `active_version_id`.
- Rollback = `POST /admin/prompts/{key}/activate/{version}` repoints only.
- Validation before commit: render the candidate with dummy values for each
  declared placeholder; a `KeyError`/stray `{` fails the request with 422.
  This is the guard against "admin typo takes down classification".
- Every mutation calls `prompt_cache.invalidate()` +
  `await prompt_cache.publish_invalidation()` — the same pair as
  `admin/service.py:34-35`.

### 4. Read path

New `core/prompts.py` (or `rag/prompt_store.py`, ≤300 lines either way):

```python
async def get_prompt(key: str) -> str  # cache.get() → dict[key, content]; falls back to code default
```

The loader fetches all active templates in one query (mirrors
`_load_route_map`'s single `get_all_active()` at `agent/service.py:53-56`).
**Fallback rule:** if the DB row is missing, inactive, or the DB is down, the
code-level constant (kept in place, renamed `DEFAULT_*`) is used and a
`prompt_fallback_default` warning is logged — the system must never fail to
answer because the prompt table is empty. Call sites change minimally:

- `prompt_builder.py:30/36/44/45` → `await get_prompt("rag.system")` etc.
  (`build_rag_prompt` becomes async or takes pre-resolved prompts from
  `RAGService` — prefer the latter: `RAGService` resolves once per query and
  passes them in, keeping `prompt_builder` pure/sync and testable).
- `intent_classifier.py:113` → `_model_classify` resolves
  `intent.classifier` via `get_prompt` before `.format(message=message)`.
- `nodes.py:178-181` → `clarify_node` resolves `agent.clarify`.

### Constants (no magic numbers)

```python
CONFIG_CACHE_TTL_SECONDS = 60.0                       # inherited from ROUTE_MAP_CACHE_TTL_SECONDS
PROMPT_INVALIDATE_CHANNEL = "askflow:prompts:invalidate"
MAX_PROMPT_CONTENT_CHARS = 20_000                     # 422 above this — bigger than any sane prompt
MAX_VERSIONS_LISTED = 50                              # version-history pagination page size
```

## Files touched

| File | Change |
|---|---|
| `core/config_cache.py` (new) | Generic TTL + epoch + pub/sub cache, lifted from `agent/service.py:40-135`. |
| `agent/service.py` | Re-base route map on `ConfigCache`; delete the now-duplicated ~90 lines; keep public names (`invalidate_route_map_cache`, …) as thin wrappers so `admin/service.py:7` imports stay valid. |
| `models/prompt.py` (new) | `PromptTemplate`, `PromptVersion`. |
| `repositories/prompt_repo.py` (new) | `get_all_active`, `get_by_key`, `append_version`, `activate_version`, `list_versions`. |
| `alembic/versions/20260709_01_prompt_templates.py` (new) | Tables + seed data (hand-check the FK cycle + seed inserts — autogenerate won't produce them). |
| `core/prompts.py` (new) | `prompt_cache` instance + `get_prompt` + `DEFAULT_PROMPTS` fallback map. |
| `rag/prompt_builder.py` | Constants → `DEFAULT_*`; accept resolved prompts as params. |
| `rag/service.py` | Resolve prompts per query, pass into `build_rag_prompt`. |
| `agent/intent_classifier.py` | `_model_classify` resolves the prompt via `get_prompt`. |
| `agent/nodes.py` | `clarify_node` resolves `agent.clarify`. |
| `admin/service.py` | `AdminService` prompt methods (list/get/update/activate) with the invalidate+publish pair. |
| `admin/router.py` | `GET /prompts`, `GET /prompts/{key}/versions`, `PUT /prompts/{key}`, `POST /prompts/{key}/activate/{version}` — mutations `admin`-only. **File is 172 lines; adding ~70 pushes past 300 → split a `admin/prompt_router.py` included from `admin/router.py`.** |
| `schemas/prompt.py` (new) | Request/response models incl. placeholder validation. |
| `main.py` | Start/stop the prompt cache subscriber beside `main.py:73/86`. |
| `web/src/pages/Admin/PromptsPage.tsx` (new) | List, edit-with-preview, version history, activate — clone `IntentsPage.tsx` structure. |
| `web/src/services/admin.ts`, `router/index.tsx`, `stores/adminStore.ts` | Wire the new page under `/admin/prompts` (staff-gated like `/admin/intents`). |

## Tests

`tests/unit/test_config_cache.py` (new):
- TTL expiry reloads; within TTL serves cached.
- **Epoch race:** invalidate during an in-flight load → load result returned
  but *not* cached; next `get` hits the loader again (port of
  `test_route_map_epoch.py` against the generic class).
- publish failure (Redis down) is swallowed; subscriber message invalidates.

`tests/unit/test_prompt_store.py` (new):
- missing/inactive key → code default + warning.
- placeholder validation rejects `{typo}` and unbalanced braces with 422.
- edit appends a version and repoints; rollback repoints without new rows.
- CRUD calls both `invalidate` and `publish_invalidation` (mirror
  `test_intent_invalidation.py`).

Regression: `test_route_map_epoch.py` must stay green against the re-based
route map. Plus `make lint && make test`.

## Contract sync

- `AGENTS.md` §2 (intent classification): note that the classifier prompt is
  now DB-backed under key `intent.classifier`, with the code constant as
  fallback, and that editing it can change intent labels → the six-intent
  vocabulary at `intent_classifier.py:15-27` remains the contract; the admin
  UI must warn when an edit removes an intent label from the prompt.
- `AGENTS.md` route/clarify section: `agent.clarify` copy is template-backed.
- Harness section: explicitly record decision D3 (harness copy not templated).

## Acceptance

- [ ] Editing `rag.system` in the admin UI changes the next RAG answer on
      **every** worker without restart (pub/sub) and within 60s even with
      Redis pub/sub down (TTL).
- [ ] Rollback to version N restores exact prior content; history is intact.
- [ ] Empty/absent `prompt_templates` table → system behaves exactly as today
      (code defaults), with a logged warning.
- [ ] Epoch-race test passes for the generic cache; route-map behavior
      unchanged (`test_route_map_epoch.py` green).
- [ ] Placeholder-typo edit is rejected with 422; nothing cached or persisted.
- [ ] `agent/service.py` is *smaller* than before; all touched files ≤ 300
      lines, functions ≤ 50.
- [ ] AGENTS.md updated in the same commit; `make lint && make test` green.
