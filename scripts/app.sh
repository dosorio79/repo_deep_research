#!/usr/bin/env bash
set -euo pipefail

api_pid=""
api_ready=""

cleanup() {
  if [ -n "$api_pid" ]; then
    kill "$api_pid" 2>/dev/null || true
  fi
}

trap cleanup INT TERM EXIT

if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  printf '%s\n' 'Starting API at http://127.0.0.1:8000'
  uv run uvicorn repo_research.api:app --reload &
  api_pid=$!
else
  printf '%s\n' 'API already available at http://127.0.0.1:8000'
fi

for _attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    api_ready=1
    break
  fi
  sleep 1
done

if [ -z "$api_ready" ]; then
  printf '%s\n' 'API did not become available at http://127.0.0.1:8000/health' >&2
  exit 1
fi

printf '%s\n' 'Open frontend at http://127.0.0.1:5173'
printf '%s\n' 'Frontend API base URL is /api, proxied to http://127.0.0.1:8000'
cd frontend
npm run dev
