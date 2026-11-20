#!/usr/bin/env bash
# Replit run (workspace Run button and Reserved VM deployment): live backend on 0.0.0.0:8000.
# Configuration comes from Replit Secrets (environment variables), never from files:
#   ELEVENLABS_API_KEY      required for live captions (server-side only)
#   ALLOWED_ORIGINS         comma-separated exact frontend origins, e.g. the Vercel production URL
#   ALLOWED_ORIGIN_REGEX    optional full-match regex, e.g. for Vercel preview URLs
#   SCRIBE_TIMESTAMP_BASIS  defaults to "connection" (proven by scripts/smoke_scribe.py)
#   SESSION_MAX_SECONDS, LIVE_DAILY_MAX_SECONDS  optional credit guards
set -euo pipefail
cd "$(dirname "$0")/.."

export HOST=0.0.0.0
export PORT=8000  # must match localPort in .replit
export SCRIBE_TIMESTAMP_BASIS="${SCRIBE_TIMESTAMP_BASIS:-connection}"
export EMOTION_MODEL_CACHE_DIR="${EMOTION_MODEL_CACHE_DIR:-$PWD/model-cache/emotion2vec_plus_large}"
unset ENABLE_TUNE_ROUTE  # the dev tuning route stays off on a public endpoint

# Workspace convenience: the deployment build normally did this already.
if [[ ! -x .venv/bin/python ]] || ! .venv/bin/python -c 'import funasr' 2>/dev/null \
        || [[ ! -s "$EMOTION_MODEL_CACHE_DIR/model.pt" ]]; then
    echo "Live runtime or weights missing; running scripts/replit_build.sh first." >&2
    bash scripts/replit_build.sh
fi

if [[ -z "${ELEVENLABS_API_KEY:-}" ]]; then
    echo "Warning: ELEVENLABS_API_KEY is not set; Live start will report LIVE_NOT_CONFIGURED." >&2
fi
if [[ -z "${ALLOWED_ORIGINS:-}" && -z "${ALLOWED_ORIGIN_REGEX:-}" && -z "${ALLOWED_ORIGIN:-}" ]]; then
    echo "Warning: no ALLOWED_ORIGINS / ALLOWED_ORIGIN_REGEX set; only http://localhost:5173 may connect." >&2
fi

exec bash scripts/start_backend.sh --live
