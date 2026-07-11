# Deployment

Operator-facing deployment docs for AskFlow.

- **[CHECKLIST.md](CHECKLIST.md)** — the ordered, checkbox production
  deployment checklist (secrets → APP_ENV → migrations → workers → persistence
  → network/metrics → endpoints → ops toggles → end-to-end verify). Each item
  cites the enforcing code.

## Compose caveat

`docker-compose.yml` composes **infrastructure only** — PostgreSQL, Redis,
ChromaDB, MinIO — with dev-only credentials. The application itself is **not**
in the compose file. Run it from the repository root `Dockerfile`, or under a
process manager (systemd + `uvicorn`), pointing at the composed infra.

`--workers 1` is the supported reference topology. `--workers N` works with two
documented caveats (WebSocket cancel + per-process `/metrics`); see checklist
step 4.

## Health & observability

- Deep `GET /health` runs concurrent liveness checks against every backing
  store and returns `503` (with the failing dependency named) when any is down
  — load-balancer friendly. It never echoes connection strings or credentials.
- `GET /metrics` exposes Prometheus counters/histograms/gauges (unauthenticated
  — protect it at the proxy, checklist step 6).
- The admin dashboard **System** panel surfaces the same health plus document
  backlog, index freshness, and 24h audit activity.
