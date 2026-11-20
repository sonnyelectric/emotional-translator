# Review: Emotional Translator (Judge J2)

Reviewer role: a skeptical table-side judge plus a senior code reviewer. Branch `dev/hackathon-build` at `f097e93`. Everything below was checked against the repo, not taken from reports. Where I ran something myself, I say so. Where something has not been run by anyone, I say "not run".

## 0. What I verified myself

| Check | Command | Result |
|---|---|---|
| Backend tests (core + audio_ai) | `cd backend && ../.venv/bin/python -m pytest tests/core tests/audio_ai -q` | **250 passed** in 17.4 s |
| Frontend tests | `npm test` | **Fails: there is no `test` script** in `frontend/package.json`. The real command is `npm run test:unit`. |
| Frontend unit tests | `npm run test:unit` | **124 passed** (7 files) |
| Frontend typecheck | `npm run typecheck` | clean |
| Frontend build | `npm run build` | succeeds; ORT wasm asset is 26.9 MB |
| Text-sentiment model on the demo lines and the replay fixture | `@huggingface/transformers` 4.3.2, `Xenova/distilbert-base-uncased-finetuned-sst-2-english`, `dtype: q8`, in Node (same library and model as the browser worker) | See the table below. Two findings change the demo. |

Text-sentiment results I ran (label, score; the badge gate is score >= 0.90):

| Text | Label | Score | Consequence |
|---|---|---|---|
| "We got the grant, I cannot believe it!" (demo line 4, happy) | **NEGATIVE** | **0.907** | **Fires "Words and voice differ" if the voice reads happy.** A false badge one line before the real mismatch line. |
| "I asked once, and I am tired of being ignored." (`replay_demo` fixture, angry cloud) | **POSITIVE** | **0.945** | **Fires a false badge in replay.** It is visible in `docs/screenshots/03-settings.png`. |
| "We got the grant, this is amazing!" (proposed replacement) | POSITIVE | 0.99988 | Safe. |
| "I told you three times, and nobody listened!" | NEGATIVE | 0.99532 | Correct polarity. |
| "I just feel really tired of trying." | NEGATIVE | 0.99978 | Correct polarity. |
| "The meeting starts at three o'clock tomorrow." | POSITIVE | 0.99314 | Fires only if a visible negative cloud appears on a neutral line. |
| "I'm fine, really." / "Oh great, that's just perfect." | POSITIVE | 0.9998+ | Good mismatch lines. |

Not run by anyone yet: any ElevenLabs Scribe call, any end-to-end live session with a human voice, any threshold tuning on a human voice, any mismatch badge from live audio.

---

## 1. Scorecard

"Now" is the product as it stands. It has never produced a cloud from a human voice end to end, and every replay fixture is synthetic. "Projected" assumes the event-day steps (key, smoke test, basis set, room tuning, 2–3 interviews, one recorded fixture) succeed. The projection splits on one unknown that nobody controls: the Scribe timestamp basis.

| Category (max) | Now | Projected, basis = connection | Projected, basis = segment (no plan B) | Why |
|---|---|---|---|---|
| Problem understanding and user evidence (25) | 14 | 18 | 18 | Strong, cited, honestly hedged literature (WHO, CHI 2023, the 28-viewer null result). Zero first-hand user evidence. Two or three real interview quotes, including a critical one, are worth about +4. |
| Usefulness and product experience (25) | 9 | 17 | 10 | Today a judge can only see synthetic replay or an "Error: not configured" screen. If live clouds land on the right words, the product is genuinely legible and the accessibility settings are real. If the basis is segment-relative, live shows captions only, which is a caption app. |
| Technical execution (25) | 16 | 20 | 15 | 374 passing tests, a measured model benchmark (p95 70.5 ms per 2 s window on CPU), careful alignment, bounded worker and recovery. Not yet proven end to end. The alignment depends on two unverified provider behaviours (timestamp basis and the exact word-text join). |
| Differentiation and next-step business (15) | 9 | 10 | 8 | Google Expressive Captions is named first and credited, which is right. The words-vs-voice flag is the real differentiator, but only if it fires live. The business story is a reasonable wedge with no willingness-to-pay evidence. |
| Demo clarity (10) | 5 | 8 | 5 | The script is well structured. Beat 2 crams five statistics into 30 seconds, which will not survive a noisy room. Without a live cloud there is nothing to point at except synthetic replay. |
| **Total (100)** | **53** | **73** | **56** | |

Bottom line: the project is honest and well engineered, but it is one provider fact away from having no demo. Treat the smoke test as the first job of the day, and prepare plan B before 11:00 (Section 4, item F3).

---

## 2. Demo-risk register

L = likelihood, I = impact, each High, Medium or Low. "Say" is the exact line to use at the table.

| # | Failure | L | I | Mitigation before 4 PM | Fallback at the table and what to say |
|---|---|---|---|---|---|
| R1 | **Scribe timestamp basis is segment-relative, or unknown.** `segments.py:153-156` returns `ALIGNMENT_BASIS_UNKNOWN` for both, so no cloud is ever placed and the badge can never fire. The adapter always reports `unknown` (`adapters/scribe.py:128`). | M (undocumented, roughly a coin flip) | H | Run `scripts/smoke_scribe.py` first thing. If the verdict is segment-relative, use plan B in Section 4, item F3. | "Captions are live. The tone layer needs word timing that the provider does not label clearly, so rather than put clouds on the wrong words, it shows none. Here is the same interface in replay, labeled as such." |
| R2 | **Word-text join does not equal the commit text.** `segments.py:143` requires `" ".join(word texts)` to equal the committed text after whitespace normalization only. Any punctuation, casing or spacing difference silently kills every cloud with `ALIGNMENT_TIMESTAMP_MISMATCH`. | M | H | Read the raw smoke frames and compare the joined `words[].text` with `text`. If they differ, apply F4. | Same as R1. |
| R3 | **Untuned thresholds.** The thresholds (visible 0.42, faint 0.25, neutral suppress 0.50) were never tuned on a human voice (`docs/live/benchmark.md`, "NOT retuned"). | H | M | Tune in the actual room with `?tune=1`, saying each line 5 times. Change `.env` only for a line that fails consistently, and log every change in `benchmark.md`. | "That line didn't register. These are estimates and I rehearsed these lines, so I'll tell you when one misses." Move to the next line. |
| R4 | **Peaked scores, or `unknown` winning on pauses.** The benchmark saw `unknown` at 0.65–0.98 on pause-heavy windows. A phrase vector averages every window that overlaps the words (`phrases.py:53-88`). Windows that straddle the 2 s pause before and after a short line pull toward `unknown` or `neutral`, and a tie suppresses the phrase (`smoothing.py:52`). The tune page shows one window at a time (`tune.py:137-139`), so it will look better than the phrase-level result. | H | M | Use lines of at least 2.5 s, held to the last word, with no mid-line pause. Shorten the pause between lines to about 1 s; long pauses don't help the windows. Judge success from a full live run, not from the tune page. | Same as R3. |
| R5 | **Venue noise.** The RMS silence gate is 0.003, about −50 dBFS (`emotion/worker.py:17`). A busy room will never be that quiet, so the gate will not fire and room noise is scored as `neutral` or `unknown`. Scribe's VAD may also take longer to find the 0.65 s silence it needs before it commits text. No commit means no timing, which means no cloud. | H | H | Use a wired headset or lavalier mic, about a hand-width from the mouth. Test at 3:30 PM in the judging room itself, not at a quiet table. | "It's loud in here, so I'm using a close mic. If the captions lag, that's the provider waiting for a pause." |
| R6 | **Your narration and the judge's voice get captioned.** The talk track narrates between lines while listening. That narration gets transcribed, scored and possibly badged. The judge's voice also goes to ElevenLabs. | H | M | Press Pause while explaining and Resume before each line. Each Resume opens a new connection, so rehearse that it reconnects within about 1 s. Disclose once at the start. | "Quick note: while I'm listening, audio goes to ElevenLabs for transcription. The tone model runs on this laptop." |
| R7 | **A false "Words and voice differ" badge on the happy line.** Line 4's text scores NEGATIVE 0.907 (run above). | H, if the happy cloud lands | M (undercuts the punchline) | Change line 4 to "We got the grant, this is amazing!" (POSITIVE 0.99988) in TALK_TRACK, REHEARSAL and BACKUP_VIDEO. Also raise the gate (F1). | If it fires anyway: "That's a false flag. The text model misread 'I cannot believe it' as negative. It's a cue, not a verdict." |
| R8 | **A false badge in replay.** `replay_demo` shows a badge on "I asked once, and I am tired of being ignored." with an angry cloud (screenshot 03). REHEARSAL and integration-run both say replay never shows a badge. | H (deterministic) | M | Apply F1, which suppresses it at 0.945. Or use `replay_anger_sad` as the fallback fixture, or switch Words vs voice off in replay. | "That badge is a false positive from the text model on authored test data." |
| R9 | **Wi-Fi for Scribe.** | M | H | Phone hotspot tested by 3:45 PM. | Switch to replay and read out the provenance (see Section 3, H1). |
| R10 | **Wi-Fi for the 68 MB text model.** There is no `frontend/public/models/`, so the browser downloads it from Hugging Face. The ORT wasm may also come from a CDN in dev (unverified). | M | M (no badge, which fails silently) | Pre-bundle the model: `mkdir -p frontend/public/models/Xenova && cp -R frontend/node_modules/@huggingface/transformers/.cache/Xenova/distilbert-base-uncased-finetuned-sst-2-english frontend/public/models/Xenova/`. The cache already exists from my run, and `models/` is gitignored. Then test with Wi-Fi off. | "The words-vs-voice check runs in the browser and it's still loading." Show it later or in the video. |
| R11 | **Mic permission or the wrong input device.** | M | H | Grant permission in Chrome at 3:45 PM, select the headset in macOS Sound settings, and confirm the level meter moves. | Fix it in about 20 s, or switch to replay. |
| R12 | **Model load time.** About 4.5 s warm and 21.7 s cold (benchmark). If you press Start while it is still loading, every window is unusable and phrases get no clouds. | L | M | Launch `demo_live.sh` at least 1 minute before the judge arrives and confirm "Model: ready" on `?tune=1`. | Wait it out: "The model loads locally. Five seconds." |
| R13 | **Opening `127.0.0.1:5173` instead of `localhost:5173`.** The WebSocket Origin check is an exact match against `http://localhost:5173` (`ws.py:188`). | L | H | Bookmark `http://localhost:5173`. | Retype the URL. |
| R14 | **Reconnect gaps.** `insufficient_audio_activity` triggers an immediate reconnect (`session.py:369-379`). Audio during the reconnect is not forwarded (`session.py:405-407`), so the first syllables of the next line can be lost. | M | L | Pause while talking to the judge (R6) so idle connections close cleanly. | Repeat the line. |
| R15 | **A quota or terms error on a fresh account** (`SCRIBE_TERMS`, `SCRIBE_QUOTA`). | L | H | The smoke test catches it at 11:15. | Replay. |

---

## 3. Honesty audit

I checked every factual claim in TALK_TRACK, JUDGE_QA and SUBMISSION against `docs/research/R1–R5` and `SYNTHESIS.md`. Claims that check out are not listed: the WHO 2.5 billion projection, NIDCD 15% / 37.5 M (self-reported, NHIS 2012 data), WHO isolation and loneliness, the CHI 2023 study with 16 DHH participants, the 28-viewer null result, Google Expressive Captions availability, $0.22/h, the EU AI Act Art. 5(1)(f), Barrett 2019 on faces, the $3–5B speech-analytics range, the Apache-2.0 base model, the FunASR attribution, and "transcribes, does not translate".

### High: fix before anyone says it

- **H1. The fallback line asserts provenance that does not exist yet.** The "If live fails" script in REHEARSAL says "This is a saved recording of events from a real run". All 7 fixtures in `shared/fixtures/manifest.json` are `synthetic_example`, which means hand-written. A caveat follows two sentences later, but the first sentence is false today. Rewrite it to read the provenance first: "This is replay, not live. This fixture is [read the banner: hand-written test data / recorded from a real session]."
- **H2. "Replay never shows the badge" is false.** REHEARSAL (mismatch section and fallback script) and `docs/live/integration-run.md` both say no fixture has a mismatch line. `replay_demo` shows "Words and voice differ" on an angry, negative-worded sentence (screenshot 03; text POSITIVE 0.945 from my run). It is a false positive shown in your own screenshot, and a judge who opens Settings will see it.
- **H3. "It runs in a browser on any device" overclaims.** This is TALK_TRACK Beat 5; JUDGE_QA 5 says "browser-based" and SYNTHESIS pitch line 7 says "runs in any browser". The tone model is a 1.95 GB local Python process with 2.4 GiB peak memory (benchmark), and the browser is only the display. Say: "The interface is a web page. Today the tone model runs on a laptop beside it, not on a phone."
- **H4. The happy demo line will probably raise a false "differ" badge** (Section 0). This is not a false claim, but the script promises a clean contrast that the model will not deliver.

### Medium: overclaims and imprecision

- **M1. JUDGE_QA 11 overgeneralizes.** It says participants "preferred clean text with color over cartoon icons". R3 §1 says *two Deaf participants* said that. "Over half wanted toggles" is correct. Fix: "...and two Deaf participants said they preferred clean text with color over cartoon icons."
- **M2. TALK_TRACK Beat 3 describes the inspector's scores wrongly.** It calls them "relative model scores for the 2-second window". They are actually an EMA-smoothed, overlap- and duration-weighted average over every window that touches the phrase (`smoothing.py:25-31`, `phrases.py:53-88`). Say: "relative model scores averaged over this phrase, not certainty."
- **M3. JUDGE_QA 1 volunteers "about 72 percent".** It is labeled correctly as the original emotion2vec on IEMOCAP (R2 §4). In a noisy room, though, a judge remembers the number and not the caveat. SYNTHESIS's do-not-say list bans any accuracy percentage for our system. Drop the number: "The base paper reports beating comparable models on acted benchmarks. There is no published number for the version we use, and I haven't measured one."
- **M4. TALK_TRACK Beat 2 drops the legibility cost from the CHI 2023 result.** SYNTHESIS pitch line 5 includes "at a moderate cost to legibility", and it is also the reason the clouds are subtle and can be toggled. Put it back; it costs four words.
- **M5. JUDGE_QA 7 is still a FILL even though real numbers exist.** Fill it with: "Model scoring takes about 65 ms per 2-second window on this laptop's CPU (p95 70 ms, benchmark on synthetic speech). End-to-end time from phrase end to cloud has not been measured." Do not estimate the end-to-end time.
- **M6. JUDGE_QA 3 says "Normal sessions are not stored".** That is true of the code today. Once you record a live session as a fixture, that session is stored, as events and text with no audio. Add: "except one demo session I recorded of my own voice, as text events only."
- **M7. Rule drift: the minimum is 2 words in code, 3 in the spec.** REHEARSAL line 5 and SYNTHESIS rule 6 say 3 or more words; `valence.ts:10` has `MIN_WORDS = 2`. REHEARSAL notes this, but the table row still says 3.
- **M8. Rule drift: surprised can flag.** SYNTHESIS mismatch rule 5 says "Surprised and neutral never flag". Code maps `surprised` to positive valence (`valence.ts:12-19`), so negative text with a surprised voice flags, and the test enshrines it (`valence.test.ts:35`). See F2.

### Low

- **L1. The prize source is outside the research files.** TALK_TRACK §D says the ElevenLabs prize "is confirmed on the event page (luma.com/yog7cocv)", but SYNTHESIS A8 marks it UNVERIFIED and no research file cites that page. The organizers' rubric names the prize, so this is fine. Just don't cite a page nobody in the repo fetched.
- **L2. Beat 2 is a wall of numbers.** It is accurate, but at least two of the five numbers will be lost in the room (see Section 5).

### Unlabeled synthetic data, and places the UI could mislead

- **U1.** Every fixture is `synthetic_example`. The banner labels this correctly: "Synthetic example: hand-written events, not model output". But three nearby UI strings contradict it during replay:
  - The banner lead says "Saved **result**, not live audio." (`ReplayBanner.tsx:21`).
  - The fixture picker is labeled "Saved **result**" (`SessionControls.tsx:54`).
  - The profile footnote says "Detected vocal cues from the emotion2vec+ model" (`App.tsx:414-416`), and it is shown under hand-written data.
  
  The inspector also says "The voice in this phrase scored highest for sad" about a phrase no voice produced. Fix: rename both strings to "Saved replay", and in replay show the provenance text instead of the model footnote (F6).
- **U2. "Confidence" wording is handled well.** The UI says "Relative model support, not confidence" and "Model scores (not calibrated probabilities)". The inspector's whole-number percentages ("66% relative model support") will still read as confidence to a lay judge, so say "relative" out loud every time.
- **U3.** `benchmark.md` and `integration-run.md` label TTS and fake-mic inputs as synthetic. Good; keep any number from them out of the pitch except latency.

### When and where it was built

- **The pitch docs (TALK_TRACK, JUDGE_QA, SUBMISSION, REHEARSAL, BACKUP_VIDEO, USER_FEEDBACK) contain no statement about when or where the project was built.** The dates in them describe the event, the feedback sessions or a test run. TALK_TRACK explicitly says "Do not say when or where the app was built." That passes.
- **Internal docs do contain build-timing statements**, and a judge would see them if the repo link is submitted:
  - `docs/PLAN.md` §6 "Timeline (tonight, PT)" (01:30–05:30) and D2 "Pre-download them tonight";
  - `docs/live/scribe-preflight.md` ("no API key at build time", "the summarizing fetch tonight").
- **README.md's "Implementation kit" section** says the work is for "three developers and three coding agents", while PLAN says "solo, with AI agents". A judge reading the repo could be misled about team size.

  I am not recommending what to say either way. The owner should decide what the submitted repo shows, and make it consistent.

---

## 4. Code review

### Fix before demo (each 30 minutes or less, ranked by demo impact)

- **F1. Raise the text gate from 0.90 to 0.97** (`frontend/src/mismatch/valence.ts:7`), and update `valence.test.ts`. Because: it removes both false badges found in Section 0 (0.907 and 0.945). Every intended mismatch line scores 0.9998 or higher. Time: 5 minutes. Also change demo line 4 in three docs (R7).
- **F2. Surprised must never flag** (`valence.ts:55-57`). Add `if (voice === 'surprised') return false;` to `opposes`, and change the test at `valence.test.ts:35` to expect no flag. Because: SYNTHESIS rule 5 requires it, and a surprised cloud is ambiguous in valence. Time: 5 minutes.
- **F3. Plan B for a segment-relative basis** (`backend/app/alignment/segments.py:153-156`). Today `segment` means no clouds ever. Prepare this now, and decide after the smoke test:
  - **Zero-code plan B.** If the smoke test shows phrase A on each *fresh* connection starting at about the lead-silence time, the first commit of each connection is effectively connection-relative. Set `SCRIBE_TIMESTAMP_BASIS=connection`, then press Pause → Resume between every line, so each line is the first commit of a new epoch. The risk is that a second commit inside one epoch lands on the wrong words. The bounds check (`segments.py:166`) catches only part of that. So speak exactly one line per Resume and rehearse it.
  - **Code plan B (about 30 minutes, with a test).** Accept `segment` only for the first commit of each epoch, and warn for the rest. That makes the zero-code version safe.
  - Do not invent an origin from commit timing on demo day.
- **F4. Loosen the word-join check** (`segments.py:142-144`). Compare against the timed notice's own `text`, which `adapters/scribe.py` already carries, before falling back to the commit text. Normalize case and strip punctuation on both sides. Because: an exact join is the single most likely silent killer of all clouds after the basis question. Time: 15 minutes, plus one test with the real frame from the smoke test.
- **F5. Add a live-session recorder for the labeled fixture.** Nothing in the repo can currently save a live session as a replay fixture, even though PLAN D9 and the run sheet assume one. Fixture lines are exactly the server events that `Emitter.emit` produces (`session.py:96`).
  1. Add an opt-in tee: when `RECORD_EVENTS=/abs/path.jsonl` is set, append each emitted JSON line to that file.
  2. Write a small converter that rewrites `session.status` payloads to `mode: "replay"`, `scribe/emotion_model: "not_required"`, and sets a fixed `session_id`. This is needed because `replay.py:243` rejects non-replay status.
  3. Add a manifest entry with `provenance: "recorded_result"`.
  4. Run `scripts/verify_replay.sh`.
  
  Time: 30 minutes. If it slips, skip it and keep the honest synthetic label.
- **F6. Fix the replay UI copy** (`ReplayBanner.tsx:21`, `SessionControls.tsx:54`, `App.tsx:414-416`): "Saved result" becomes "Saved replay", and the model footnote is hidden in replay mode or replaced with the provenance text. Time: 10 minutes. See U1.
- **F7. Pre-bundle the text model** (command in R10). Time: 2 minutes plus a test with Wi-Fi off.
- **F8. Add `"test": "vitest run"`** to `frontend/package.json`. Because: judges and reviewers will type `npm test` and see an error. Time: 1 minute.

### Post-hackathon

1. **Phrase evidence is diluted by silence and `unknown` windows** (`phrases.py:53-88`, `smoothing.py:52`). Exclude windows whose top label is `unknown`, or whose RMS sits near the noise floor, from word vectors. Also make the RMS gate relative to a measured noise floor instead of a fixed −50 dBFS (`emotion/worker.py:17`).
2. **The tune page tunes the wrong thing** (`tune.py:137-139`). It classifies single windows, but the live pipeline classifies phrase averages. Add a "phrase" readout (for example, the mean over the last N windows) so tuning matches what the judge sees.
3. **The eager reconnect on `insufficient_audio_activity`** (`session.py:369-379`, `relay.py:34`) bills silence and drops the start of the next utterance. Reconnect lazily on the next above-gate frame, and buffer about 1 s of audio for replay into the new epoch.
4. **`retry_once_seen` lives for the whole session and never resets** (`session.py:258`, `relay.py:52-56`). A second `commit_throttled` an hour later is fatal. Reset it after a healthy period.
5. **`ALIGNMENT_BASIS_UNKNOWN` is a dead end for `segment`.** Investigate whether Scribe's `session_started.config` or a diarized `segment_index` can give an origin. Otherwise switch to `commit_strategy=manual`, where we own the commit boundaries.
6. **The Origin check is an exact string match** (`ws.py:188`). Also accept `http://127.0.0.1:5173`.
7. **`MIN_WORDS` 2 vs 3** (`valence.ts:10`): pick one and document it.
8. **An end-to-end latency metric** from phrase end to `emotion.finalized` is missing. This is the number judges ask for.
9. **SST-2 is a movie-review model** and misreads plain speech ("I am tired of being ignored" comes out POSITIVE 0.945). Evaluate a three-class sentiment model with a neutral class before trusting the flag.
10. **Bias, accent and spontaneous-speech evaluation:** none exists (R2 §4). It is required before any accessibility claim.

---

## 5. Script critique

**What works.** The "I'm fine" hook is concrete and human. The wording discipline ("detected vocal cue", "differ", not "sarcasm") is exactly right for a skeptical judge. Naming Google first defuses the obvious attack. Saying a miss out loud is a strength.

**What doesn't work in a noisy room with a non-technical judge:**

1. **Beat 2 has five statistics in 30 seconds** (2.5 B, 15%, 37.5 M, a 16-person study, a 28-viewer study). A judge standing at a table keeps one number at most. Keep the WHO projection and the two studies (one for, one against). Move the US numbers to Q&A.
2. **The hook is never paid off.** The opening is "I'm fine" said through tears, but the demo never says "I'm fine". The app can show exactly this: "I'm fine, really, it's fine." said sadly scores POSITIVE 0.9998 as text, so with a sad cloud it raises the badge. Make that the close, so the story ends where it began.
3. **Narration while listening** gets captioned (R6). Script the Pause/Resume presses.
4. **Line 4 will probably raise a false badge** (R7). Swap it.
5. **Beat 4 is jargon for a non-technical judge.** "emotion2vec plus Large" and "backend lines those scores up" mean nothing to them. Say "a tone model on this laptop" and keep the model name for the backup video card and the Q&A.
6. **Three minutes is tight.** Five lines, each with pauses, a 1–3 s wait for the cloud and narration, take about 70–80 s. Cut line 1 (neutral) unless a judge asks how a flat voice looks; the idle screen already shows "no cloud".

### Rewritten opening (0:00–0:20)

> "If I text you 'I'm fine', do you know if I'm fine? [beat] Captions have the same problem. Someone says 'I'm fine' through tears, and the caption says: I'm fine. The words arrive. The tone doesn't. A Virginia Tech study puts it plainly: real-time captions often omit emotional cues. This puts the tone back, as a shape around the exact words, and it tells you when the words and the voice disagree."

Citations: "real-time captions often omit emotional and non-verbal cues" is SYNTHESIS §4 may-say #4 (R3 §1, arXiv 2603.15977). I dropped "2025" because the arXiv id suggests a 2026 posting of an ACII 2025 paper, and "a Virginia Tech study" is safe either way. The tears scenario stays a thought exercise, as the existing note says. Do not present it as a real person.

### Rewritten close (2:45–3:00)

> [Resume. Say it sadly, slowly:] "I'm fine, really, it's fine." [Pause. Point.] "The words say fine. The voice doesn't. That gap is what captions drop today." [If no badge: "No badge that time. It's an estimate, and I'll always tell you when it misses."]
> "Next: test it with Deaf and hard-of-hearing users before claiming it helps anyone. The first buyer is campus disability services, because they already have a captioning obligation and a budget owner (R4 §3). Willingness to pay is untested. Today I'd love three minutes of your feedback. Thank you."

Citations: the line's text score comes from the REHEARSAL integrator run and my run (POSITIVE 0.9998). The buyer rationale is from R4 §3 ("a buyer exists, legal obligation to provide captions"); do not turn it into "the ADA requires live captions" (SYNTHESIS do-not-say). Rehearse this line 5 times. If the sad cloud does not reach visible opacity (support of at least 0.42), the badge cannot fire. In that case fall back to "Oh great, that's just perfect." said angrily, and drop the callback.

---

## 6. Event-day run sheet (PT)

Rule: if the 11:00–12:00 block slips past 12:30, stop adding features and protect the interviews, the video and the submission.

| Time | Task | Done when |
|---|---|---|
| 10:45 | Laptop on power, notifications off, headset mic plugged in. `git status` clean. Pre-bundle the text model (R10). | Static files exist under `frontend/public/models/` (gitignored). |
| 11:00 | Redeem the ElevenLabs coupon via Discord `#coupon-codes`. Create the API key and accept the terms in the ElevenLabs dashboard. Roderich types the sign-in details himself. | Key visible in the dashboard. |
| 11:10 | Paste `ELEVENLABS_API_KEY=` into `backend/.env`. Never commit it; `.env` is gitignored, and `git status` confirms. | `git status` shows nothing new. |
| 11:15 | Record a consented WAV of your own voice: 16 kHz mono, two phrases with a pause of 1.5 s or more (`ffmpeg -i in.wav -ac 1 -ar 16000 -sample_fmt s16 out.wav`). Run `.venv/bin/python scripts/smoke_scribe.py --wav /abs/out.wav`. | Verdict printed for 2 fresh streams. |
| 11:30 | Paste the scrubbed output into the "Observations" section of `docs/live/scribe-preflight.md`. Answer: the basis; whether the joined `words[].text` equals `text` (R2/F4); event order; whether the 0.65 s VAD threshold was accepted. | All 5 observation lines filled. |
| 11:40 | Set `SCRIBE_TIMESTAMP_BASIS=connection` if proven. If segment, choose F3 plan B now. Restart `scripts/demo_live.sh` and open `http://localhost:5173`. Say lines 2 and 3. | A cloud appears on the right words, **or** you know why not. |
| 11:55 | Fixes in priority order, with a hard stop at 12:45: F1, F2, F7 → F4 (if the join differs) → F3 code (if needed) → F6 → F5 → F8. Run `pytest` and `npm run test:unit` after each one. | Tests green. |
| 12:45 | Lunch, while away from the laptop. | |
| 13:15 | **Tune in the judging room, or the noisiest spot you can find.** Open `?tune=1`, say each of the 5 lines 5 times, and note the top raw label and support. Then do one **full live run** to judge phrase-level results (R4). Change `EMOTION_*` in `.env` only for a line that fails consistently, restart, and log every change and its reason in `docs/live/benchmark.md`. Write pass/fail per line in REHEARSAL. | Each kept line passes at least 4 of 5 times in live mode. Unreliable lines dropped. |
| 13:50 | Record one real live session of your own voice as a fixture (F5), with provenance `recorded_result`. Run `scripts/verify_replay.sh`. If F5 was skipped, keep the synthetic fallback and the honest label. | Fixture plays with the "Recorded result" banner. |
| 14:10 | Interview 2–3 attendees with `USER_FEEDBACK.md`: consent line first, verbatim notes, negative answers kept. No audio unless they agree. | N completed interviews written in the table. |
| 14:50 | Film the backup video (`BACKUP_VIDEO.md`) with the corrected line 4: a real live run, misses kept, any replay labeled, no key on screen. Upload it as unlisted and test the link logged out. | Link opens in a private window. |
| 15:20 | Fill in `SUBMISSION.md`: <ul><li>the replay command (`scripts/demo_replay.sh`, fixture id and its provenance);</li><li>the video link;</li><li>the user-feedback table, verbatim and permitted only, with a 1–2 sentence summary;</li><li>any measured results;</li><li>delete the Replit line if unused.</li></ul> Apply honesty fixes H1–H4 and M1–M6 to the pitch docs. | No `[FILL]` left. |
| 15:40 | **Submit.** Screenshot the confirmation. | Confirmation saved. |
| 15:45 | Room check: hotspot tested; `demo_live.sh` running with "Model: ready"; text model warmed (Settings no longer says "warming up"); mic level moves; laptop audio muted; one rehearsal of the 60-second version; backup video open on the phone. | Ready at 16:00. |

---

*Reviewer notes on method: I made no code changes. I ran `npm run build`, which rewrote the gitignored `frontend/dist/`. The sentiment checks ran from a temporary script, deleted afterwards, and used the model already cached in `node_modules`. `git status` was clean apart from this file.*
