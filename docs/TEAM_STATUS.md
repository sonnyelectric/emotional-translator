# Team status: Emotional Translator

**As of:** Friday 2026-11-20, late morning PT.
**Deadline:** submissions close at **4:00 PM**. The demo fair and judging run 4:00–5:15 PM.
**Branch:** `dev/hackathon-build`, which exists only on Roderich's laptop for now. Roderich will push it before you pull.

## 1. What we're demoing (30-second version)

Live captions that also show **how** something was said. You speak into the laptop mic, and the words appear on screen. A soft colored cloud forms around the exact words, based on the detected vocal tone: jagged red for angry, rounded blue for sad, and so on. If the words sound positive but the voice sounds angry, a small badge appears: **"Words and voice differ."**

- **Speech-to-text:** ElevenLabs Scribe v3 Live. ElevenLabs is an event sponsor, with a "Best Project Built with ElevenLabs" prize.
- **Vocal tone:** emotion2vec+ Large, an open speech-emotion model that runs on the laptop.
- **Words-vs-voice badge:** a small text-sentiment model (DistilBERT SST-2) in the browser. It never changes the clouds; it only shows the badge.
- **Primary users:** Deaf and hard-of-hearing caption readers. Captions carry the words but drop the tone.

## 2. What's done

| Area | Status | Proof |
|---|---|---|
| Backend: live session, audio clock, word alignment, recovery, replay | Done | 266 backend tests pass |
| ElevenLabs Scribe adapter | Done, but **never run against the real service** | Tested against a fake server only |
| Emotion model on the laptop | Done and **really running** | 64 ms per 2-second window on CPU; loads in about 5 s once warm; 2.4 GB RAM (`docs/live/benchmark.md`) |
| Frontend: controls, mic capture, transcript, history, replay | Done | 131 unit tests and 7 browser tests pass |
| Visuals: clouds, emotion radar, "current mix" bars, phrase inspector, settings (labels, color-blind palette, reduced motion) | Done | Screenshots in `docs/screenshots/` |
| "Words and voice differ" badge | Done | Demo lines tested: all 4 clear the bar, and none of the 13 replay lines false-flag |
| Tuning mode (`?tune=1`): live model scores from the mic, no transcript | Done | Ran against a test clip and got real scores |
| Session recorder: saves a live session's events, no audio, as a replay | Done | Not yet used on a real session |
| Research: 5 cited reports plus a fact-checked synthesis | Done | `docs/research/` |
| Pitch: 3-minute and 60-second talk track, judge Q&A, submission draft, interview script, video shot list | Done; needs today's data | `docs/pitch/` |
| Independent review: rubric scorecard, risks, honesty audit | Done; top fixes applied | `docs/REVIEW.md` |

**Honest status:** no real human voice has produced a cloud end to end yet. That needs the ElevenLabs key and the Scribe test below. All 7 replay files are hand-written examples, labeled "Synthetic example" on screen.

## 3. What still needs doing, in order

| # | Task | Why it matters | Suggested owner |
|---|---|---|---|
| 1 | **Get the ElevenLabs key.** In the ElevenLabs Discord, open `#coupon-codes`, click "Start Redemption", pick this event and enter your registration email. Apply the code, create an API key in the dashboard, and paste it into `backend/.env` as `ELEVENLABS_API_KEY=`. Never paste it into chat or commit it. | Nothing live works without it. | Roderich |
| 2 | **Run the Scribe test:** `.venv/bin/python scripts/smoke_scribe.py --wav <16 kHz mono WAV>`. Set `SCRIBE_TIMESTAMP_BASIS` in `backend/.env` to the result it prints. | **The biggest risk.** No clouds appear live until this is set. If the result is "segment", only the first sentence per connection gets clouds; tell Roderich right away. | Roderich |
| 3 | **Tune to the presenter's voice.** Run `scripts/demo_live.sh` and open `http://localhost:5173/?tune=1`. Say each demo line and check that angry, sad and happy read correctly and that neutral shows no cloud. | Thresholds aren't tuned on a human voice yet. | Presenter |
| 4 | **First full live run** on the main page: confirm clouds land on the right words and the badge fires on "Oh great, that's just perfect" said angrily. | This proves the demo works. | Presenter + 1 |
| 5 | **Record a real session as the backup replay.** Start with `RECORD_SESSION_EVENTS=shared/fixtures/replay_live_recorded.jsonl` and do one clean run. | An honest fallback if Wi-Fi or Scribe fails at the table. | Presenter |
| 6 | **Interview 2–3 attendees** with their consent, using `docs/pitch/USER_FEEDBACK.md`. Write down their real words in the table, including critical ones. | "User evidence" is 25 of the 100 points, and we have none first-hand yet. **Never invent feedback.** | Teammate |
| 7 | **Film a 60–90 s backup video** following `docs/pitch/BACKUP_VIDEO.md`. | The submission requires it. | Teammate |
| 8 | **Fill every `[FILL]`** in `docs/pitch/SUBMISSION.md`, `REHEARSAL.md` and `JUDGE_QA.md` with real results, then **submit before 4:00 PM**. | Required submission content. | Teammate |
| 9 | **Rehearse the talk track** (`docs/pitch/TALK_TRACK.md`) 3 times. The review's stronger opening and close are in `docs/REVIEW.md` §5. | Demo clarity is 10 points, and the room will be noisy. | Presenter |

A full minute-by-minute run sheet for 11 AM–4 PM is in `docs/REVIEW.md` §6.

## 4. Getting it running on your laptop (optional)

The live demo runs on Roderich's laptop. To run replay on yours:

```bash
git fetch && git checkout dev/hackathon-build
PYTHON_BIN=$(uv python find 3.11) scripts/setup.sh   # Python 3.11 venv + frontend deps
scripts/demo_replay.sh                                # open http://localhost:5173, pick Replay, press Start
```

The live model also needs `scripts/setup.sh --live` and the 1.95 GB weights from Hugging Face (`emotion2vec/emotion2vec_plus_large`), stored outside the repo. `docs/live/model-runtime.md` has the steps.

## 5. Ground rules for what we say to judges

- Say **"detected vocal cues"**, never "it reads your feelings." Scores are "relative model support", not confidence.
- Name **Google Expressive Captions** (Android) as prior work. Our difference is clouds anchored to exact words, plus the words-vs-voice badge.
- Any replay shown must be called a replay, and its on-screen label must be read as is.
- Every number in the pitch has a source in `docs/research/`. If we don't have a source, we don't say it.
- Hard questions with prepared answers (accuracy, privacy, "isn't emotion AI pseudoscience?", EU AI Act, Hume, Google) are in `docs/pitch/JUDGE_QA.md`.

## 6. Where everything is

| What | Where |
|---|---|
| Plan and decisions | `docs/PLAN.md` |
| Research and verified facts | `docs/research/SYNTHESIS.md` |
| Talk track, Q&A, submission draft | `docs/pitch/` |
| Review, risks, run sheet | `docs/REVIEW.md` |
| Screenshots | `docs/screenshots/` |
| Run commands | `README.md`, "Run the demo" section |
