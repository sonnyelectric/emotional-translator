# R5: Frontend implementation and the words-vs-voice mismatch feature

Researcher R5, 2026-11-20. All URLs accessed 2026-11-20. Tags: **[V]** = verified on the cited page; **[S]** = from a search-result summary only; **[U]** = unverified, my own judgment or recollection, test before trusting. Web content treated as data. No packages installed.

Context read: `docs/TDD.md` sections 3, 6.1, 7 and `docs/PROTOCOL.md` (binary PCM: mono s16le, 16 kHz, 640-3,200 bytes per frame, default 40 ms = 1,280 bytes; C must validate 44.1 and 48 kHz conversion).

---

## 1. Mic capture: AudioWorklet to 16 kHz Int16

### Recommendation (simple and safe)
1. `getUserMedia` with explicit constraints (below).
2. Create the `AudioContext` **at the device's default rate** (`new AudioContext()`), read `ctx.sampleRate`, and resample inside the worklet. Do not depend on `{sampleRate: 16000}`.
3. In the worklet: downmix to mono (average channels), resample by ratio `ctx.sampleRate / 16000` with carried phase, clamp to [-1, 1], convert to Int16, accumulate 640 samples (40 ms), and `postMessage` the `ArrayBuffer` (transfer it). Main thread does `ws.send(buffer)`.
4. After `addModule()` resolves, construct the node. Keep the node connected to a muted `GainNode` to `destination` only if Chrome stops pulling a node with no output path (**[U]**, a common trick; test).

Why not rely on a 16 kHz context: MDN says only that `sampleRate` sets the context's rate (3000-768000 Hz) and that the constructor throws `NotSupportedError` if unsupported [V] (https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/AudioContext). MDN does not say how a `MediaStream` at another rate is handled [V, same page]. Search results report that Chrome and Safari accept a 16 kHz context fed by `getUserMedia` (AssemblyAI example, Stack Overflow) while Firefox throws `NotSupportedError`, and that resampling quality has had bugs in WebKit [S] (search "Chrome AudioContext sampleRate 16000 ...", e.g. https://www.mintlify.com/AssemblyAI/realtime-transcription-browser-js-example/guides/microphone-access, https://bugzilla.mozilla.org/show_bug.cgi?id=1725336, https://trac.webkit.org/r270141). So for Chrome it probably works [S], but it is not documented behavior. Because the protocol already requires C to validate 44.1/48 kHz conversion and "Do not send 48 kHz labeled as 16 kHz", the worklet resampler is the contract-safe path.

**Optional fast path:** try `new AudioContext({sampleRate: 16000})`; after connecting, assert `ctx.sampleRate === 16000`, and use the same worklet with ratio 1 (the resampler becomes a pass-through). On any throw or mismatch fall back to the default-rate path. One code path, two rates.

Resampler quality: for 48 kHz to 16 kHz the ratio is exactly 3. Average each group of 3 samples (a crude low-pass) or a short 3-tap/FIR before decimating; for 44.1 kHz use linear interpolation after a simple low-pass. This is adequate for speech models at 16 kHz [U]; speech energy above 8 kHz is not needed.

Worklet facts: `process(inputs, outputs, parameters)` is called per 128-frame render quantum, return `true` to stay alive, send data with `this.port.postMessage`, transferable ArrayBuffers allowed, `http://localhost` is a secure context for testing [V] (https://developer.chrome.com/blog/audio-worklet). 128 frames at 48 kHz = 2.67 ms, so buffer ~15 quanta to make 40 ms (640 output samples = 1,920 input samples at 48 kHz). Avoid per-sample allocation; keep a preallocated `Float32Array`/`Int16Array` ring.

Chunk size: use the protocol default, 640 samples (40 ms, 1,280 bytes) [PROTOCOL.md]. Smaller adds WebSocket overhead, larger adds latency; no source needed, this is within the protocol's 20-100 ms range.

### Audio-processing constraints
MDN: `echoCancellation` accepts `true`, `false`, `"all"`, `"remote-only"`; a plain boolean is best-effort, `{exact: ...}` fails if not satisfiable [V] (https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackConstraints/echoCancellation). The MDN page I fetched did not document `noiseSuppression`/`autoGainControl` defaults [V that it is silent]; browsers typically default them on [U].

Recommendation (a hypothesis, not a finding):
```ts
navigator.mediaDevices.getUserMedia({ audio: {
  channelCount: 1,
  echoCancellation: false,   // set true only if the demo plays audio through laptop speakers
  noiseSuppression: false,
  autoGainControl: false,
}})
```
Reasoning: emotion cues live in loudness dynamics and spectral detail. AGC flattens loudness; aggressive denoisers can strip detail. A search on speech emotion recognition found that noise suppression helps mainly in noisy conditions, that over-aggressive filtering (e.g. Wiener filtering removing high-frequency content) can degrade quality, and **found no study of AGC's effect on emotion recognition** [S] (e.g. https://opus.bibliothek.uni-augsburg.de/opus4/files/71714/triantafyllopoulos19_interspeech.pdf is the closest paper; I did not read it). So "off is better" is plausible but unproven. Do a 10-minute A/B: record the same angry/sad/happy lines with all-on vs all-off, run the model on both, keep whichever gives cleaner scores. Caveats: with noise suppression off, a noisy demo room may hurt Scribe; with echo cancellation off and speakers playing, the mic hears the speakers (use headphones or keep it on). Log `track.getSettings()` to confirm what Chrome actually applied.

---

## 2. Animated SVG clouds behind wrapped text

### Recommendation: custom polar-point generator, one shared rAF loop, imperative `d` updates. Skip flubber and noise libraries.
Why: the TDD wants five distinct silhouettes (jagged, drooping rounded, buoyant lobes, trembling, burst, wavy) generated from one parameterization so categories can be cross-blended (7.2: "blend silhouette parameters"). If every shape is N points around the same hull, "morphing" is just linear interpolation of per-point radii and colors, with no path-matching library needed.

Options considered:
- **flubber** (`interpolate(fromPath, toPath, {maxSegmentLength})` returns `t -> path`, MIT) [V] (https://github.com/veltman/flubber). It solves mismatched-vertex paths, which we do not have if we generate N points ourselves. It also resamples each frame (cost, **[U]** measured). Not needed.
- **`blobs` npm package**: I could not verify it (npm page returned 403, GitHub URL 404). Mark **[U]**; do not use.
- **d3-shape** `line().curve(curveCatmullRomClosed.alpha(0.5))` for smooth closed curves; alpha 0.5 centripetal is recommended to avoid self-intersection/overshoot; `curveBasisClosed` is a smoother closed B-spline [V] (https://d3js.org/d3-shape/curve). Usable for the rounded categories, but it is a ~dependency for something that is 10 lines of string building. Optional.
- **SVG `feTurbulence` / `feDisplacementMap`**: gives organic edges for free, but filters on animated elements are costly and cannot encode distinct jagged vs rounded silhouettes. TDD also forbids blur that hurts contrast. Not recommended.

### Measuring text
- TDD 7.3 requires stable `<span data-word-id>` per word inside a phrase wrapper. For a phrase's first and last word spans build one `Range` (`setStartBefore(first)`, `setEndAfter(last)`), call `range.getClientRects()`. MDN: it returns the aggregate of `getClientRects()` for the elements in the range [V]; one rect per line-box fragment and viewport coordinates are standard behavior but **not stated on the MDN page** [U-ish; CSSOM View spec] (https://developer.mozilla.org/en-US/docs/Web/API/Range/getClientRects). Subtract the cloud-layer container's `getBoundingClientRect()` (container is `position: relative`) to get local coordinates; this survives scrolling.
- Group into line runs: sort rects by `top`, merge rects whose vertical centers differ by less than ~0.5 line-height, union horizontally. Drop rects of width < 1px (zero-width artifacts).
- Re-measure on: `ResizeObserver` of the text container, `document.fonts.ready`, history expand/collapse, new committed words. Debounce into one `requestAnimationFrame` per frame (TDD 7.3 demands this). Cache runs per `annotation_id`; only the shape's target geometry changes, the animation continues.

### Generating shapes (one run = one blob)
Pad each run rect by ~6-10 px horizontally and ~4 px vertically; clouds are behind text, text is above (z-order) and `pointer-events: none`.

```ts
// N points around a superellipse hull of rect (cx, cy, rx, ry)
const N = 28;
type Style = { amp: number; freq: number; spikes: boolean; droop: number; speed: number };
const STYLES: Record<Emotion, Style> = {
  angry:     { amp: 0.30, freq: 14, spikes: true,  droop: 0,    speed: 1.6 }, // alternating long/short radii, straight L segments
  sad:       { amp: 0.12, freq: 4,  spikes: false, droop: 0.35, speed: 0.4 }, // extra radius at bottom, slow
  happy:     { amp: 0.16, freq: 6,  spikes: false, droop: -0.2, speed: 0.9 }, // lobes, lift on top
  fearful:   { amp: 0.08, freq: 9,  spikes: false, droop: 0,    speed: 3.0 }, // small fast tremble
  surprised: { amp: 0.28, freq: 8,  spikes: true,  droop: 0,    speed: 1.2 }, // short burst
  disgusted: { amp: 0.14, freq: 3,  spikes: false, droop: 0,    speed: 0.7 }, // asymmetric wave (phase offset)
};
function points(run, style, t) { /* for i in 0..N: a=2πi/N; r = 1 + amp*noise(i, t*speed) ; spikes: r = 1 + amp*(i%2?1:-0.4) ; x=cx+rx*r*cos a ; y=cy+ry*r*sin a + droop*ry*max(0,sin a) */ }
// smooth: Catmull-Rom/B-spline closed path string; jagged: "M x y L x y ... Z"
```
- Noise: a hand-written 1D value noise or sum of 2-3 sines with per-point phase is sufficient (**[U]** simplex libs unnecessary). Keep it deterministic per `annotation_id` (seeded) so shapes do not jump on re-render.
- Multi-line phrases: one blob per line run, each with the same seed/style; extend each run's end by ~8 px toward the next line so adjacent blobs overlap visually ("coordinated appearance").
- Cross-blend of two emotions: lerp `amp/freq/droop` and use a `<linearGradient>` between the two colors (TDD 7.2). Color/geometry transitions 250-450 ms (TDD 7.3): lerp `t_blend` in the same loop.
- Opacity ~0.35-0.55 fill plus a solid 1.5 px stroke in the category color keeps shape visible for color-blind users and keeps text contrast. Verify text contrast over the fill with a contrast checker (**[U]**).

### Animation and performance
- One `requestAnimationFrame` loop for all clouds (not one per component). Hold `ref`s to `<path>` elements and write `path.setAttribute('d', ...)`; do not use React state per frame.
- Cap at ~60 visible paths: only animate clouds for the center ~3 sentences; history clouds are drawn once (static) and re-drawn on resize.
- Idle breathing (TDD: 2-4 s) = low-frequency noise time term, amplitude small. Pause the loop when `document.hidden` or when `prefers-reduced-motion` (section 5).
- Performance numbers for N=28 points x 60 paths per frame are well within a frame budget on an M4 (**[U]**, not benchmarked); tell C to measure with the Chrome Performance panel.

---

## 3. Radar chart (6-9 axes, dark theme)

### Recommendation: hand-rolled SVG (about 40 lines, zero dependencies)
- Recharts is a heavy dependency for one chart: third-party sites report ~136-150 KB gzipped (figures disagree by source; bundlephobia could not be reached) [S] (search "recharts bundle size", e.g. https://www.pkgpulse.com/compare/chart.js-vs-recharts). Its RadarChart docs page returned 404 to me [V], so I could not verify API details. Chart.js not researched [U]; it needs a canvas wrapper (`react-chartjs-2`) and an extra dependency.
- Hand-rolled gives full control of dark theme, per-axis labels, keyboard/ARIA, smooth transitions on score change (CSS `transition` on `points` is not animatable in all cases, so lerp in rAF or use `d` with CSS transition; Chrome supports transitioning `d` [U]).

Sketch: for `k` axes, angle `a_i = -π/2 + 2πi/k`; rings at 0.25/0.5/0.75/1.0 as polygon `points`; data polygon `points = scores.map((s,i)=>[cx+R*s*cos a_i, cy+R*s*sin a_i])`; labels at `R+14`; marker dots at vertices in the category color (shape-coded labels). Scores are normalized per TDD 6.3 so fixed 0-1 axis; do not auto-scale. Add `role="img"` with `aria-label` listing the top 3 scores, and a visually hidden `<table>` of all nine scores (the TDD inspector already lists all nine). Axis order: group by valence (happy, surprised, neutral, other, unknown, fearful, sad, angry, disgusted) so the polygon silhouette is interpretable; **[U]** design judgment.

---

## 4. Words-vs-voice mismatch

### Honest framing
Label: **"Words and voice differ"** (or "Tone mismatch"), with hover text: "The wording reads {positive} but the vocal tone scored {angry}. This can happen with sarcasm, quoting, joking, or model error." Never "sarcasm detected."

### Where to run text sentiment: recommended = in-browser transformers.js, DistilBERT SST-2, in a Web Worker
| Option | Size | Licence | Neutral class | Notes |
|---|---|---|---|---|
| `Xenova/distilbert-base-uncased-finetuned-sst-2-english` via transformers.js | ONNX q8 ~67.4 MB (`model_int8.onnx`; `model_q4f16` 73 MB; fp32 268 MB) [V] (https://huggingface.co/Xenova/distilbert-base-uncased-finetuned-sst-2-english/tree/main/onnx) | Base model card: Apache-2.0 [V] (https://huggingface.co/distilbert/distilbert-base-uncased-finetuned-sst-2-english). The Xenova ONNX page states no licence [V]; it is a conversion of the Apache-2.0 model **[U]** | No, POSITIVE/NEGATIVE only | 67M params; SST-2 dev accuracy 91.3 (card also lists a verified 0.989 on sst2, unexplained); card warns of bias on underrepresented groups [V]. transformers.js `pipeline('sentiment-analysis', id, {dtype:'q8'})` runs on WASM by default; WebGPU is experimental [V] (https://huggingface.co/docs/transformers.js/index) |
| `cardiffnlp/twitter-roberta-base-sentiment-latest` | Not stated on card; ONNX/transformers.js availability not mentioned on page [V] | CC-BY-4.0 [V] (https://huggingface.co/cardiffnlp/twitter-roberta-base-sentiment-latest) | Yes (neg/neu/pos) | Trained on ~124M tweets 2018-2021, TweetEval fine-tune; no accuracy figure on card [V]. Python route needs `transformers` + torch (heavier) |
| Claude Haiku 5.5 (`claude-haiku-5-5`) | n/a (API) | API terms | Any prompt | Listed as the fastest model, intended for "classification, extraction, and routing"; from $0.10 / $0.50 per million input/output tokens [V] (https://platform.claude.com/docs/en/about-claude/models/overview). Needs backend key, network, and adds an API round trip per sentence; I found **no verified latency figure** [U] |

Recommendation: **DistilBERT SST-2 in the browser.** Reasons: (1) TDD 3.1 requires the replay path to work offline, with no key and no backend; a client-side selector over the committed sentences works identically for live and replay, while an LLM call would break offline replay. (2) No API key or new backend route; no ownership conflict with A/B. (3) Apache-2.0 and a one-line API. (4) Binary output is fine for a *mismatch* flag if we gate on high confidence.

Risks: first load downloads ~67 MB (cached afterward by the browser cache/transformers.js cache **[U]**); preload in the Worker on page open, show the feature as "warming up" until ready, and fail silently (feature just stays off). I found no sourced millisecond latency for DistilBERT in the browser [S]; expect short sentences to take well under a second on an M4 **[U]**, measure it. SST-2 is movie-review sentiment, so short conversational lines can be noisy; mitigate with thresholds.

Fallback if the download is a problem on demo Wi-Fi: pre-bundle the model files in `public/models/` and set `env.allowRemoteModels=false` (**[U]** transformers.js setting name; check docs), or let the backend (A) call Haiku and add a `text_sentiment` field to committed segments (needs schema change, A approval).

### Mismatch rule (suggested, tunable)
Compute per committed sentence: `textPol` from SST-2 (`score` >= 0.90 required; else "unclear", no flag). Vocal side: take the sentence's time-weighted dominant emotion from existing annotations, require its model support above the app's "not faint" threshold and dominant != neutral.
- **Flag** when `textPol=POSITIVE` and vocal in {angry, sad, fearful, disgusted}; or `textPol=NEGATIVE` and vocal = happy. Surprised is ambiguous; do not flag.
- Neutral vocal never flags (avoids false alarms on flat reading voice).
- Minimum 3 words in the sentence. Show an unobtrusive badge on the sentence, not a cloud; log both signals in the inspector. Test fixtures: "That's great." angry; "I'm fine." sad; "This is terrible!" happy; plus controls with matching tone.

### Does research support text-voice incongruity as a sarcasm cue? Partly; keep the claim modest
- Cheang and Pell (2008), "The sound of sarcasm", Speech Communication 50(5): English sarcasm shows a slower speech rate and reduced F0 (mean pitch), reduced F0 variability and HNR [S] (summaries via https://pubmed.ncbi.nlm.nih.gov/19739753/ for the Cantonese/English paper and https://www.cs.columbia.edu/~julia/papers/cheangDell08.pdf; I did not read the full text). They describe sarcasm as mainly conveying negative critical attitude [S].
- Cross-linguistic variation: slower rate is the most consistent cue; pitch direction differs (English lower F0, Cantonese higher; Mandarin driven by contour complexity) [S] (https://ling.cuhk.edu.hk/people/peggy/ICPhS2019_LanHuiXuMok.pdf, https://research.rug.nl/en/publications/prosodic-encoding-of-sarcasm-at-the-sentence-level-in-dutch/).
- A Groningen study reports a trade-off: when semantic cues for sarcasm are present, listeners/speakers rely less on prosody, and vice versa ("dry" vs "dripping" sarcasm) [S] (https://arxiv.org/html/2408.14892v1).
- A recent preprint, "When Models Hear What They Expect: Diagnosing Prosodic Heuristics in Multimodal Sarcasm Detection" (https://arxiv.org/pdf/2608.30204), appeared in results; I did **not** read it. Treat as **[U], not peer-reviewed**, and do not cite its claims.
- I did **not** find a source that directly shows "positive words + emotion-model vocal anger" reliably predicts sarcasm. So: say "differ", not "sarcasm". Sarcastic speech is not simply "angry"; the acoustic markers above (slower, lower, flatter) do not map onto emotion2vec's anger class **[U inference]**, so a mismatch flag is a weaker and different signal than sarcasm detection. Defensible one-liner for judges: "Words and voice can carry different signals; research shows sarcasm often involves that gap, but a gap alone does not prove sarcasm."

---

## 5. Accessibility of the visualization

### WCAG 1.4.1 (Use of Color)
Color must not be the only visual means of conveying information or distinguishing elements; add shape, text labels, icons, or patterns [V] (https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html). The cloud design already pairs color with geometry (TDD 7.2: "Make shape silhouette distinct even for color-vision differences"), so keep that and add an optional text label (inspector, plus a small label tag on focus/hover and a toggle "Always show emotion labels").
Do not rely on the cloud alone for screen-reader users: give each annotated phrase `aria-label`/`aria-describedby` with category and support (TDD inspector requirement), and keep text above the cloud.

### Palette
TDD palette: angry `#DC4545`, sad `#478CD4`, happy `#EDB94B`, fearful `#9975D8`, surprised `#EF9858`, disgusted `#68A876`. Risk **[U, not simulated]**: red, orange and green can be hard to tell apart for red-green color vision deficiency, particularly angry (red) vs disgusted (green) vs surprised (orange). The shape cues mitigate this, but if the team wants a safer set, the Okabe-Ito palette is designed to be unambiguous for both color-blind and non-color-blind viewers [V] (https://jfly.uni-koeln.de/color/), hex values: orange `#E69F00`, sky blue `#56B4E9`, bluish green `#009E73`, yellow `#F0E442`, blue `#0072B2`, vermilion `#D55E00`, reddish purple `#CC79A7`, black `#000000` [S] (https://search.r-project.org/CRAN/refmans/see/html/okabeito_colors.html).
Suggested mapping (6 emotions; keeps intuitive hues): angry vermilion `#D55E00` (jagged), sad blue `#0072B2` or sky `#56B4E9` (rounded; check on navy `#101827` since dark blue has low contrast, use sky `#56B4E9`), happy yellow `#F0E442`, fearful reddish purple `#CC79A7`, surprised orange `#E69F00`, disgusted bluish green `#009E73`. Note vermilion vs orange are the closest pair; they differ by shape (spiky vs burst) and label. Keep the existing palette if time is short; the shape coding satisfies the 1.4.1 intent. Run a CVD simulator (Chrome DevTools > Rendering > "Emulate vision deficiencies") before the demo.

### Reduced motion
`prefers-reduced-motion: reduce` is widely available since Jan 2020; use it to remove or replace non-essential animation [V] (https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion). Implement in JS because the rAF loop owns the animation:
```ts
const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
let reduced = mq.matches; mq.addEventListener('change', e => { reduced = e.matches; });
// in loop: if (reduced) { skip noise/breathing term; transitions become 150-200 ms opacity fades }
```
Semantics (color, shape, label) stay; only motion stops. Never flash faster than 3 Hz (TDD already says "never seizure-like").

---

## Open items / what I could not verify
- No measured DistilBERT-in-browser latency, no Haiku latency; measure both in the first 10 minutes.
- `blobs` package unverified; Recharts API page unreachable; Chart.js not researched.
- No direct study of AGC/noise suppression on emotion models; A/B in-room.
- Chrome-specific 16 kHz AudioContext behavior is from search summaries, not the Chrome docs.
- Palette CVD behavior not simulated.
