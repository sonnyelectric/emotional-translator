#!/usr/bin/env bash
# One command: keyless replay backend (:8000) + frontend (:5173). No API key, no model.
# Everything shown is a saved, labeled replay. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -x .venv/bin/python ]] || { echo "Run scripts/setup.sh first (Python 3.11 venv)." >&2; exit 1; }
[[ -d frontend/node_modules ]] || { echo "Run: npm --prefix frontend ci" >&2; exit 1; }
for port in "${BACKEND_PORT:-8000}" 5173; do
    if lsof -ti tcp:"$port" >/dev/null 2>&1; then
        echo "Port $port is already in use. Stop that process first." >&2
        exit 1
    fi
done

pids=()
cleanup() { for p in "${pids[@]:-}"; do kill "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

scripts/start_backend.sh --replay &
pids+=($!)
for _ in $(seq 1 40); do
    curl -fsS "http://127.0.0.1:${BACKEND_PORT:-8000}/healthz" >/dev/null 2>&1 && break
    sleep 0.25
done
curl -fsS "http://127.0.0.1:${BACKEND_PORT:-8000}/healthz" >/dev/null || { echo "Backend did not start." >&2; exit 1; }

echo
echo "Replay demo: open http://localhost:5173 , pick Replay, press Start (replay_demo)."
echo
scripts/start_frontend.sh &
pids+=($!)
wait "${pids[@]}"
