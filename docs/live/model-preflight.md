# Model preflight (B-01)

Status: **preflight only.** No model was downloaded, loaded or scored. Everything under "Verified" was observed on 2026-11-19; everything under "Proposed" is a candidate that G3 must prove on the judging laptop.

## 1. Command

```bash
python scripts/inspect_emotion.py --check [--cache-dir PATH] [--json]
```

- Standard library only. It reads installed-package metadata (`importlib.metadata`), stats the cache path, and runs `sysctl`/`system_profiler` (macOS) or `/proc` and `nvidia-smi` (Linux) for hardware. It does not import `torch`/`funasr`, open a socket, or read cache contents.
- Cache path comes from `--cache-dir`, else `EMOTION_MODEL_CACHE_DIR`. Missing packages or a missing cache are printed as **findings**, not errors (exit 0).
- A cache path inside the repo is flagged, because weights must stay out of Git.
- `--download` and `--score` are not implemented; B-04 owns them.

## 2. Verified environment (this laptop, not yet confirmed as the judging laptop)

| Item | Observed |
|---|---|
| OS | macOS 27.0.1 (Darwin 27.0.0), arm64 |
| CPU / GPU | Apple M4, 10 logical cores; integrated Apple GPU |
| RAM | 24 GiB |
| System Python | 3.13.15 (clean venv: no relevant packages installed) |
| Model cache | none configured, none present |

## 3. Model source and licence

**Verified from the sources on 2026-11-19:**

- Model ID used by the app: `iic/emotion2vec_plus_large` (ModelScope ID, which FunASR resolves). The Hugging Face mirror is `emotion2vec/emotion2vec_plus_large`, which its card says has identical parameters. HF revision observed: `6c303ba987b86b93193de93e34bb2b077a6bedc4` (last modified 2024-06-24). Weights file is `model.pt` (not fetched).
- Card: about 300M parameters, 16 kHz input, nine labels in order `0 angry, 1 disgusted, 2 fearful, 3 happy, 4 neutral, 5 other, 6 sad, 7 surprised, 8 unknown`. Official example: `AutoModel(model="iic/emotion2vec_plus_large")` then `model.generate(wav, granularity="utterance", extract_embedding=False)`; the model downloads automatically on first use. The card's widget metadata suggests about 4 GB memory for inference (a hint, not a measurement).
- Licence: the HF card says `license: other`, name `model-license`, linking to the FunASR repo. The FunASR `MODEL_LICENSE` (v1.1) permits use, copying, modification and sharing, and requires attribution to the source/author and keeping the model name. It also disclaims liability and terminates the licence on "unjustified denigration" of the software. The emotion2vec GitHub README shows an MIT badge. Code packages: `funasr` MIT, `modelscope` Apache-2.0, `torch` BSD-style/Apache.

**Pending confirmation (do not treat as cleared):**

1. Which text governs the weights: the HF card's `other` pointing to FunASR `MODEL_LICENSE`, or the MIT badge on the emotion2vec repo. They differ.
2. Whether the ModelScope page for `iic/emotion2vec_plus_large` states terms of its own.
3. Whether the training data (large pseudo-labelled set) imposes any condition on use. The card does not say.
4. Whether commercial or hackathon-judging use is allowed. The text read does not restrict it, but that is not a legal confirmation.
5. Rule for now: each developer downloads from the official source into their own cache. Do not redistribute or bundle `model.pt`; add attribution (name + source) to the README/demo credits.

## 4. Candidate stack (PROPOSED, not verified to work)

Latest releases seen on PyPI on 2026-11-19. None has been installed or run with this model.

| Component | Candidate pin | Why / risk |
|---|---|---|
| Python | 3.11 (matches TDD/A candidate) | `torch` 2.15 needs >=3.11; `modelscope` needs >=3.10. 3.13 is installed on this laptop, but older FunASR code is less likely to be tested there. Use 3.11 unless G3 shows otherwise. |
| `funasr` | 1.4.27 | Latest; model card says `pip install -U funasr modelscope`. |
| `modelscope` | 1.40.3 | Needed for the `iic/...` download path. |
| `torch` | 2.15.0 | Latest; check Apple `mps` vs CPU. CPU is the safe default. |
| `torchaudio` | match the `torch` release | PyPI JSON lookup failed for it; resolve with pip. |
| `numpy` | a version compatible with the above | 2.5.2 is already on this laptop's system Python. |

Pin exact versions in B-04's live lock only after a successful run on the target laptop. Cache: choose a directory outside the repo (for example `~/model-cache/emotion2vec`) and put it in `backend/.env` as `EMOTION_MODEL_CACHE_DIR`. Check how FunASR/ModelScope honour this variable in B-04, since both also have their own default cache locations (not verified here).

## 5. Checklist for A (machine selection and permissions)

- [ ] Name the judging laptop. If it is not this M4/24 GiB machine, re-run `--check` on it.
- [ ] Confirm Python 3.11 can be installed (this machine has 3.13 only on PATH) and agree the version with B.
- [ ] Confirm about 5 GB free disk outside the repo for the cache (estimate; actual `model.pt` size not checked).
- [ ] Confirm internet access for the one-time download from ModelScope or HF, then an offline run.
- [ ] Decide that `setup.sh --live` must not download weights automatically. Download stays an explicit B-04 step.
- [ ] Confirm microphone permission for the browser and that the backend may bind loopback only.
- [ ] Runtime or permission conflicts found so far: none confirmed. Possible conflicts to watch: Python 3.13 vs 3.11 choice, and `torch` 2.15 wheel availability for macOS arm64 on 3.11 (unchecked).

## 6. Fields B-04 must record from real output inspection and benchmark

- Environment: OS, CPU/GPU, RAM, exact Python, `funasr`, `modelscope`, `torch`, `torchaudio`, `numpy` versions, device used (cpu/mps).
- Model: ID, source (ModelScope or HF), revision/commit, `model.pt` size and checksum, cache path convention, licence text version consulted.
- Output shape from a real `generate()` call: top-level type, keys, label list and order, score layout (length, raw sum, range, any negative or non-finite value), label string form (for example Chinese/English mixed names), and whether embeddings were absent.
- Score decision, per [Pipeline "Scores and visual classification"](../PIPELINE.md#scores-and-visual-classification): which `score_kind` the real vector supports (`probability_like` or `comparable`) and the evidence for it. For `probability_like`, the observed raw sums and whether they fall within the 1e-3 unit-sum tolerance after normalization. For `comparable`, the documented bounded [0,1] conversion. The exact mapping from model label order and strings to the nine schema labels in schema order, with only proven aliases. How label-only, incomplete, negative or non-finite output is detected and failed.
- Input: sample rate, dtype, window length (32000 samples at 16 kHz), whether a numpy array can be passed instead of a file path.
- Performance (per [Pipeline "Measurements"](../PIPELINE.md#measurements) and the HANDOFFS evidence rule): cold load time, RAM peak, inference run time and queue wait as p50/p95 in milliseconds with sample size, dropped/stale window counts over a 3-minute run at 2 s windows / 1 s hop, silence-gate energy threshold used, and the hardware it ran on.
- Behaviour: determinism across repeat runs, and the result on a permitted short local sample.

## 7. Handoff notes

- B-04: use the tested command above. Open questions are the licence items in section 3, the candidate pins in section 4, and everything in section 6 (no real model facts are known yet).
- Git hygiene: no weights, audio or keys were added. `.gitignore` already covers `.env*`, `model-cache/`, `models/` and audio extensions.
