#!/bin/sh
set -eu

python -m uvicorn api:app --host 127.0.0.1 --port 8000 &
API_PID=$!

cd /app/frontend
npm run start -- --hostname 127.0.0.1 --port 3001 &
UI_PID=$!

cd /app

cleanup() {
  kill "$API_PID" "$UI_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

nginx -g "daemon off;"
