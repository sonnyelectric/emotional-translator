#!/usr/bin/env bash
# One command: live backend with the real emotion2vec+ Large model (:8000) + frontend (:5173).
# Scribe needs ELEVENLABS_API_KEY in backend/.env. Without it the model still loads,
# Live start reports "Live mode is not configured", and Tuning mode (?tune=1) works.
# Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -x .venv/bin/python ]] || { echo "Run scripts/setup.sh --live first (Python 3.11 venv + live lock)." >&2; exit 1; }
.venv/bin/python -c 'import funasr' 2>/dev/null || { echo "Live deps missing. Run scripts/setup.sh --live." >&2; exit 1; }
[[ -d frontend/node_modules ]] || { echo "Run: npm --prefix frontend ci" >&2; exit 1; }

# Local weights (never committed). Override with EMOTION_MODEL_CACHE_DIR or backend/.env.
if [[ -z "${EMOTION_MODEL_CACHE_DIR:-}" && -f "$HOME/model-cache/emotion2vec_plus_large/model.pt" ]]; then
    export EMOTION_MODEL_CACHE_DIR="$HOME/model-cache/emotion2vec_plus_large"
fi
for port in "${BACKEND_PORT:-8000}" 5173; do
    if lsof -ti tcp:"$port" >/dev/null 2>&1; then
        echo "Port $port is already in use. Stop that process first." >&2
        exit 1
    fi
done
if ! grep -qE '^ELEVENLABS_API_KEY=.+' backend/.env 2>/dev/null && [[ -z "${ELEVENLABS_API_KEY:-}" ]]; then
    echo "Note: no ELEVENLABS_API_KEY in backend/.env. Live captions will report a setup error;"
    echo "      Tuning mode (http://localhost:5173/?tune=1) and Replay still work."
fi

# Local demo: keep the dev tuning page (?tune=1) available. Public deployments leave it off.
export ENABLE_TUNE_ROUTE="${ENABLE_TUNE_ROUTE:-1}"

pids=()
cleanup() { for p in "${pids[@]:-}"; do kill "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

scripts/start_backend.sh --live &
pids+=($!)
for _ in $(seq 1 60); do
    curl -fsS "http://127.0.0.1:${BACKEND_PORT:-8000}/healthz" >/dev/null 2>&1 && break
    sleep 0.5
done
curl -fsS "http://127.0.0.1:${BACKEND_PORT:-8000}/healthz" >/dev/null || { echo "Backend did not start." >&2; exit 1; }

echo
echo "Backend up. The model loads in the background (about 5 s warm, 20+ s cold);"
echo "the Tuning page shows 'Model: loading' until it is ready."
echo "  Live:   http://localhost:5173"
echo "  Tuning: http://localhost:5173/?tune=1   (model only, no transcript)"
echo
scripts/start_frontend.sh &
pids+=($!)
wait "${pids[@]}"
