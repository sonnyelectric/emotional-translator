#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if (( $# > 1 )); then
    echo "Usage: $0 [--backend-only|--frontend-only|--live]" >&2
    exit 2
fi
target="${1:-all}"
case "$target" in
    all|--backend-only|--frontend-only|--live) ;;
    *) echo "Usage: $0 [--backend-only|--frontend-only|--live]" >&2; exit 2 ;;
esac

if [[ "$target" == --live && ! -f backend/requirements-live.lock ]]; then
    echo "Live setup requires backend/requirements-live.lock from B-04." >&2
    exit 1
fi

if [[ "$target" != --frontend-only ]]; then
    if [[ ! -x .venv/bin/python ]]; then
        "${PYTHON_BIN:-python3.11}" -m venv .venv
    fi
    .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else "Backend setup requires Python 3.11.")'
    requirements=(-r backend/requirements.lock)
    if [[ "$target" == --live ]]; then
        requirements+=(-r backend/requirements-live.lock)
    fi
    .venv/bin/python -m pip install "${requirements[@]}"
fi

if [[ "$target" != --backend-only ]]; then
    if [[ ! -f frontend/package-lock.json ]]; then
        echo "Frontend setup requires frontend/package-lock.json from C-01." >&2
        exit 1
    fi
    npm --prefix frontend ci
fi
