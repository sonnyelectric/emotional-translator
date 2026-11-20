# Rehearsal: demo lines, delivery, checklist, fallback

Sources: `docs/DEMO.md`, `docs/research/R2` s6 (demo tips), R5 s1 and s4. R2 s6 says the model was trained and benchmarked on mostly acted speech, so use clearly acted, sustained lines at normal mic distance. It also says to rehearse the exact lines on the real laptop and tell judges they were rehearsed. No source ranks per-emotion reliability, so test each line and keep only those that work.

## The lines (say each with a 2-second pause before and after)

| # | Cue | Line | How to deliver |
|---|---|---|---|
| 1 | Neutral | "The meeting starts at three o'clock tomorrow." | Flat, even pace, no stress, quiet-normal volume. |
| 2 | Angry | "I told you three times, and nobody listened!" | Louder, clipped, hard consonants, stress "three" and "nobody", fast, falling pitch, tight jaw. Keep it sustained to the end of the line. |
| 3 | Sad | "I just feel really tired of trying." | Slow, soft, low energy, breathy, pitch drifting down, a small pause after "really". Do not whisper (the model needs signal). |
| 4 | Happy | "We got the grant, this is amazing!" | Bright, higher pitch, wide pitch swings, smiling while speaking, quick and lifted. |
| 5 | Mismatch | "Oh great, that's just perfect." | Say it ANGRY: loud, clipped, hard stress on "great" and "perfect". Positive words, angry voice. Needs 2 or more words (code `MIN_WORDS`) and text sentiment of 0.97 or higher to flag (PLAN D3, R5 s4). Test it: if the badge does not appear, switch to "Thanks so much, that is wonderful." angrily, or the backup "I'm fine." said sadly (R5 s4 fixtures). |

### Mismatch line check, text side only (run 2026-11-20 by the integrator)

Real run, not estimated: `Xenova/distilbert-base-uncased-finetuned-sst-2-english`, dtype `q8`, `@huggingface/transformers` 4.3.2 in Node (the same library and model id the browser worker loads).

| Line | Label | Score | Clears 0.97? |
|---|---|---|---|
| "Oh great, that's just perfect." | POSITIVE | 0.99987 | yes |
| "That is great, thanks so much for cancelling on me again." | POSITIVE | 0.99960 | yes |
| "I'm fine, really, it's fine." | POSITIVE | 0.99985 | yes |
| "Thanks a lot." | POSITIVE | 0.99981 | yes |

All four pass the text gate, so line 5 stays as written; any of the others is a valid backup (say it angrily or sadly). This only proves the text half. The badge also needs (a) Scribe to transcribe the words exactly enough to keep the polarity, (b) a visible (opacity >= 0.31) angry, sad, fearful or disgusted cloud on that segment, which needs word timestamps, so `SCRIBE_TIMESTAMP_BASIS` must be set from the smoke test (with `unknown` no cloud is placed and the badge cannot fire), and (c) the browser model to have finished its first download (Settings shows "warming up" until then). The code's minimum is 2 words (`MIN_WORDS` in `frontend/src/mismatch/valence.ts`), not 3. Replay and the badge: see the fixture check below. With the 0.97 gate no replay fixture shows the badge; do not promise one in the fallback script.

### All five demo lines, text side (run 2026-11-20 by fixer F1, same model and settings)

| Line | Label | Score |
|---|---|---|
| 1 "The meeting starts at three o'clock tomorrow." | POSITIVE | 0.99314 |
| 2 "I told you three times, and nobody listened!" | NEGATIVE | 0.99532 |
| 3 "I just feel really tired of trying." | NEGATIVE | 0.99978 |
| 4 "We got the grant, this is amazing!" | POSITIVE | 0.99988 |
| 5 "Oh great, that's just perfect." | POSITIVE | 0.99987 |
| close "I'm fine, really, it's fine." | POSITIVE | 0.99985 |

Line 4 was "We got the grant, I cannot believe it!", which the model reads NEGATIVE 0.907 (docs/REVIEW.md), a false badge if the voice reads happy. It was swapped. Line 1 is POSITIVE 0.993, so a visible angry/sad/fearful/disgusted cloud on it would flag; say it flat.

### Replay fixtures: would any segment show a false badge? (run 2026-11-20 by fixer F1)

Real run, not estimated: `npm run check:fixtures` in `frontend/` (`frontend/scripts/fixture_sentiment.ts`). It scores every committed segment of every fixture in `shared/fixtures/manifest.json` with the model above, rebuilds the segment's final annotations from the fixture events, and applies the unchanged badge logic (`computeMismatch`, gate 0.97, surprised never flags). It exits non-zero if any segment would flag. Re-run it on any newly recorded fixture.

| Fixture | Segment | Text | Label | Score | Dominant visible voice | Badge |
|---|---|---|---|---|---|---|
| replay_demo | seg-1 | "For the record, everyone arrived on time." | POSITIVE | 0.99882 | none | no |
| replay_demo | seg-2 | "I asked once, and I am tired of being ignored." | POSITIVE | 0.94541 | angry | no (flagged at the old 0.90 gate) |
| replay_demo | seg-3 | "I waited by the door for hours, hoping you would come back even after the whole house had gone quiet." | NEGATIVE | 0.99563 | sad | no |
| replay_demo | seg-4 | "The last bus leaves at midnight." | NEGATIVE | 0.96237 | none | no |
| replay_demo | seg-5 | "I am glad we can finally go home." | POSITIVE | 0.99965 | happy | no |
| replay_anger_sad | seg-1 | "I am so tired of hearing that, and I wish you would stay." | NEGATIVE | 0.99920 | angry | no |
| replay_neutral | seg-1 | "The meeting begins at nine." | POSITIVE | 0.98447 | none | no |
| replay_mixed | seg-1 | "I cannot believe how this ended." | NEGATIVE | 0.99199 | angry | no |
| replay_delayed_timing | seg-1 | "I thought you would call." | POSITIVE | 0.65674 | sad | no |
| replay_delayed_timing | seg-2 | "Maybe the signal dropped." | NEGATIVE | 0.99824 | none | no |
| replay_failures | seg-1 | "The first sentence stays on screen." | POSITIVE | 0.99783 | none | no |
| replay_failures | seg-2 | "The transcript can continue." | POSITIVE | 0.63548 | none | no |
| replay_retraction | seg-1 | "I will try again tomorrow." | POSITIVE | 0.89076 | none | no |

Result: 0 of 13 segments show the badge.

Delivery rules:
- Mic about a hand-width (10-15 cm) away, same distance every time. Do not shout into it. Strong prosody beats volume.
- Hold the emotion through the whole line. Two-second windows score what they hear (R2 s4), so a half-hearted line reads neutral. Expect neutral to dominate quiet or flat speech (R2 s6).
- One full phrase per window. A single clipped word may be unstable (R2 s6, unverified).
- Practice each line 5 times on the real laptop and mic. Record which lines produce the expected cloud. Keep only reliable lines. Write the result here: [FILL: line, pass/fail, date].
- Tell the judge the lines are rehearsed. Report misses plainly.
- Do not run the demo with headphones off if speakers play audio: echo cancellation is off by default (PLAN D8), so keep laptop audio muted.

## Pre-demo checklist (docs/DEMO.md, PLAN s6)
- [ ] ElevenLabs key redeemed and in `.env`; live Scribe smoke passed; quota and terms accepted.
- [ ] emotion2vec+ Large weights downloaded (1.95 GB, R2 s1); launch with `--live` so the model is preloaded before presenting.
- [ ] Record: commit, OS, CPU, RAM, Python, Node, browser, model id (docs/DEMO.md preflight).
- [ ] Mic permission granted for the browser; correct input device; level meter moves; laptop audio muted; AGC/noise suppression/echo off confirmed.
- [ ] Browser text-sentiment model warmed (about 67 MB first load, R5 s4) so the differ badge works; confirm it fires on line 5.
- [ ] One backend worker and the frontend running; stable Wi-Fi. Mute notifications. Close other tabs.
- [ ] Replay fixture ready in the same UI (named fixture; shows REPLAY banner and provenance). Rehearse keyless replay once with networking off.
- [ ] Idle screen clean; Reset works; settings: labels on, default palette.
- [ ] Permission to speak aloud near neighbors; tell judges live transcription audio goes to ElevenLabs.
- [ ] Backup video file and link open in a second tab or on the phone.
- [ ] Interview notes (`USER_FEEDBACK.md`) and the submission form ready.
- [ ] Phone charged, laptop plugged in, battery saver off.

## Fallback path
1. Live works: use the full script in `TALK_TRACK.md`.
2. Live degraded (Scribe slow or no words): Stop, Reset, retry once. If it still fails, go to step 3.
3. Live fails (no key, no network, mic or backend down): use the script below.
4. Everything fails: play the backup video.

## "If live fails" script (say it, do not hide it)
Prefer the recorded fixture (`replay_live_recorded`, banner reads "Recorded live session, <date> (text, timestamps, scores; no audio)") once it exists; record it with `RECORD_SESSION_EVENTS=shared/fixtures/replay_live_recorded.jsonl` (see `.env.example`), then run `npm --prefix frontend run check:fixtures` and `scripts/verify_replay.sh`. Read the banner first and say the matching line:

- Recorded fixture: "Live transcription is not cooperating right now. [Say what failed: the network, the mic, the backend.] I am switching to replay. This is a recorded live session of my own voice from earlier today: the saved text, timestamps and model scores, no audio, played through the same interface. It is not live."
- Synthetic fixture (banner reads "Synthetic example (hand-written, not model output)"): "Live transcription is not cooperating right now. [Say what failed.] I am switching to replay. This is a hand-written test example, not a recording and not model output. It shows how the interface behaves."

(Press Stop if active, Reset, switch to REPLAY, play the named fixture. Point at the REPLAY banner and the provenance label.) "Same screen, same layout. What you do not get in replay is me speaking to it live, which is why I wanted to show you that. You can see the jagged cloud on the angry line and the rounded one on the sad line." (With the 0.97 gate no synthetic fixture shows the words-versus-voice badge, so do not point at a badge in replay. A recorded fixture shows a badge only if it fired live; check before promising it.) Never present replay as live.
If the judge wants to see live later, offer: "Come back in five minutes, I will have it fixed."

## After a live miss
"That line did not register the way I intended. The model is a pretrained estimate, and quiet or flat speech tends to read neutral." Do not blame the judge, the room or the model's makers (FunASR license s4.2, R2 s5).
