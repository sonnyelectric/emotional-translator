# Emotion model benchmark (B-06, standalone)

Real model, real run, 2026-11-20. Standalone only: no Scribe, no browser, no integrated 3-minute mic run (not done; see Gaps).
Command: `python scripts/benchmark_emotion.py --wav <wav> [--device mps] --json <out>`; raw per-window JSON kept outside the repo.

## Environment
Apple M4 (10 cores), 24 GiB, macOS 27.0.1 arm64, Python 3.11.18, funasr 1.4.27, torch 2.15.0, torchaudio 2.11.1, numpy 2.4.6, modelscope 1.40.3.
Checkpoint: `iic/emotion2vec_plus_large`, HF revision 6c303ba987b86b93193de93e34bb2b077a6bedc4, local dir, `model.pt` 1,945,790,254 bytes.

## Input
`tts_mix.wav`: 72.7 s of 16 kHz mono speech made with macOS `say` (4 voices x 4 sentences: angry/happy/sad/neutral wording, 0.5 s gaps). It is synthetic TTS, not human emotional speech, so the labels below say nothing about accuracy. Latency does not depend on content. WindowScheduler produced 71 windows (2 s, 1 s hop); first 2 are warm-up, **69 timed**.

## Results (per 2 s window, wall clock around `score()`, no queueing)

| Device | Cold load | Warm load | Peak RSS | p50 | p95 | min | max |
|---|---|---|---|---|---|---|---|
| CPU (default) | 21.7 s (first ever load, disk cold) | 4.45 s | 2,454 MiB | 64.1 ms | 70.5 ms | 62.8 ms | 84.3 ms |
| MPS (experiment) | n/a | 4.57 s | 2,500 MiB | 29.8 ms | 31.0 ms | 29.3 ms | 41.0 ms |

Peak RSS is `ru_maxrss` of the whole process (model + torch). Example `test.wav` (4.1 s): 1 timed window 64.4 ms.

**p95 is about 70 ms against a 1,000 ms hop (about 7%). The hop is met with large margin; no drops are expected.** Mitigation if a slower laptop is used: the worker's max_pending=2 evicts the oldest not-yet-started window (TDD drop-stale rule); not triggered here. Under-load behaviour (drops with Scribe running) is covered by unit tests with a blocking fake, not measured live.

MPS: ran without error, top label identical on 69/69 windows, max score difference 1e-4 vs CPU, 2.15x faster. CPU stays the default (the extra speed is unneeded and MPS is less proven); MPS is a safe fallback option. Not tested for long runs.

## Observations about the scores (TTS input, not a claim of accuracy)
- Distributions are very peaked: many windows have top score 0.99-1.000.
- `unknown` wins on many pause-heavy/short-word windows (e.g. 0.65-0.98). The policy suppresses unknown-leading windows, so those render no cloud. Mostly-silent windows would be settled by the worker's RMS gate (0.003, about -50 dBFS) without inference; the benchmark script bypasses the worker, so gate hit-rate is unmeasured.
- Thresholds (alpha 0.55, 0.25/0.42, hysteresis 0.06) were NOT retuned; no human-voice data yet.

## Gaps (not done)
- Integrated 3-minute mic run with A/C, mic-to-partial, phrase-end-to-cloud: not measured.
- No real human emotional speech benchmark; run `--wav <consented.wav> --pace` for that.
- `--pace` flag implemented but not exercised in this run.
