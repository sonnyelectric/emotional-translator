# Hackathon build plan: Berkeley Startup Sprint, 2026-11-20

Owner: Roderich (solo, with AI agents). Submissions close 4 PM PT; the demo fair runs 4–5:15 PM.
Research behind each decision is in `docs/research/R1–R5` and is synthesized in `docs/research/SYNTHESIS.md`.

## 1. What we are building (one sentence)

Live captions that also show **how** something was said. The app draws a colored, shaped cloud around the exact words, based on detected vocal tone. It also flags the moment when **the words and the voice disagree**.

## 2. Who it is for, and why judges should care

- **Primary user:** Deaf and hard-of-hearing people who read captions. Captions carry the words but drop the tone. WHO projects nearly 2.5 billion people will have some hearing loss by 2050 (R3).
- **Also:** cochlear-implant users (pitch cues are degraded, R3) and anyone who finds tone hard to read. That includes some autistic people, language learners, and people reading meeting captions. We frame it as an optional extra channel, never as a "fix" for anyone (R3, double-empathy framing).
- **Rubric fit:** user evidence (25 points) comes from cited research and live feedback from 2–3 attendees today. Usefulness (25) comes from a working live demo. Technical execution (25) comes from real streaming STT, a real local model, and word-level alignment. Differentiation (15) is the words-versus-voice flag plus word-anchored clouds, contrasted with Google Expressive Captions (R4). Demo clarity (10) comes from a scripted 3-minute walkthrough.

## 3. Decisions (changes to the TDD are marked NEW)

| # | Decision | Because |
|---|---|---|
| D1 | Keep **ElevenLabs Scribe v3 Live** as the only speech-to-text. | ElevenLabs sponsors the event: every participant gets credits, and there is a "Best Project Built with ElevenLabs" prize. Pricing is $0.22/hour (R1). |
| D2 | Keep the **emotion2vec+ Large** local model via `funasr.AutoModel`, on CPU by default. | It is real and on-device, and its scores are softmax probabilities (R2). Weights are 1.95 GB. Pre-download them tonight. |
| D3 | NEW: **Words-versus-voice flag.** A DistilBERT SST-2 text-sentiment model runs in the browser (transformers.js, Web Worker). It flags only when text sentiment is at least 0.9 and the voice shows a visible non-neutral emotion of the opposite valence. The label reads "Words and voice differ", never "sarcasm". | It is novel (R4 found no product doing this) and honest. It runs in the frontend, so the backend contract does not change (R5). |
| D4 | NEW: **Emotion profile panel** (from mockup image 2). A hand-rolled SVG radar shows the six visible categories (angry, disgusted, fearful, happy, sad, surprised) for the latest analyzed segment. It sits beside a "current mix" bar list. | It matches the mockup, and the TDD had already planned a radar as post-core work. |
| D5 | NEW: **Mockup items we will NOT build.** No "Disdain/Sarcasm" or "Embarrassment" categories, and no Prosody/Semantics/Multimodal weight sliders. | The model has no such labels, and no fusion exists. Showing them would fake output. |
| D6 | NEW: **Accessibility settings.** A toggle for emotion labels, a color-blind-safe palette (Okabe-Ito), and reduced motion. | Each cloud carries shape plus color plus an optional label (WCAG 1.4.1). Over half of study participants wanted toggles (R3). |
| D7 | Scribe adapter fixes from R1: send `model_id=scribe_v3_live` explicitly; times are **seconds**; drop `words[].type=="spacing"` items; handle the extra error codes. | The TDD missed these details. |
| D8 | Mic capture: default-rate AudioContext; resample to 16 kHz and convert to Int16 in the worklet; 40 ms chunks; echo cancellation, noise suppression and auto gain all **off**. | Per R5. Processing that changes the voice could change the emotion signal. |
| D9 | Replay stays the labeled backup. Once the API key works, record one real live session's **events** (no audio) as `replay_live_recorded.jsonl`. | Honest backup that uses the same UI. |
| D10 | NEW: **Static replay build** (`npm run build:replay`). It can be hosted on the hackathon site or Replit with a visible REPLAY banner and no backend. | Lets judges open a link afterwards. |

## 4. Agent roster

| Agent | Model | Lane, with the work orders it covers | Writes only to |
|---|---|---|---|
| Researchers R1–R5 | Sonnet 5.5 | Done. Cited reports in `docs/research/`. | `docs/research/` |
| Judge J1 (synthesis) | Opus 5.5 | Turns R1–R5 into verified facts for each lane, TDD amendments, and conflicts. | `docs/research/SYNTHESIS.md` |
| Builder BA | Opus 5.5 | Backend: A-02 replay HTTP, A-03 clock and relay, A-04 alignment, A-05 recovery. | `backend/app/` except the B paths, `backend/tests/core`, `shared/`, `scripts/start_*` |
| Builder BB1 | Sonnet 5.5 | Model: B-02 scorer policy, B-04 real Large model, B-05 bounded worker, B-06 benchmark. Actually installs and runs the model on this M4. | `backend/app/emotion/`, `backend/app/adapters/emotion2vec.py`, `backend/app/audio/window_scheduler.py`, `backend/tests/audio_ai/`, `backend/tests/fakes/`, `backend/requirements-live.lock`, `scripts/benchmark_emotion.py`, `docs/live/` |
| Builder BB2 | Sonnet 5.5 | Scribe: B-03 adapter plus `scripts/smoke_scribe.py`, against a fake upstream. Live smoke runs once the key exists. | `backend/app/adapters/scribe.py`, `backend/tests/audio_ai/test_scribe*.py`, `scripts/smoke_scribe.py`, `docs/live/scribe-preflight.md` |
| Builder BC1 | Opus 5.5 | Frontend shell: C-01, C-02, C-03 capture, C-05 resilience. App, protocol, reducer, replay, controls, history. | `frontend/` except `src/visual/` and `src/mismatch/` |
| Builder BC2 | Sonnet 5.5 | Visuals: C-04 clouds, radar, current mix, phrase inspector, settings, plus the D3 mismatch worker. Pure components against a props contract. | `frontend/src/visual/`, `frontend/src/mismatch/` |
| Builder BD | Sonnet 5.5 | Pitch: talk track, judge Q&A, submission text, backup-video shot list, rehearsal lines. | `docs/pitch/` |
| Integrator I1 | Opus 5.5 | Merges the lanes, wires the end-to-end path, runs G1 (replay) and G3 (real model), and fixes breaks. | anywhere |
| Judge J2 (review) | Opus 5.5 | Scores the product, demo and script against the rubric; writes the review; lists fixes. | `docs/REVIEW.md` |

Each builder works in its own git worktree and branch. The integrator merges them in dependency order: BA, then BB1 and BB2, then BC1, then BC2.

## 5. Interfaces fixed before builders start

- Wire protocol: `docs/PROTOCOL.md` and `shared/schemas/v1/`. Unchanged; D3 needs no schema change.
- Backend ports: `backend/app/audio_ai_ports.py` and `docs/PIPELINE.md`.
- Visual props contract between BC1 and BC2: `frontend/src/visual/contract.ts`. BC2 creates it first, and BC1 imports from it. The integrator reconciles any drift.
  - `TranscriptView({ segments, partial, annotations, settings, onInspect })` renders the text plus clouds.
  - `EmotionProfile({ latest: ScoreMap | null, settings })` renders the radar plus the current-mix bars.
  - `PhraseInspector({ annotation | null, onClose })`.
  - `SettingsPanel({ settings, onChange })`, with `settings = { showLabels, palette: 'default'|'cvd', reducedMotion, mismatch }`.
  - `useMismatch(segments, annotations) → Map<segment_id, {textSentiment, score, voice, differs}>`.
- Dependencies that only BC1 may add to `package.json`: `@huggingface/transformers` (for BC2).

## 6. Timeline (tonight, PT)

1. 01:30–02:00: research (done), plan (this file), J1 synthesis.
2. 02:00–04:00: builders BA, BB1, BB2, BC1, BC2 and BD in parallel. BB1 downloads the model weights early.
3. 04:00–05:00: integrator merges and runs replay plus the real model with fake Scribe.
4. 05:00–05:30: J2 review, fixes, demo run on localhost.
5. At the event, once the ElevenLabs key is redeemed: live Scribe smoke, record the real replay, rehearse, interview 2–3 attendees, film the backup video, submit before 4 PM.

## 7. Honesty rules for every agent

Never fabricate model output, timestamps, statistics, quotes or user feedback. Replay is always visibly labeled. Speak of "detected vocal cues", not feelings. Every factual claim in the pitch cites its `docs/research` source.
