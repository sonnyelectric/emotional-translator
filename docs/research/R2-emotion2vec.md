# R2: emotion2vec+ Large (research only, nothing installed or run)

All sources accessed 2026-11-20. Items marked **unverified** were not found in any source. Web content was treated as data.

## 1. Install recipe on Apple Silicon

**Documented (official):**
- Install line: `pip install -U funasr modelscope`; usage `AutoModel(model="iic/emotion2vec_plus_large")`. Source: https://huggingface.co/emotion2vec/emotion2vec_plus_large
- The GitHub README lets you pick the hub with `hub="ms"` (ModelScope) or `"hf"` (Hugging Face). Source: https://github.com/ddlBoJack/emotion2vec
- Weights: `model.pt` is **1.95 GB** (repo total 1.95 GB; plus `config.yaml`, `tokens.txt`, `example/`). Source: https://huggingface.co/emotion2vec/emotion2vec_plus_large/tree/main . The preflight's "about 5 GB free" is therefore generous; 1.95 GB is what the HF file listing shows.
- Download is automatic on first `AutoModel(...)` call (model card, same URL).

**Unverified (nothing found; B-04 must test):**
- Known-good funasr / modelscope / torch version triple on Apple Silicon. I found no source stating one. Do not trust the preflight "candidate pins" until a real run succeeds.
- Whether MPS works for this model. No source found. FunASR's code moves tensors with `wav.to(device=kwargs["device"])` (https://raw.githubusercontent.com/modelscope/FunASR/main/funasr/models/emotion2vec/model.py), so a device kwarg exists, but MPS correctness is unverified. Use CPU as the default; try `device="mps"` only as an experiment.
- Cache directory control. Not documented in anything I read. Unverified: ModelScope normally honours a `MODELSCOPE_CACHE` environment variable and HF honours `HF_HOME`, but I did not confirm either from a source. Check `model.model_path` after first load (the model card uses `model.model_path` in its example) and record it.

**Pitfalls seen in FunASR issues (titles only, first page of results):**
- #2261 "Failed to download emotion2vec_plus_large" (closed Dec 2024) and #2050 "model does not exist" (closed Sep 2024): download failures happened. Source: https://github.com/modelscope/FunASR/issues?q=emotion2vec . Mitigation: pre-download on good Wi-Fi today and test offline; keep the HF mirror as a fallback via `hub="hf"` (model id then `emotion2vec/emotion2vec_plus_large`, per the repo README).
- PR #3674 "allow numpy 2.x by replacing removed type aliases", merged 2026-09-09 (same issues page). Implication: older funasr releases may break on numpy 2.x; use a funasr release that includes this fix, or pin numpy<2. Unverified which release contains it.
- Third-party blog posts suggest `modelscope` upgrade and `trust_remote_code=True`; low-quality, unverified; ignore unless an error appears.

**Apple-native alternative:** an MLX conversion exists (fp16 safetensors, 324 MB, FunASR MODEL_LICENSE, Swift-oriented, no speed or accuracy claims): https://huggingface.co/mlx-community/emotion2vec-plus-large-mlx . Not Python-ready; not recommended for today.

## 2. Return format of `generate()`

From FunASR source (https://raw.githubusercontent.com/modelscope/FunASR/main/funasr/models/emotion2vec/model.py), as summarised by the fetch tool (it could not quote the whole function):
- Each result is `{"key": ..., "labels": ..., "scores": ...}`; with `extract_embedding=True` a `"feats"` entry is added. Returned as a list of dicts (one per input).
- `scores`: mean-pooled output goes through a linear projection, "unuse" labels are set to `-inf`, then `torch.softmax(x, dim=-1)`. So **scores are softmax probabilities** (sum to about 1) when the projection layer exists, which it does for the plus models (inferred; confirm with a real call).
- Evidence from an issue: top neutral score about 0.99, disgusted about 0.0018, happy about 0.00001, i.e. very peaked distributions. https://github.com/modelscope/FunASR/issues/2728
- `granularity="utterance"` averages over time; `"frame"` keeps 50 Hz features (model card).

**Label strings:** `tokens.txt` in the HF repo is exactly:
`生气/angry`, `厌恶/disgusted`, `恐惧/fearful`, `开心/happy`, `中立/neutral`, `其他/other`, `难过/sad`, `吃惊/surprised`, `<unk>`. Source: https://huggingface.co/emotion2vec/emotion2vec_plus_large/raw/main/tokens.txt . So labels are `"中文/english"` bilingual strings and the ninth is `<unk>`, not "unknown". B-04 must map by splitting on `/` and map `<unk>` to `unknown`. The "unknown" name is only in the card/README.
- Issue #2728: the same model via ModelScope `pipeline` returned only 5 labels (angry, happy, neutral, sad, plus unknown), while FunASR `AutoModel` returned 9. No explanation given. **Use `funasr.AutoModel`, not the modelscope pipeline.** The HF card's `pipeline` usage is the 5-label path.
- Whether `labels` and `scores` are same-length lists (9 entries) in AutoModel output: implied by the 9-label report in #2728; confirm in B-04.

**Numpy input:** FunASR's loader (https://raw.githubusercontent.com/modelscope/FunASR/main/funasr/utils/load_utils.py) converts numpy arrays with `torch.from_numpy`; the only dtype handling is int16 scaled to float32 in [-1, 1]. Other dtypes are neither cast nor checked, so pass **float32 mono in [-1, 1]** (or int16). Sample rate is assumed 16 kHz unless `fs`/`audio_fs` says otherwise (resamples if different). Raw `bytes` are not decoded. The model card itself only shows file paths and wav.scp (it does not document arrays), so array input is supported by code, not by the card. I did not run it; B-04 should confirm.

## 3. Latency and model variants

- Size: about 300M parameters (card). 
- **No published CPU or Apple Silicon latency for emotion2vec+ Large was found** (searched; only unrelated FunASR ASR benchmarks). Number: **unverified**. B-04's benchmark is the only source. Rough reasoning, not a measurement: a 300M-parameter encoder on a 2 s clip is likely well under the 1 s hop on an M4, but this is a guess.
- Variants: seed (201 h fine-tuning), base (4,788 h), large (42,526 h; the README also says "40k hours" elsewhere). Source: https://github.com/ddlBoJack/emotion2vec . Base is a smaller model (card parameter count for base/seed not retrieved: unverified), and speed gain unverified. Fallback ids would be `iic/emotion2vec_plus_base` / `iic/emotion2vec_plus_seed` (listed in README).
- The original `emotion2vec_base` is a representation model without the 9-class head (README table says fine-tuning "N/A"); do not use it for labels.

## 4. Accuracy and limits (honest claims)

Paper numbers are for the **original self-supervised emotion2vec with a linear probe**, not emotion2vec+ Large. Source: https://arxiv.org/html/2312.15185 (ACL Findings 2024).
- IEMOCAP (acted, 4-class): WA 71.79% (5-fold) / 72.94% (10-fold speaker-out); baselines data2vec 2.0 68.58, WavLM+ 67.98.
- Multilingual WA: SUBESCO 90.91, EmoDB 84.34, URDU 81.50, ShEMO 79.97, CaFE 74.52, AESDD 72.33, RESD 64.75, EMOVO 61.21, M3ED (Mandarin TV) 49.15 with UA only 26.98.
- Pre-training used 262 h of English emotion data; evaluations are linear probes on small datasets; protocols differ across rows; no limitations section.
- **emotion2vec+ numbers:** the GitHub README says "Details of model performance will be announced later" and gives no scores (https://github.com/ddlBoJack/emotion2vec). The fetch of the model card showed no benchmark. A search snippet mentioning about 69% on "resd" was unattributed: unverified, do not cite.
- Not found: any evaluation on short (1-2 s) clips, natural spontaneous speech, bias by gender/accent/age. Treat as **unknown**.
- Labels are pseudo-labels (large model fine-tuned on "filtered large-scale pseudo-labeled data"), so "ground truth" in training was itself model output (card).

**Can say:** "A pretrained speech-emotion model, reported in an ACL 2024 paper to beat comparable self-supervised models on acted benchmarks, estimates a probability over nine emotion categories from the sound of a 2-second window, locally."
**Cannot say:** that it reads true feelings; any accuracy figure for our setup or for emotion2vec+ Large; that it works on spontaneous speech or all languages (Mandarin natural speech was its worst result); that word-level emotion is native (it is utterance-level; windows are our heuristic).

## 5. License

- HF card: `license: other`, name `model-license` (https://huggingface.co/emotion2vec/emotion2vec_plus_large). GitHub README: MIT badge, no license text shown (https://github.com/ddlBoJack/emotion2vec).
- FunASR MODEL_LICENSE (https://raw.githubusercontent.com/modelscope/FunASR/main/MODEL_LICENSE): s2.1 "free to use, copy, modify, and share"; s2.2 must attribute source and author and retain model names; no mention of commercial use (no restriction found); s4.2 "unjustified denigration" of the software forfeits all licenses; s5 violation terminates the license.
- The MLX conversion card states the weights fall under FunASR MODEL_LICENSE (https://huggingface.co/mlx-community/emotion2vec-plus-large-mlx). Resolution (best evidence, not legal advice): the weights are governed by MODEL_LICENSE (the model card points there); the MIT badge appears to apply to the GitHub code repo. The ModelScope page was not checked: unverified.
- Practical: attribute "emotion2vec+ (iic/emotion2vec_plus_large), FunASR/ModelScope" in the demo credits; do not redistribute `model.pt`; do not disparage the software in the pitch.

## 6. Demo tips

No source ranks per-emotion reliability for the plus model: **unverified**. Grounded hints only:
- Training/benchmark data are mostly acted, so use clearly **acted, sustained, prosodically strong** lines in English at normal mic distance; expect neutral to dominate quiet/flat speech (issue #2728 shows ~0.99 neutral on a sample).
- Prefer angry, happy, sad, neutral (the four classes that even the 5-label pipeline output keeps) over disgusted, fearful, surprised, other (rarely shown in the evidence).
- Rehearse the exact lines on the real laptop and mic beforehand; show real outputs and say they are model estimates; do not cherry-pick silently: tell judges the lines were rehearsed.
- Short 2 s windows: each should contain a full phrase; a single clipped word may be unstable (unverified).

## Contradictions with TDD / preflight

1. Preflight lists about 5 GB disk; actual `model.pt` is 1.95 GB (HF listing).
2. TDD/preflight say the label "unknown"; the tokens file uses `<unk>` and bilingual `中文/english` strings. The adapter must parse these.
3. The card's `modelscope pipeline` example yields 5 labels (issue #2728); the TDD requires 9, so use `funasr.AutoModel` only.
4. Preflight lists "torch 2.15 / funasr 1.4.27" as latest; I could not verify them or any working combination. Also numpy 2.x support in funasr was only fixed 2026-09-09 (PR #3674).
5. Preflight says cache honours `EMOTION_MODEL_CACHE_DIR`; no evidence that funasr/modelscope read that variable. Pass the path explicitly or set the hub's own env var.
6. Licence: MIT badge vs MODEL_LICENSE; best reading is MODEL_LICENSE for weights.
7. TDD "normalized per-label scores": scores already appear to be softmax outputs; still sum-check.

## Open questions

- Which funasr/modelscope/torch/numpy versions install and run on macOS arm64 with Python 3.11? (B-04 trial; fall back to `uv pip install` with numpy<2 if errors.)
- Does `device="mps"` work and is it faster than CPU?
- Real p50/p95 latency of a 2 s window on the M4; peak RAM.
- Does a float32 numpy array give the same scores as the same audio from a WAV file?
- Does the ModelScope model page state its own license terms?
- Exact `labels`/`scores` list lengths and the `<unk>` position in `AutoModel` output.
- Any emotion2vec+ Large published benchmark (README says "later"); none found.
