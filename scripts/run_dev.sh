#!/usr/bin/env bash
# Launches backend (FastAPI on :8799) and frontend (Vite on :5174) together.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"

cleanup() {
  jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[dev] starting backend uvicorn :8799"
(cd "${ROOT}/backend" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8799 --reload) &

echo "[dev] starting vite :5174"
(cd "${ROOT}/frontend" && npm run dev) &

wait
