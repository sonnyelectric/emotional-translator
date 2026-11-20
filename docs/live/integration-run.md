# Integration run (Integrator I1, 2026-11-20)

Real runs on this laptop: Apple M4, macOS 27.0.1, Python 3.11.18 (`.venv` from `backend/requirements.lock` + `backend/requirements-live.lock`), Node 22.23.5, Google Chrome 157.0.8103.79 via Playwright (`channel: chrome`). Ports 8000/5173. No ElevenLabs key existed; none was created or used.

## Replay stack (`scripts/demo_replay.sh`)
- Backend replay + Vite came up; `replay_demo` played to "Replay finished" in Chrome with no page errors. The REPLAY banner showed "Synthetic example: hand-written events, not model output". These clouds are authored fixture data, not model output.
- Screenshots: `docs/screenshots/01-main-replay.png` (profile left, transcript centre, history below), `02-phrase-inspector.png` (sad phrase, finalized, nine scores), `03-settings.png` (labels on, colour-blind palette, reduced motion on).
- Reduced motion: the last cloud path's `d` attribute was identical across 1.2 s with the setting on (static).
- Words-vs-voice browser model: first load failed in dev because the worker's local-bundle probe received Vite's `index.html` for `/models/...` (fixed: the worker now checks for a JSON response). After the fix it downloaded from Hugging Face and the Settings toggle stayed available. No fixture contains a mismatch line, so no badge is shown in replay.

## Live stack without a key (`scripts/demo_live.sh`)
- Backend log: "Live launch without ELEVENLABS_API_KEY; live start will report LIVE_NOT_CONFIGURED". Model loaded from `~/model-cache/emotion2vec_plus_large` ("All keys matched successfully").
- UI, Live > Start listening (fake Chrome mic): status pill "Error"; notice "Live session ended. Live transcription is not configured on this laptop. Replay still works." with a **Switch to Replay** button; no transcript segments; Reset enabled and the Replay mode switch enabled afterwards. Screenshot `04-live-no-key.png`.
- Tuning route, `scripts/tune_wav.py --wav ~/model-cache/emotion2vec_plus_large/example/test.wav --pace` (4.1 s, model state `ready` at connect): 3 of 3 windows scored.

  | Window | Top raw label | Raw score | classify() | model ms |
  |---|---|---|---|---|
  | 0-2 s | angry | 0.9994 | angry | 107.0 |
  | 1-3 s | angry | 1.0000 (rounded) | angry | 100.0 |
  | 2-4 s | angry | 1.0000 (rounded) | angry | 109.1 |

  An earlier run on port 8010 gave the same labels (model 112.1 / 100.2 / 103.6 ms). Model time here (~100-110 ms per window) is higher than the B-06 benchmark p95 of 70 ms; it is still about 10% of the 1 s hop. Not investigated (the dev server and Chrome were running alongside).
- Tuning page `?tune=1` with Chrome's fake microphone (a synthetic test tone, not speech): windows 0-5 s all scored, top raw label neutral (0.902 on the shown window), classify() "suppressed (no cloud)", model 91.3 ms. Screenshot `05-tuning-mode.png`. Says nothing about accuracy on real voices.
- `RUN_LIVE_MODEL=1 pytest backend/tests/live`: 1 passed.

## Not done
- No Scribe call (no key). Timestamp basis, end-to-end captions with clouds, and the live mismatch badge remain unverified until the key exists and `scripts/smoke_scribe.py` runs.
- No human-voice threshold tuning; use `?tune=1` for that.
