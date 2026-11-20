# Model runtime (B-04), verified on this M4

## Install (Python 3.11)
```
uv python install 3.11 && uv venv --python 3.11 .venv-live
uv pip install --python .venv-live/bin/python -r backend/requirements-live.lock
```
`backend/requirements-live.lock` is the freeze of the venv that ran the model (core lock included). Key pins: funasr 1.4.27, modelscope 1.40.3, torch 2.15.0, torchaudio 2.11.1, numpy 2.4.6. Install order mattered not; everything resolved in one `uv pip install` of the core lock + funasr modelscope torch torchaudio numpy psutil. numpy 2.x works with funasr 1.4.27.

## Weights
`scripts/fetch_model.sh` performs this download (skips present files, verifies model.pt sha256 `be501a01…784da4`). Linux x86_64 CPU install: `backend/requirements-live-linux.txt` (same pins; torch/torchaudio `+cpu` from the PyTorch CPU index).
Download once from Hugging Face `emotion2vec/emotion2vec_plus_large` rev 6c303ba987b86b93193de93e34bb2b077a6bedc4 into `~/model-cache/emotion2vec_plus_large/` (config.yaml, configuration.json, tokens.txt, model.pt 1,945,790,254 B). Never commit weights. `Emotion2vecLargeScorer(cache_dir=...)` loads that directory (or `<cache_dir>/emotion2vec_plus_large`); with `cache_dir=None` it uses env `EMOTION_MODEL_CACHE_DIR`, else falls back to the hub id (network). Loading from the local directory needs no network. Loading prints a harmless "miss key in ckpt ... decoder" warning (pre-training decoder not in the checkpoint; "All keys matched successfully" is also logged).

## Call and observed return (REAL)
`AutoModel(model=<dir>, device="cpu", disable_update=True)`; `model.generate(wav_float32, granularity="utterance", extract_embedding=False, disable_pbar=True)` (all kwargs accepted by 1.4.27). Observed return for `example/test.wav`:
```
[{'key': 'test',
  'labels': ['生气/angry','厌恶/disgusted','恐惧/fearful','开心/happy','中立/neutral','其他/other','难过/sad','吃惊/surprised','<unk>'],
  'scores': [1.0, 4.3e-12, 7.7e-12, 1.8e-10, 7.2e-11, 1.4e-14, 9.8e-11, 8.9e-10, 5.7e-21]}]
```
- A list with one dict; `labels` are bilingual `中文/english`, ninth is `<unk>`; `scores` are Python floats, 9 entries aligned with labels, softmax (sum 1.0000000743 observed).
- Mapping: `split("/")[-1]`, `<unk>` -> `unknown`, anything else rejected. `score_kind = probability_like`; scores renormalized to exactly 1 after a 1e-3 sum check. Label-only, missing, negative, NaN/inf, duplicate, wrong-length output raises `ScoringError`.
- Input: float32 mono 16 kHz in [-1, 1] (`s16le / 32768`). On 1.4.27 an int16 numpy array gave identical scores (max diff 0.0), but we always pass float32 so older funasr cannot overdrive it.
- Scores for a numpy window and a file path both work; MPS (`device="mps"`) works and matches CPU top labels 69/69.

## Components
- `backend/app/audio/window_scheduler.py` `WindowScheduler`: 32,000-sample windows every 16,000, 8 s bounded ring, copies windows, never pads tail, no joining across epochs or forward gaps.
- `backend/app/emotion/worker.py` `BoundedEmotionWorker(scorer, *, max_pending=2, silence_rms=0.003, clock_ms=...)`: one load off-loop, single-thread executor, drop-oldest-pending with a `dropped` notice, `silence` / `failed` / `scored` notices, `discard(session_id, epoch=)` removes pending and quarantines a running result (counted in `stats.stale_results`, no notice).
- `backend/app/emotion/smoothing.py`: `smooth`, `classify` (pure; `DefaultScorePolicy` bundles them). `classify` hysteresis applies only when the previous state has the same primary label; opacity follows support breakpoints (faint 0.14-0.30 over support 0.25-0.42, standard 0.35-0.75 over 0.42-1.0).
- Test fake: `backend/tests/fakes/emotion.py` `FakeEmotionScorer(vectors_by_start, cycle=, fail_on=, block_on=)`; `.release` / `.entered` threading events.

## Tests
`pytest backend/tests -q` (no model needed): 100 pass. `RUN_LIVE_MODEL=1 pytest backend/tests/live` adds a real-model test (101 pass).
