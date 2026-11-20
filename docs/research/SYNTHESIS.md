# SYNTHESIS: verified research brief for builders (Judge J1, 2026-11-20)

Inputs: `docs/PLAN.md`, `docs/research/R1`–`R5`, `docs/TDD.md`, `docs/PIPELINE.md`, `docs/PROTOCOL.md`, `docs/live/model-preflight.md`, `.env.example`.
Citation keys: `[R1 API ref]` means "R1 report, its source tag API ref". `[J1: URL]` means Judge J1 fetched and checked that URL today (2026-11-20). Section 3 lists every J1 check with its verdict.
Rule for all lanes: if this file and a report disagree, this file wins only where section 3 says CORRECTED. Otherwise the report and its source win.

---

## 1. Per-lane fact sheets

### BA: backend (A-02 to A-05)

- **Scribe time unit.** Word `start`/`end` are **seconds, as doubles**. The API reference says "Start time in seconds." [R1 API ref] [J1: https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime]. Convert with `sample = round(seconds * 16000)` before alignment. The PIPELINE "Timed token" record already wants integer samples.
- **Spacing items.** `words[].type` is the enum `word` | `spacing` [J1: same URL]. Alignment must use only `type == "word"`. BB2 should drop spacing items in the adapter, so BA never receives them. BA should still guard against them.
- **Timestamp basis (connection- vs segment-relative) is NOT documented** [R1; J1: same URL, "doesn't say"]. Keep `timestamp_basis="unknown"` until BB2's smoke test settles it. PIPELINE rule 4 already handles this: an unknown basis produces an alignment warning and keeps the stable text.
- **Event order.** `committed_transcript` comes first. `committed_transcript_with_timestamps` comes after it, and only when `include_timestamps=true` [R1 Events]. Neither event has a documented commit key (`segment_index` appears only when `diarize=true`) [R1 Events]. So use FIFO plus normalized-text matching, as PIPELINE says.
- **Errors to classify** (all have the shape `{message_type, error}`) [R1 API ref] [J1]:
  - Permanent (no retry): `auth_error`, `quota_exceeded`, `unaccepted_terms`, `invalid_request`.
  - Transient (bounded backoff, new epoch): `rate_limited`, `queue_overflow`, `resource_exhausted`, `transcriber_error`, `error`, `session_time_limit_exceeded`.
  - `insufficient_audio_activity`: transient. The upstream may close during long silence. Reconnect lazily on the next speech.
  - `commit_throttled`, `chunk_size_exceeded`, `input_error`: these mean a bug on our side. Log them and treat them as transient once, then fatal.
  - This split is J1 judgment built on R1's list. The docs give no retry semantics.
- **No session limit or max chunk size is documented** [J1: API ref]. In manual mode the API auto-commits after about 36 s of audio [R1 Commit]. We use VAD mode, so this does not apply directly.
- **Billing counts silence** [R1 STT cap]. So close the upstream on Pause and Stop. PROTOCOL already opens a new epoch on Resume.
- **The mismatch flag (D3) needs no backend change** [PLAN §5; R5 §4]. Do not add a `text_sentiment` field.

### BB1: model (B-02, B-04, B-05, B-06)

- **Model ids:** `iic/emotion2vec_plus_large` (ModelScope). The Hugging Face mirror is `emotion2vec/emotion2vec_plus_large`, loaded with `hub="hf"` [R2 §1].
- **Install:** `pip install -U funasr modelscope` [R2 §1]. Use **funasr ≥ 1.4.27**, the latest release (2026-11-17) [J1: https://pypi.org/pypi/funasr/json]. Because: J1 checked the 1.4.27 wheel. It contains the int16-numpy scaling fix from 2026-11-13/14, which older releases lack (see section 3). Other latest versions: torch 2.15.0 (needs Python ≥3.11), modelscope 1.40.3 (needs ≥3.10), numpy 2.5.5 (**needs Python ≥3.12**) [J1: pypi.org JSON for each]. On Python 3.11, pip will choose an older numpy, which is fine. Do not force numpy 2.5.x on 3.11.
- **Weights:** `model.pt` is 1.95 GB [R2 §1]. The preflight's "~5 GB disk" is generous. The card's widget hints at about 4 GB RAM for inference [docs/live/model-preflight.md]. That is a hint, not a measurement.
- **Call:** `model.generate(wav, granularity="utterance", extract_embedding=False)` [R2 §2; TDD §2].
- **Input:** pass a **float32 mono numpy array in [-1, 1] at 16 kHz**. Because: FunASR's loader runs `torch.from_numpy`. Only `np.int16` is scaled by 1/32768, and only in recent releases. Other dtypes pass through unchanged. Raw Python `bytes` are not dispatched by `load_audio_text_image_video` [J1: https://raw.githubusercontent.com/modelscope/FunASR/main/funasr/utils/load_utils.py, lines 161–165]. Convert yourself with `np.frombuffer(pcm, "<i2").astype(np.float32) / 32768.0`, so the result does not depend on the funasr version.
- **Output:** a list of dicts `{"key", "labels", "scores"}` [R2 §2]. The source code [J1: funasr/models/emotion2vec/model.py lines 298–312]:
  ```python
  labels = tokenizer.token_list ...
  x = self.proj(x)
  for idx, lab in enumerate(labels):
      x[:,idx] = -np.inf if lab.startswith("unuse") else x[:,idx]
  x = torch.softmax(x, dim=-1)
  ...
  result_i = {"key": key[i], "labels": select_label, "scores": select_score}
  ```
  The plus-large `tokens.txt` contains no `unuse` tokens, so all 9 labels come back. The scores are a **softmax over all 9, so they sum to 1** → `score_kind="probability_like"`. Still run the 1e-3 sum check (PROTOCOL).
- **Label strings** are exact and in this order [J1: https://huggingface.co/emotion2vec/emotion2vec_plus_large/raw/main/tokens.txt]:
  `生气/angry, 厌恶/disgusted, 恐惧/fearful, 开心/happy, 中立/neutral, 其他/other, 难过/sad, 吃惊/surprised, <unk>`.
  Map with `lab.split("/")[-1]`, and turn `"<unk>"` into `"unknown"`. Reject any other label (PIPELINE: "Accept proven class aliases only").
- **Use `funasr.AutoModel`, not the ModelScope `pipeline`.** Because the pipeline returned only 5 labels in issue #2728 [R2 §2].
- **Device:** CPU by default. MPS is unverified, so try it only as an experiment [R2 §1].
- **Cache:** there is no evidence that funasr or modelscope read `EMOTION_MODEL_CACHE_DIR` [R2 contradiction 5]. J1 recommends (judgment, unverified) one of two approaches. Either set `MODELSCOPE_CACHE` (or `HF_HOME` for `hub="hf"`) from `EMOTION_MODEL_CACHE_DIR` before importing funasr, or download once and pass the local directory as `model=`. Record `model.model_path` after the first load [R2 §1].
- **Latency on the M4: no published number** [R2 §3]. B-06 is the only source. Report p50/p95 for a 2-second window.
- **Expect peaked distributions.** One issue shows neutral ≈0.99 [R2 §2, issue #2728]. Tune thresholds with real lines, not with intuition.
- **License:** FunASR MODEL_LICENSE governs the weights. It requires attribution, forbids redistributing `model.pt`, and terminates on "unjustified denigration" [R2 §5].

### BB2: Scribe adapter (B-03, `scripts/smoke_scribe.py`)

- **Endpoint:** `wss://api.elevenlabs.io/v1/speech-to-text/realtime`. Server-side auth uses the `xi-api-key` header [R1 §1].
- **Query:** `model_id=scribe_v3_live` (**the default is `scribe_v2_realtime`; the enum is exactly `scribe_v2_realtime | scribe_v3_live`**) [J1: API ref], `audio_format=pcm_16000`, `commit_strategy=vad`, `include_timestamps=true`, `vad_silence_threshold_secs=0.65`. The API range for that last value is 0.192–3.0, and no default is documented [R1 Commit].
- **Never combine `filter_background_audio=true` with `include_timestamps`.** The result is `invalid_request` and the connection closes [R1 Commit].
- **Send:** `{"message_type":"input_audio_chunk","audio_base_64":"<b64>","commit":false,"sample_rate":16000}`. Add `previous_text` on the first chunk only, and only if used [R1 API ref].
- **Receive:**
  - `session_started{session_id, config{...}}`.
  - `partial_transcript{text}`: each one replaces the last. Empty or repeated text is a keepalive.
  - `committed_transcript{text}`.
  - `committed_transcript_with_timestamps{text, language_code|null, words[{text,start,end,type,speaker_id,logprob,characters}]}`.
  - `warning{warning}`.
  - All from [R1 Events] [J1: API ref].
- **Units:** seconds (double). Drop `type=="spacing"`. Convert to integer samples at 16 kHz and record "verified unit: seconds (API ref), precision observed: X" as PIPELINE requires.
- **Use the raw `websockets` library, not the SDK.** Because the SDK hides raw frames that the timing smoke test needs, and its enums lack `turn_prediction` [R1 §5]. The SDK is `elevenlabs` 2.79.0 (2026-11-16) [R1; J1: PyPI].
- **The smoke test must settle the timestamp basis.** Proposed protocol (J1 judgment):
  1. Stream 3.0 s of digital silence, then say phrase A, pause about 1.5 s, then say phrase B.
  2. If phrase A's first `start` is about 3.0 s and B's starts are larger still → the clock is **connection-relative**.
  3. If B's starts reset to near 0 → the clock is **segment-relative**, and the segment origin is not supplied.
  4. Record raw scrubbed frames in `docs/live/scribe-preflight.md`. Also record whether the timed event follows each commit in order for back-to-back short commits [R1 open questions].
- **Concurrency is not a concern.** Even the Free tier allows 6 concurrent realtime sessions [R1 §1].

### BC1: frontend shell (C-01, C-02, C-03, C-05)

- **Capture constraints** (a hypothesis, A/B it in the room) [R5 §1]:
  ```ts
  navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1,
    echoCancellation: false, noiseSuppression: false, autoGainControl: false }})
  ```
  Log `track.getSettings()` to see what Chrome actually applied. Turn echo cancellation back on if the demo plays audio through the speakers [R5 §1].
- **AudioContext:** create it at the default rate (`new AudioContext()`), read `ctx.sampleRate`, and resample in the worklet. A 16 kHz context in Chrome probably works, but that is search-summary evidence only [R5 §1, tag S]. PROTOCOL requires validated 44.1/48 kHz conversion.
- **Worklet:** `process()` runs once per 128-frame quantum and must return `true` to stay alive. Post a transferable `ArrayBuffer` [R5, verified against https://developer.chrome.com/blog/audio-worklet].
  - Each frame is 640 output samples (40 ms) = 1,280 bytes [PROTOCOL]. At 48 kHz that takes 1,920 input samples, about 15 quanta.
  - Downmix to mono, low-pass and decimate (for 48 kHz the ratio is exactly 3), clamp to [-1, 1], convert to Int16 little-endian, and keep the resampler phase across buffers [R5 §1; PROTOCOL].
- **`localhost` counts as a secure context**, so mic capture works there [R5 §1].
- **The only new dependency is `@huggingface/transformers`.** The latest npm version is **4.3.2** [J1: https://registry.npmjs.org/@huggingface/transformers/latest]. Pin it exactly. Because: an unpinned major version could change the dtype or file names (see BC2).
- **Static replay build (D10):** the replay view must not import the mic or WebSocket code paths [PROTOCOL Replay HTTP].

### BC2: visuals and mismatch (C-04, radar, settings, D3 worker)

- **Clouds:** generate your own polar points (N≈28) around each line-run rect. Morph by lerping radii, drive everything from one shared rAF loop, and write `path.setAttribute('d', …)` imperatively. No flubber, no `blobs` (unverified), no SVG filters [R5 §2]. Per-emotion style parameters are in R5 §2.
- **Measurement:** build a `Range` from the first word span to the last, call `range.getClientRects()`, and group the rects into line runs. Subtract the container's bounding rect. Re-measure on ResizeObserver, `document.fonts.ready`, history moves and new commits, with one rAF debounce [R5 §2; TDD §7.3].
- **Radar:** hand-rolled SVG with no dependency. Axis angle `a_i = -π/2 + 2πi/k`. Use a fixed 0–1 scale; never auto-scale. Add `role="img"` and an `aria-label` [R5 §3]. PLAN D4 fixes **6 axes** (the visible categories). All 9 scores stay in the inspector.
- **Palette:** the wire `color` values are fixed in PROTOCOL. The CVD setting is a **client-side remap keyed by `primary`**. The Okabe-Ito mapping:

  | Emotion | Name | Hex |
  |---|---|---|
  | angry | vermilion | `#D55E00` |
  | sad | sky | `#56B4E9` |
  | happy | yellow | `#F0E442` |
  | fearful | reddish purple | `#CC79A7` |
  | surprised | orange | `#E69F00` |
  | disgusted | bluish green | `#009E73` |

  Sources: [R5 §5; https://jfly.uni-koeln.de/color/]. The hex values come from a search summary [R5 tag S]. Run the Chrome DevTools vision-deficiency emulator before the demo.
- **WCAG 1.4.1:** color must not be the only cue. Shape plus an optional label satisfies it [R5 §5, verified against w3.org].
- **Reduced motion:** use `matchMedia('(prefers-reduced-motion: reduce)')` from JS and drop the breathing and noise terms. Semantics stay [R5 §5]. Never flash faster than 3 Hz [TDD].
- **Mismatch model:** `Xenova/distilbert-base-uncased-finetuned-sst-2-english` [R5 §4; J1 verified id].
  ```js
  import { pipeline } from "@huggingface/transformers";
  const classifier = await pipeline('sentiment-analysis', 'Xenova/distilbert-base-uncased-finetuned-sst-2-english');
  // [{ label: 'POSITIVE', score: 0.999788761138916 }]
  ```
  Source: [J1: https://huggingface.co/Xenova/distilbert-base-uncased-finetuned-sst-2-english].
  - Output is binary, POSITIVE or NEGATIVE only, with no neutral class [R5 §4].
  - **dtype:** the WASM default is `q8`, and q8 loads **`onnx/model_quantized.onnx` (67.6 MB)**, not `model_int8.onnx` [J1 CORRECTED: transformers.js 4.3.2 dist `DEFAULT_DTYPE_SUFFIX_MAPPING` `q8:"_quantized"`, `DEFAULT_DEVICE_DTYPE_MAPPING wasm:q8`; file sizes from https://huggingface.co/Xenova/distilbert-base-uncased-finetuned-sst-2-english/tree/main/onnx].
  - For offline or demo Wi-Fi: `env.allowRemoteModels` and `env.localModelPath` exist in 4.3.2 [J1: dist bundle]. Pre-bundle the files under `public/models/`.
- **Mismatch rule** [PLAN D3; R5 §4]:
  1. Require text `score ≥ 0.90`.
  2. Require a non-neutral, visible, time-weighted dominant voice category.
  3. Flag when text is POSITIVE and voice is in {angry, sad, fearful, disgusted}.
  4. Flag when text is NEGATIVE and voice is happy.
  5. Surprised and neutral never flag.
  6. The sentence must have at least 3 words.
  7. Show the label "Words and voice differ", never "sarcasm".
- **Load the mismatch model in a Web Worker.** Show "warming up" while it loads, and fail silently so the feature just stays off [R5 §4].

### BD: pitch

See section 4 for the safe-to-say list and the do-not-say list. Also:
- Name Google Expressive Captions first, using its **current** availability (section 3, check 7), then differentiate [R4 §0].
- Ethics lines are in R3 §6. Interview questions are in R3 §7.
- Credit "emotion2vec+ (iic/emotion2vec_plus_large), FunASR/ModelScope" on the credits slide [R2 §5].

---

## 2. TDD / plan amendments (research vs docs)

| # | Doc and location | Says | Research says | Resolution |
|---|---|---|---|---|
| A1 | TDD §1 line 18 "Explicitly excluded: … DistilRoBERTa … cross-model fusion" and §6.3 "Do not use language sentiment … or any second ML model for emotion scoring" | Text sentiment is excluded | PLAN D3 adds DistilBERT SST-2 text sentiment [R5 §4] | **Amend the TDD.** D3 is allowed only as a separate "Words and voice differ" badge. It must **never** change `scores`, `support`, cloud color or shape, or the classifier. Say this in the pitch so it is not read as "fusion". |
| A2 | TDD §2.2, §6.3, preflight, `model-window.schema` | Label `unknown`; "aliases" | Model emits bilingual `中文/english` strings and `<unk>` [R2; J1 CONFIRMED] | Adapter maps `split("/")[-1]` and `<unk>`→`unknown`. Wire keeps the 9 English keys unchanged. |
| A3 | TDD §2.3 "do not assume probabilities"; §6.3 "normalize" | Unknown output kind | Softmax over 9 [R2; J1 CONFIRMED in 1.4.27 wheel] | `score_kind="probability_like"`. Keep the sum check, and fail if it is broken. |
| A4 | TDD §6.2 error list | 4 error types | 14 `message_type` errors [R1; J1 CONFIRMED] | Use the BA classification in section 1. Add `SCRIBE_*` warning codes only if needed. No schema change: PROTOCOL allows other recognized codes. |
| A5 | TDD §2.1, §6.1 | Silent on units and spacing | Seconds (double); `type` is `word` or `spacing` [J1 CONFIRMED] | PLAN D7 is correct. Add both to TDD §6.2. |
| A6 | preflight "~5 GB disk"; `EMOTION_MODEL_CACHE_DIR` honoured | — | 1.95 GB; no evidence the env var is read [R2] | Keep 5 GB as headroom. BB1 maps the variable explicitly (section 1). |
| A7 | preflight version candidates | torch 2.15 / funasr 1.4.27 "latest" | Confirmed as latest [J1: PyPI]. numpy 2.5.5 needs Py ≥3.12. funasr <1.4.27 (pre-2026-11-14 main) mis-scales int16 arrays | Pin funasr ≥1.4.27 or always pass float32. Python 3.11 is fine. |
| A8 | PLAN D1 "there is a 'Best Project Built with ElevenLabs' prize"; TDD footnote "131k credits" | Stated as fact | Neither appears in the Hacker Guide [R1 §4, §2] | **UNVERIFIED.** Confirm both at the event before saying them on stage. API usage is billed in USD at $0.22/h [J1 CONFIRMED]. |
| A9 | PROTOCOL annotation `color` fixed; PLAN D6 CVD palette | — | Okabe-Ito [R5] | CVD palette is a frontend remap by `primary`. No wire change. |
| A10 | TDD §7.1 / post-core "Radar … all relevant categories" vs R5 9-axis suggestion | — | PLAN D4: 6 axes | Follow PLAN D4 (6 axes). The 9 scores stay in the inspector. |
| A11 | R3 §1 (Hassan and Burnett "hearing participants") | — | Abstract: **28 DHH viewers**, no significant difference in understanding or preference [J1: https://par.nsf.gov/biblio/10442631] | CORRECTED. R4 had it right. Use it as an honest limit (section 4). |
| A12 | R4 Google row "US only, English" | — | May 2025 update: English in **US, UK, Canada, Australia**, Android 15+, plus a "duration" feature (stretched words like "amaaazing") [J1: https://9to5google.com/2025/05/15/google-global-accessibility-awareness-day-2025/] | CORRECTED. The pitch must not call Google "US-only". |
| A13 | R5 §4 "q8 ~67.4 MB (`model_int8.onnx`)" | — | q8 → `model_quantized.onnx` 67.6 MB [J1] | CORRECTED (minor). It matters for pre-bundling the right file. |
| A14 | PLAN §3 D3 "R4 found no product doing this" | — | R4 says "not found, not proven absent"; Hume plus text sentiment could replicate it [R4 §2] | Wording: "we did not find a caption product that…". |
| A15 | TDD §6.1 step 3 relay | — | Billing counts silence [R1 STT cap] | Close upstream on Pause (already planned). Do not keep Scribe open when idle. |

No contradictions found with PIPELINE windowing or alignment math, or with PROTOCOL framing (40 ms, s16le, 16 kHz). PROTOCOL needs no schema change.

---

## 3. Cross-check (J1 verification, 2026-11-20)

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | Scribe word `start`/`end` in seconds; `type` ∈ {word, spacing} | **CONFIRMED** | API ref: "Start time in seconds."; enum `word`/`spacing`. https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime |
| 2 | `scribe_v3_live` is a valid id; default is `scribe_v2_realtime` | **CONFIRMED** | Same page: enum `scribe_v2_realtime`, `scribe_v3_live`; default `scribe_v2_realtime`. |
| 3 | Timestamp basis documented? | **UNVERIFIED** (undocumented) | Same page does not say. The smoke test decides. |
| 4 | Scribe error list (14 types); no documented session or chunk limit | **CONFIRMED** | Same page. |
| 5 | Scribe v3 Live $0.22/h; API billed in USD, not credits | **CONFIRMED** | https://elevenlabs.io/pricing/api |
| 6a | emotion2vec+ label strings `中文/english` + `<unk>` | **CONFIRMED** | https://huggingface.co/emotion2vec/emotion2vec_plus_large/raw/main/tokens.txt (fetched raw) |
| 6b | Scores are softmax probabilities | **CONFIRMED** | FunASR `funasr/models/emotion2vec/model.py` L298–312 on main and in the funasr 1.4.27 wheel |
| 6c | numpy input supported; only int16 scaled; bytes not decoded | **CONFIRMED with correction** | `load_utils.py` L161–165. The int16 → /32768 scaling was **added 2026-11-13/14** (commit "fix(audio): scale int16 numpy waveforms…"). Earlier funasr passed int16 **unscaled** ("the signal was overdriven"). 1.4.27 includes it. Raw `bytes` input has no branch in the loader. A separate `load_bytes()` helper exists. → Pass float32. |
| 7 | Google Expressive Captions: Dec 2024, on-device, US English, Android 14+, caps + sound labels | **CORRECTED** (availability) | Launch facts confirmed: https://blog.google/products-and-platforms/platforms/android/google-android-expressive-captions/ ("Dec 05, 2024", "in real time and on device", "available in the U.S. in English", Android 14+, "select devices"). May 2025: "rolling out in English in the US, UK, Canada, and Australia for Android 15 and above" plus a duration feature: https://9to5google.com/2025/05/15/google-global-accessibility-awareness-day-2025/. No 2026 expansion found (unverified either way). |
| 8 | transformers.js model id and API | **CONFIRMED**; file detail **CORRECTED** | Model card usage quoted in section 1 BC2. q8 → `model_quantized.onnx` (67.6 MB). npm latest 4.3.2. |
| 9 | WHO "nearly 2.5 billion … by 2050" | **CONFIRMED** | https://www.who.int/news-room/fact-sheets/detail/deafness-and-hearing-loss (dated 3 Mar 2026). The same page gives "430 million … require rehabilitation" today and defines disabling as >35 dB in the better ear. The 2050 disabling figure is "more than 700 million"; the fetcher's wording was "will require hearing rehabilitation". Use that number with that wording. The "1.5 billion today" figure was **not** on this fact sheet: **UNVERIFIED** (R3 snippet only). |
| 10 | EU AI Act Art. 5(1)(f) text and 2 Feb 2025 application | **CONFIRMED** | https://artificialintelligenceact.eu/article/5/ ("the use of AI systems to infer emotions of a natural person in the areas of workplace and education institutions" … "except … medical or safety reasons"). Applies from 2 Feb 2025 (Art. 113(a)). The 2 Dec 2026 amendments do not touch point (f). The Official Journal was not read. |
| 11 | CHI 2023 (Pataca et al.): which style beat conventional captions | **CONFIRMED (R3 wording)** | Search abstract summary: "the emotion-based model outperformed traditional captions in depicting emotions and emphasis, with only a moderate loss in legibility"; 8 interviewed, 16 in the study. Full text not read. R4's "prosody alone did not beat conventional" comes from a secondary review: say it only as "reportedly". |
| 12 | Hassan and Burnett used hearing participants (R3) | **CORRECTED** | 28 DHH viewers; no significant difference. https://par.nsf.gov/biblio/10442631 |

---

## 4. Pitch-safe claims

### May say (each with its citation)

1. "By 2050, nearly 2.5 billion people are projected to have some degree of hearing loss." [WHO fact sheet; J1 check 9]
2. "Today about 430 million people need rehabilitation for disabling hearing loss." [same WHO page]
3. "WHO lists social isolation, loneliness and stigma among the effects of unaddressed hearing loss." [same WHO page; R3 §5]
4. "Real-time captions often omit emotional and non-verbal cues." Attribute it: "a 2025 Virginia Tech study". [R3 §1; arXiv 2603.15977]
5. "In a CHI 2023 study with 16 deaf and hard-of-hearing participants, an emotion-based caption style beat conventional captions at showing emotion and emphasis, at a moderate cost to legibility. So we keep clouds subtle and let you turn them off." [R3 §1; J1 check 11]
6. Honest limit: "Another study with 28 DHH viewers found no significant difference between three emotive caption styles. So this is early, not proven." [J1 check 12]
7. "Google already ships Expressive Captions on Android: capitals for intensity, sound labels, and stretched words. It is English-only, on Android 14+/15+ phones. Ours runs in any browser, anchors a shaped cloud to the exact words, and flags when words and voice differ." [J1 check 7; R4]
8. "We did not find a caption product that flags when the words and the voice disagree." [R4 §2] Say "did not find", never "first".
9. "Transcription is ElevenLabs Scribe v3 Live, streaming with word-level timestamps, at $0.22 per hour of audio." [J1 checks 1, 5]
10. "The emotion model is emotion2vec+ Large, about 300 million parameters. It runs locally on this laptop, so the audio for emotion never leaves the machine. Transcription audio does go to ElevenLabs." [R2 §3; TDD §5]
11. "It estimates a probability over nine vocal-emotion categories from 2-second windows. We align those windows to word timestamps, so a cloud is a phrase-level cue, not a per-word verdict." [J1 check 6b; R2 §4; R4 §2]
12. "The base emotion2vec paper (ACL Findings 2024) reports beating comparable self-supervised models on acted benchmarks." [R2 §4] Never give a number for our setup.
13. "The EU AI Act bans inferring emotions in workplaces and schools, except for medical or safety reasons. We have not assessed EU deployment. A school or workplace rollout would need legal review." [J1 check 10; R3 §6]
14. "The words-versus-voice badge says 'words and voice differ'. Research ties sarcasm to that gap, but a gap alone does not prove sarcasm." [R5 §4]
15. "Shape plus color plus an optional label, a color-blind-safe palette, and reduced motion." [R5 §5; WCAG 1.4.1]
16. Any attendee quote collected today, with their permission. [R3 §7]

### Do not say

- "Detects emotions / feelings / what someone really feels", "lie or sarcasm detector". Say "detected vocal cues" instead [R3 §6; TDD §1].
- Any accuracy percentage for our system or for emotion2vec+ Large. None is published [R2 §4].
- "Proven to help deaf users". The studies are small and mixed [R3 §1; J1 check 12].
- "Google's captions are US-only" or "Google has no word-level analysis" [J1 check 7; R4 Q3].
- "First ever" or "nobody does this" [R4 §0].
- "1.5 billion people have hearing loss today" (UNVERIFIED on the WHO fact sheet) or "2.5 billion deaf people". Say "people with hearing loss" [R3 §1].
- "Fully on-device" or "private by default". Scribe is a cloud service [TDD §5].
- "Works in all languages" or "works on spontaneous speech" [R2 §4].
- "Built for autistic people" or "fixes what autistic people miss". Use the optional-channel framing [R3 §2].
- "Best Project Built with ElevenLabs prize" or "131k credits", until confirmed at the event [R1 §4; A8].
- "Laughter / audio-event detection in realtime" (UNVERIFIED for realtime) [R1 §3].
- "The ADA requires live captions" [R4 §3].
- Any disparaging line about FunASR or emotion2vec. The license terminates on "unjustified denigration" [R2 §5].
- Hume's price as fact ("UNVERIFIED", sales-quoted) [R4 §3].

---

## 5. Open questions and risks (ranked by demo impact)

| Rank | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **Scribe timestamp basis unknown** (connection vs segment) [J1 check 3] | If we guess wrong, every cloud lands on the wrong words, or nothing aligns | BB2 smoke protocol (silence lead-in, two phrases) right after the key is redeemed. Until then keep `unknown`, so the app degrades to text plus a warning, not wrong clouds. BA unit-tests both bases with the fake upstream. |
| 2 | **Model shows only neutral** on live speech (peaked ≈0.99 neutral seen) [R2 §2] | A demo with no clouds | Rehearse acted, sustained lines (angry, happy, sad first) on the real mic [R2 §6]. Tune thresholds from B-06 data, not by guessing. Labelled replay is the backup (D9). |
| 3 | **Model install / version break on macOS arm64**; no known-good pin [R2 §1] | No live model | Use funasr ≥1.4.27 and Python 3.11. Pre-download the 1.95 GB tonight, test offline, and keep `hub="hf"` as a fallback [R2 §1]. Freeze the lock after the first success. |
| 4 | **Inference latency on the M4 unknown** [R2 §3] | Clouds later than ~3 s, or dropped windows | B-06 benchmark p50/p95. If p95 is over 1 s (the hop), fall back to `iic/emotion2vec_plus_base` (speed gain unverified) or accept drops (bounded worker). |
| 5 | **int16 scaling / dtype** [J1 check 6c] | Overdriven input gives garbage scores | Always pass float32/32768 and add a unit test: the same clip from WAV and from an array should give the same scores [R2 open question]. |
| 6 | **Chrome resampling / AGC / NS** [R5 §1] | Wrong rate gives garbled STT; processing may flatten emotion cues | Default-rate context plus the worklet resampler, a PROTOCOL 44.1/48 kHz test, and log `getSettings()`. 10-minute A/B of processing on vs off. Headphones if echo cancellation is off. |
| 7 | **ElevenLabs key/credits arrive late**; prize unverified [R1 §4] | No live Scribe until the event | Fake upstream for everything tonight. Redeem via Discord first thing. Silence is billed, so stop streaming when idle. |
| 8 | **Demo Wi-Fi**: 67.6 MB DistilBERT download, Scribe needs network | Mismatch badge missing; live STT fails | Pre-bundle the model in `public/models/` with `env.allowRemoteModels=false`. Phone hotspot as a backup. The mismatch badge fails silently. |
| 9 | **Mismatch false positives** (SST-2 is movie-review text) [R5 §4] | A wrong badge on stage | Use the ≥0.97 gate (raised from 0.90 after two false badges, docs/REVIEW.md), min 2 words in code, no neutral or surprised. Script two lines known to trigger it ("That's great." said angrily; "I'm fine." said sadly). |
| 10 | **Judge knows Google Expressive Captions (now multi-country)** [J1 check 7] | Weakens the differentiation score | Name it first and use pitch line 7. |
| 11 | **`insufficient_audio_activity` closes the upstream during pauses in speech** [R1] | Reconnect banner mid-demo | Treat it as transient, reconnect quietly with a new epoch, and keep the transcript. |
| 12 | **Ethics question (EU AI Act, "pseudoscience")** [R3 §6; R4 Q1] | Lost credibility | Pitch lines 13–14 and the "vocal cues" wording. Barrett 2019 concerns faces; cite it only for the general principle. |

Still open after J1 (needs a live run or event-day check):
- the timestamp basis;
- whether the timed event stays in order under back-to-back VAD commits;
- the real M4 latency and RAM;
- MPS vs CPU;
- Creator credit count and prize criteria;
- ElevenLabs data retention;
- whether YouTube/Google expanded expressive captions in 2026 (a search result titled "YouTube expands Expressive Captions to all devices" was seen but not read: UNVERIFIED).
