#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if (( $# > 1 )); then
    echo "Usage: $0 [--replay|--live]" >&2
    exit 2
fi
case "${1:---replay}" in
    --replay) export TRANSLATOR_MODE=replay ;;
    --live)
        if [[ ! -f backend/requirements-live.lock ]]; then
            echo "Live launch requires B-04's runtime. Run scripts/setup.sh --live once it lands." >&2
            exit 1
        fi
        export TRANSLATOR_MODE=live
        ;;
    *) echo "Usage: $0 [--replay|--live]" >&2; exit 2 ;;
esac

if [[ ! -x .venv/bin/python ]]; then
    echo "Run scripts/setup.sh --backend-only first." >&2
    exit 1
fi
# HOST defaults to loopback; a hosted deployment sets HOST=0.0.0.0. PORT (hosting platforms)
# wins over BACKEND_PORT (local scripts). Always exactly one worker: the live lease, model and
# daily cap are per process.
host="${HOST:-127.0.0.1}"
port="${PORT:-${BACKEND_PORT:-8000}}"
exec .venv/bin/python -m uvicorn backend.app.main:create_app --factory --host "$host" --port "$port" --workers 1
