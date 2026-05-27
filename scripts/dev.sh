#!/usr/bin/env bash
# Tomorrow's You — Local dev launcher
# Usage: bash scripts/dev.sh         (backend + frontend in parallel)
#        bash scripts/dev.sh backend
#        bash scripts/dev.sh frontend

set -euo pipefail
cd "$(dirname "$0")/.."

start_backend() {
  echo "[backend] starting uvicorn on :8001"
  exec uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload
}

start_frontend() {
  echo "[frontend] starting Next.js dev on :3000"
  cd frontend
  exec npm run dev
}

case "${1:-all}" in
  backend)  start_backend ;;
  frontend) start_frontend ;;
  all)
    start_backend &
    BACK_PID=$!
    start_frontend &
    FRONT_PID=$!
    trap "kill $BACK_PID $FRONT_PID 2>/dev/null || true" EXIT
    wait
    ;;
  *)
    echo "Usage: $0 [backend|frontend|all]"; exit 1 ;;
esac
