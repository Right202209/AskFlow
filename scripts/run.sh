#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="api"
SKIP_DOCKER=0
SKIP_MIGRATE=0
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-5173}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/run.sh [api|web|all] [--skip-docker] [--skip-migrate]

Modes:
  api   Start Docker dependencies, run migrations, then start FastAPI.
  web   Start the Vite frontend only.
  all   Start both backend and frontend together.

Options:
  --skip-docker   Skip "docker compose up -d"
  --skip-migrate  Skip "alembic upgrade head"
  -h, --help      Show this help message

Environment variables:
  API_HOST  Default: 0.0.0.0
  API_PORT  Default: 8000
  WEB_HOST  Default: 0.0.0.0
  WEB_PORT  Default: 5173
EOF
}

log() {
  printf '[run] %s\n' "$*"
}

fail() {
  printf '[run] %s\n' "$*" >&2
  exit 1
}

resolve_python() {
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    printf '%s\n' "$ROOT_DIR/.venv/bin/python"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi

  fail "Python was not found. Create .venv or install Python 3.11+ first."
}

ensure_npm() {
  command -v npm >/dev/null 2>&1 || fail "npm was not found. Install Node.js first."
}

ensure_docker_compose() {
  command -v docker >/dev/null 2>&1 || fail "docker was not found. Install Docker first."
  docker compose version >/dev/null 2>&1 || fail "docker compose is unavailable."
}

check_backend_dependencies() {
  "$PYTHON_BIN" -c "import uvicorn" >/dev/null 2>&1 || fail "uvicorn is missing. Run 'make install'."
  if (( SKIP_MIGRATE == 0 )); then
    "$PYTHON_BIN" -c "import alembic" >/dev/null 2>&1 || fail "alembic is missing. Run 'make install'."
  fi
}

check_frontend_dependencies() {
  ensure_npm
  [[ -f "$ROOT_DIR/web/package.json" ]] || fail "web/package.json was not found."
  [[ -d "$ROOT_DIR/web/node_modules" ]] || fail "Frontend dependencies are missing. Run 'make install-web'."
}

start_docker() {
  (( SKIP_DOCKER == 1 )) && return
  ensure_docker_compose
  log "Starting Docker services..."
  (
    cd "$ROOT_DIR"
    docker compose up -d
  )
}

run_migrations() {
  (( SKIP_MIGRATE == 1 )) && return
  log "Applying database migrations..."
  (
    cd "$ROOT_DIR"
    PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON_BIN" -m alembic upgrade head
  )
}

backend_command() {
  (
    cd "$ROOT_DIR"
    export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
    exec "$PYTHON_BIN" -m uvicorn askflow.main:create_app \
      --factory \
      --reload \
      --host "$API_HOST" \
      --port "$API_PORT"
  )
}

frontend_command() {
  (
    cd "$ROOT_DIR/web"
    exec npm run dev -- --host "$WEB_HOST" --port "$WEB_PORT"
  )
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      api|web|all)
        MODE="$1"
        ;;
      --skip-docker)
        SKIP_DOCKER=1
        ;;
      --skip-migrate)
        SKIP_MIGRATE=1
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        fail "Unknown argument: $1"
        ;;
    esac
    shift
  done
}

start_api() {
  check_backend_dependencies
  start_docker
  run_migrations
  log "Starting backend at http://localhost:$API_PORT"
  backend_command
}

start_web() {
  check_frontend_dependencies
  log "Starting frontend at http://localhost:$WEB_PORT"
  frontend_command
}

start_all() {
  local backend_pid
  local frontend_pid

  check_backend_dependencies
  check_frontend_dependencies
  start_docker
  run_migrations

  cleanup() {
    local exit_code=$?
    if [[ -n "${backend_pid:-}" ]]; then
      kill "$backend_pid" >/dev/null 2>&1 || true
    fi
    if [[ -n "${frontend_pid:-}" ]]; then
      kill "$frontend_pid" >/dev/null 2>&1 || true
    fi
    wait >/dev/null 2>&1 || true
    exit "$exit_code"
  }

  trap cleanup INT TERM EXIT

  log "Starting backend at http://localhost:$API_PORT"
  backend_command &
  backend_pid=$!

  log "Starting frontend at http://localhost:$WEB_PORT"
  frontend_command &
  frontend_pid=$!

  wait -n "$backend_pid" "$frontend_pid"
}

main() {
  parse_args "$@"

  if [[ ! -f "$ROOT_DIR/.env" ]]; then
    log ".env not found. Copy .env.example to .env if local configuration is required."
  fi

  case "$MODE" in
    api)
      PYTHON_BIN="$(resolve_python)"
      start_api
      ;;
    web)
      start_web
      ;;
    all)
      PYTHON_BIN="$(resolve_python)"
      start_all
      ;;
  esac
}

main "$@"
