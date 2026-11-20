# Rehearsal: demo lines, delivery, checklist, fallback

Sources: `docs/DEMO.md`, `docs/research/R2` s6 (demo tips), R5 s1 and s4. R2 s6 says the model was trained and benchmarked on mostly acted speech, so use clearly acted, sustained lines at normal mic distance. It also says to rehearse the exact lines on the real laptop and tell judges they were rehearsed. No source ranks per-emotion reliability, so test each line and keep only those that work.

## The lines (say each with a 2-second pause before and after)

| # | Cue | Line | How to deliver |
|---|---|---|---|
| 1 | Neutral | "The meeting starts at three o'clock tomorrow." | Flat, even pace, no stress, quiet-normal volume. |
| 2 | Angry | "I told you three times, and nobody listened!" | Louder, clipped, hard consonants, stress "three" and "nobody", fast, falling pitch, tight jaw. Keep it sustained to the end of the line. |
| 3 | Sad | "I just feel really tired of trying." | Slow, soft, low energy, breathy, pitch drifting down, a small pause after "really". Do not whisper (the model needs signal). |
| 4 | Happy | "We got the grant, I cannot believe it!" | Bright, higher pitch, wide pitch swings, smiling while speaking, quick and lifted. |
| 5 | Mismatch | "Oh great, that's just perfect." | Say it ANGRY: loud, clipped, hard stress on "great" and "perfect". Positive words, angry voice. Needs 3 or more words and text sentiment of 0.90 or higher to flag (PLAN D3, R5 s4). Test it: if the badge does not appear, switch to "Thanks so much, that is wonderful." angrily, or the backup "I'm fine." said sadly (R5 s4 fixtures). |

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
"Live transcription is not cooperating right now. [Say what failed: the network, the mic, the backend.] I am switching to replay. This is a saved recording of events from a real run, played through the same interface, not live." (Press Stop if active, Reset, switch to REPLAY, play the named fixture. Point at the REPLAY banner and the provenance label.) "Same screen, same clouds. What you do not get in replay is me speaking to it live, which is why I wanted to show you that. You can see the jagged cloud on the angry line, the rounded one on the sad line, and the badge where the words and voice differ."
If the fixture is synthetic rather than recorded from a real session, say that: "This fixture was authored for testing, not recorded." Read the provenance shown in the UI and say exactly that. Never present replay as live.
If the judge wants to see live later, offer: "Come back in five minutes, I will have it fixed."

## After a live miss
"That line did not register the way I intended. The model is a pretrained estimate, and quiet or flat speech tends to read neutral." Do not blame the judge, the room or the model's makers (FunASR license s4.2, R2 s5).
