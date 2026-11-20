# Emotional Translator

Live captions that also show **how** something was said: a soft, shaped cloud around the words, driven by detected vocal cues (emotion2vec+ Large, local), plus a "Words and voice differ" flag. Replay is always labeled REPLAY.

## Run the demo

One-time setup (Python 3.11, Node 20.19+): `scripts/setup.sh --live` (or `scripts/setup.sh` for replay only). Model weights live outside the repo in `~/model-cache/emotion2vec_plus_large/` ([model runtime](docs/live/model-runtime.md)). Ports: backend 8000, frontend 5173.

| What | Command | Needs |
|---|---|---|
| **Replay** (saved, labeled; no key, no model) | `scripts/demo_replay.sh`, then open http://localhost:5173, choose **Replay**, press **Start** | venv + `npm --prefix frontend ci` |
| **Live** (mic -> Scribe v3 Live + local emotion model) | put `ELEVENLABS_API_KEY=...` in `backend/.env` (never commit it), then `scripts/demo_live.sh`, open http://localhost:5173, press **Start** | live deps, weights, key |
| **Tuning** (model only, no transcript, no key) | `scripts/demo_live.sh`, open http://localhost:5173/?tune=1, press **Start mic**. From a WAV: `.venv/bin/python scripts/tune_wav.py --wav file-16k-mono.wav` | live deps, weights |
| **Scribe smoke** (decides `SCRIBE_TIMESTAMP_BASIS`) | `.venv/bin/python scripts/smoke_scribe.py --wav /abs/consented-16k-mono.wav`, then set `SCRIBE_TIMESTAMP_BASIS` in `backend/.env` from its verdict ([preflight](docs/live/scribe-preflight.md)) | key |
| **Static replay build** (no backend; host anywhere) | `npm --prefix frontend run build:replay` -> `frontend/dist-replay/` (`npm --prefix frontend run preview:replay` to check) | Node |

Without a key, `demo_live.sh` still loads the model; pressing Start in Live shows "Live session ended. Live transcription is not configured on this laptop. Replay still works." with a **Switch to Replay** button, and Tuning mode works ([run log](docs/live/integration-run.md)). With `SCRIBE_TIMESTAMP_BASIS=unknown` (default) captions appear but clouds are not placed until the smoke test proves the basis. If the smoke test shows segment-relative times, `segment` places clouds on the first commit of each connection only (press Pause then Resume before each line); see the [preflight table](docs/live/scribe-preflight.md). Thresholds are the `EMOTION_*` values in [.env.example](.env.example); copy to `backend/.env` and restart to change them.

Tests: `.venv/bin/python -m pytest backend/tests -q` (add `RUN_LIVE_MODEL=1` for the real-model test) · `npm --prefix frontend run typecheck && npm --prefix frontend test` · `PW_CHANNEL=chrome npm --prefix frontend run test:e2e` · `npm --prefix frontend run check:fixtures` (runs the real text-sentiment model over every replay fixture and fails if any segment would show a false "Words and voice differ" badge).

Recorded replay (opt-in): set `RECORD_SESSION_EVENTS=shared/fixtures/replay_live_recorded.jsonl` in `backend/.env` before a live run. When the session stops, its server events (text, timestamps, scores; never audio) become a validated replay fixture labelled "Recorded live session" and the default replay. Without the flag nothing is stored. Every bundled fixture is otherwise a synthetic example (hand-written, not model output), and the UI says so.

Hosted live backend (Replit Reserved VM) + Vercel frontend: [docs/DEPLOY_REPLIT.md](docs/DEPLOY_REPLIT.md). Weights on a fresh box: `scripts/fetch_model.sh` (pinned revision, sha256-checked).

Screenshots: [docs/screenshots/](docs/screenshots/). Pitch and rehearsal: [docs/pitch/](docs/pitch/).

---

# Implementation kit

Use this kit to start a fresh GitHub monorepo with three developers and three coding agents. The included TDD is the product baseline. The kit supplies the work orders, interfaces, and synthetic example data each agent needs before implementation. The K0 snapshot means these kit files are available to all three builders.

## Start here

1. **Developer A, backend and integration:** Create the shared repository and publish K0 as described in [Setup](docs/SETUP.md). Give each teammate access and the same base commit. Start [A-01](docs/prompts/A-01.md).
2. **Developer B, audio and AI:** Clone the shared repository and start [B-01](docs/prompts/B-01.md) using the B setup instructions. B owns the Scribe adapter, real emotion2vec+ Large adapter, scheduling, smoothing, and benchmarks. [Setup](docs/SETUP.md#builder-b--audio-and-ai)
3. **Developer C, frontend:** Clone the shared repository and start [C-01](docs/prompts/C-01.md) using the C setup instructions. C owns the browser microphone, React state and UI, SVG clouds, and visual checks. [Setup](docs/SETUP.md#builder-c--frontend)

Give each agent one prompt file at a time, the repo checkout with the listed prerequisites, and the applicable files under `docs/` and `shared/`. Bring results back with the PR evidence template. [Prompt schedule](docs/DEPENDENCIES.md) · [Handoff workflow](docs/HANDOFFS.md)

## What the team delivers

- **First development milestone:** Once the dependencies have been installed, A starts a keyless local FastAPI process and C starts the frontend. A synthetic saved event stream drives the real shared reducer and shows partial-to-final text, animated phrase clouds, multiline wrap, and history through loopback. See the exact checks for segments, revisions, and controls. [G1 acceptance](docs/ACCEPTANCE.md#g1--offline-vertical-slice)
- **Hackathon centerpiece:** Live microphone audio reaches ElevenLabs Scribe v3 Live in VAD mode and the real, locally loaded emotion2vec+ Large model. Timestamped phrases receive clouds driven by scored windows. Show live first and use visibly labeled saved replay if needed. [Live gates and rehearsal](docs/ACCEPTANCE.md) · [Demo runbook](docs/DEMO.md)

## Files

| Need | Start with |
|---|---|
| Product requirements and the 16 frozen decisions | [TDD](docs/TDD.md), [decision traceability](docs/DECISIONS.md) |
| Ownership, paths, and machine setup | [Repository plan](docs/REPOSITORY.md), [builder setup](docs/SETUP.md), [environment template](.env.example) |
| Browser and backend agreement | [Protocol](docs/PROTOCOL.md), [JSON Schemas](shared/schemas/v1/server-event.schema.json), [fixture guide](shared/fixtures/README.md) |
| Backend and adapter agreement | [Pipeline interfaces](docs/PIPELINE.md) |
| Parallel work and evidence | [Dependency graph](docs/DEPENDENCIES.md), [acceptance checks](docs/ACCEPTANCE.md), [handoff workflow](docs/HANDOFFS.md) |

The repository tree describes files the builders will create. Start from K0 and reviewed prerequisite commits, even if you have an exploratory prototype elsewhere. The example fixture provenance is `synthetic_example`. The copy of the TDD in this kit is verbatim.
