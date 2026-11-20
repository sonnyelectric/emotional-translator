#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f frontend/package-lock.json ]]; then
    echo "Frontend launch requires C-01. Run scripts/setup.sh --frontend-only once it lands." >&2
    exit 1
fi
exec npm --prefix frontend run dev -- --host localhost --port 5173 --strictPort
