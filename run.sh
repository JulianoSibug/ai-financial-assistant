#!/usr/bin/env bash
# Starts Ledger. Dev mode (default) runs the backend and frontend dev server
# concurrently. `--prod` serves the already-built frontend/dist through the
# backend alone (run `npm run build` in frontend/ first).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROD=false
for arg in "$@"; do
  [[ "$arg" == "--prod" ]] && PROD=true
done

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

mkdir -p data

if command -v uv >/dev/null 2>&1; then
  echo "Setting up Python environment with uv..."
  [[ -d .venv ]] || uv venv .venv --quiet
  uv pip install -q -p .venv/bin/python -r backend/requirements.txt -r backend/requirements-dev.txt
else
  echo "uv not found, using venv + pip..."
  [[ -d .venv ]] || python3 -m venv .venv
  ./.venv/bin/pip install -q -r backend/requirements.txt -r backend/requirements-dev.txt
fi
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if $PROD; then
  if [[ ! -d frontend/dist ]]; then
    echo "frontend/dist not found. Run 'npm run build' in frontend/ first, or omit --prod for dev mode." >&2
    exit 1
  fi
  echo ""
  echo "Ledger is running: http://$HOST:$PORT"
  echo ""
  exec "$PYTHON" -m uvicorn backend.main:app --host "$HOST" --port "$PORT"
fi

FRONTEND_PORT=5173

cleanup() {
  echo ""
  echo "Shutting down..."
  # `npm run dev &` backgrounds the npm wrapper, not the vite process it
  # spawns -- npm doesn't forward TERM to its child, so killing the
  # tracked PID alone leaves vite (and the port) held open. Kill by port
  # instead, which is robust regardless of how each process was spawned.
  lsof -ti:"$PORT" -sTCP:LISTEN 2>/dev/null | xargs -r kill >/dev/null 2>&1 || true
  lsof -ti:"$FRONTEND_PORT" -sTCP:LISTEN 2>/dev/null | xargs -r kill >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

"$PYTHON" -m uvicorn backend.main:app --host "$HOST" --port "$PORT" --reload &
BACKEND_PID=$!

# Confirm it's actually still alive before moving on -- catches "port
# already in use" (or any other startup crash) immediately and loudly,
# instead of silently leaving a dead backend and a frontend that proxies
# to nothing (which surfaces to you as a browser "Bad Gateway").
sleep 1.5
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  echo "" >&2
  echo "Backend failed to start. Port $PORT may already be in use by another" >&2
  echo "process (including another Ledger window) -- check with:" >&2
  echo "  lsof -i:$PORT" >&2
  exit 1
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "Installing frontend dependencies..."
  (cd frontend && npm install)
fi

(cd frontend && npm run dev -- --port "$FRONTEND_PORT" --strictPort) &
FRONTEND_PID=$!

sleep 1
if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
  echo "" >&2
  echo "Frontend failed to start. Port $FRONTEND_PORT may already be in use --" >&2
  echo "check with:" >&2
  echo "  lsof -i:$FRONTEND_PORT" >&2
  exit 1
fi

echo ""
echo "Ledger is running: http://localhost:$FRONTEND_PORT"
echo ""

# If either process dies later on its own (crash, killed externally, etc.)
# rather than through Ctrl-C / window close, notice and bring the other
# down too instead of quietly leaving a half-working app running.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
echo "" >&2
echo "One of Ledger's processes stopped unexpectedly -- shutting the other down too." >&2
