#!/usr/bin/env bash
# Keyless replay smoke: schema/route tests, then probe a running loopback backend.
# Usage: bash scripts/verify_replay.sh   (BACKEND_URL defaults to http://127.0.0.1:8000)
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -x .venv/bin/python ]]; then
    echo "Run scripts/setup.sh --backend-only first." >&2
    exit 1
fi

.venv/bin/python -m pytest backend/tests/core/test_contracts.py backend/tests/core/test_replay.py -q

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}" .venv/bin/python - <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from backend.app.replay import validate_replay_stream
from backend.app.schemas import parse_json, schema_validator

base = os.environ["BACKEND_URL"].rstrip("/")
origin = "http://localhost:5173"
fixtures = Path("shared/fixtures")


def get(path):
    request = urllib.request.Request(base + path, headers={"Origin": origin})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()
    except OSError as error:
        sys.exit(f"FAIL: backend not reachable at {base}: {error}")


def check(condition, message):
    if not condition:
        sys.exit(f"FAIL: {message}")
    print(f"ok: {message}")


status, headers, body = get("/healthz")
check(status == 200 and json.loads(body) == {"schema_version": "1.0", "status": "ok"}, "healthz 200 v1.0")

status, headers, body = get("/api/v1/replay/manifest")
check(status == 200, "manifest 200")
manifest = parse_json(body.decode("utf-8"))
schema_validator("replay-manifest.schema.json").validate(manifest)
check(manifest == parse_json((fixtures / "manifest.json").read_text()), "manifest matches tracked file")
check(headers.get("access-control-allow-origin") == origin, "manifest allows the local frontend origin")

for entry in manifest["fixtures"]:
    status, headers, body = get(f"/api/v1/replay/{entry['id']}")
    check(status == 200 and headers.get("content-type") == "application/x-ndjson", f"{entry['id']} 200 x-ndjson")
    check(headers.get("cache-control") == "no-store", f"{entry['id']} no-store")
    check(body == (fixtures / entry["file"]).read_bytes(), f"{entry['id']} byte-for-byte")
    validate_replay_stream(body, entry["duration_ms"])

status, _, body = get("/api/v1/replay/does_not_exist")
check(status == 404 and json.loads(body)["code"] == "REPLAY_NOT_FOUND", "unknown fixture 404 REPLAY_NOT_FOUND")
print(f"verify_replay: PASS ({len(manifest['fixtures'])} fixtures, default {manifest['default_fixture']})")
PY
