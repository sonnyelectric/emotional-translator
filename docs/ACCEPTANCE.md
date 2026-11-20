# Milestones and release gates

A records a commit SHA, reviewer, environment and outcome for every gate. Pass requires observed evidence on the relevant checkout. Use `blocked` for missing access or dependencies and `failed` for a measured mismatch. Unit and contract checks run without provider access. Exact prompt-level tests live in [the schedule](DEPENDENCIES.md#exact-prerequisites-and-handoffs).

| Milestone | Implementation | Integration checkpoint | Handoff |
|---|---|---|---|
| M0 Foundation | A-01, B-01, C-01 | G0 schema parity on the same fixture files. Independently collect platform readiness. | A shares freeze SHA. C sends TS evidence. B sends hardware/cache/runtime report. |
| M1 Vertical slice | A-02, B-02, C-02 | G1 offline fixture through real local HTTP and browser. B's fake is verified separately for later orchestration. | A and C send matching demo observations. B sends fake score and window behavior. |
| M2 Adapters and capture | A-03, B-03, B-04, C-03 | Verify microphone PCM reaches local backend and actual Scribe partial+committed events in a live smoke as soon as its adapter is available. B proves G3 real window scoring independently. | C reports measured output rate and controls. B sends provider timestamp origin evidence and pin/cache requirements. A sends accepted-frame, epoch and relay semantics. |
| M3 Live alignment | A-04, B-05, C-04 | G2 timed live transcript for 2 minutes, then G4 live phrase clouds with model and browser. | A shares reconciled clock and live flow evidence. B shares bounded queue/threshold results. C shares phrase, morph and wrap observations. |
| M4 Hardening | A-05, B-06, C-05 | G5 fault behavior, 3-minute target-laptop benchmark, and keyless replay regression. | A records failure recovery and result. B sends measured latency and resource evidence. C sends pause/reset, responsive and reduced-motion checks. |
| M5 Submission | A-06, B-07, C-06 | G6 clean-checkout setup, judge rehearsal and reproducibility review. | A tags the reviewed SHA after collecting B's runtime instructions and C's demo notes. |

## G0 · Shared contracts

- Python checks the Draft 2020-12 resources offline, validates the valid corpus, and rejects the schema and parser negatives. Known event shapes are checked with Pydantic 2 and compared against the JSON Schema results. TypeScript compiles with the same sample contracts and runs the equivalent runtime validation. A compares parser/structural results. Behavioral stream cases land in A-02/A-04 and C-02.
- A verifies versions, strict domains, local reference resolution, fixtures, and the generated or checked-equivalent types on the same checkout. B signs the in-process ports. Freeze the review SHA and report any service behavior still to be verified.
- Evidence commands after the prompts land: `.venv/bin/python -m pytest backend/tests/core/test_contracts.py -q`, `npm --prefix frontend run test:contract`, `npm --prefix frontend run typecheck`.

## G1 · Offline vertical slice

Prerequisites are G0, A-02, B-02, and C-02. Test after completing local dependency installation. Disable external networking, leave loopback available, use an environment with no ElevenLabs key and no model weights, and start `bash scripts/start_backend.sh --replay` and `bash scripts/start_frontend.sh`. Run `bash scripts/verify_replay.sh` and `E2E_REAL_REPLAY=1 npm --prefix frontend run test:e2e -- --grep G1`. In the browser choose Replay then Start. The app should request the catalog and default fixture over local HTTP.

| Stimulus | Pass condition |
|---|---|
| Playback starts | `REPLAY` is visible with saved/synthetic provenance. No media permission, browser WebSocket, external requests or model import. Offline playback completes in ~18.6 s at 1×. |
| `replay_demo` seq 2–5 | Seq 3 replaces seq 2 provisional text. Seq 4 appends one stable neutral sentence and clears partial text. Seq 5 adds word IDs with no cloud. |
| Seq 7–12 | The second commit renders plain until seq 9. A red jagged cloud starts at word 3 of `seg-2` and covers “and I am tired of being ignored.” Seq 10 updates the same `a-seg-2` with greater opacity and visual intensity. Seq 12 freezes revision 3. The newer partial from seq 11 stays visible. |
| Seq 14–18 | Blue rounded cloud for `a-seg-3` covers the long sad sentence. At 1280×720 or constrained transcript width it spans at least two coordinated line shapes, with readable text above them. Resize while playing or after stop and verify the bounds follow the same words. |
| Seq 19–26 | `seg-4` remains neutral and plain. `seg-5` has a gold cloud. Latest three completed sentences `seg-3`–`seg-5` occupy center. Expand history and confirm `seg-1` and `seg-2` and the finalized red annotation persist. Stop leaves the committed display visible. Also unit-test sentence selection with multiple sentences in one commit and one sentence across commits. |
| Replay Pause/Resume | Pause between known events. The cursor and visible text stay still. Resume preserves remaining relative delay and order. Reset cancels pending events and clears center/history/annotation state. Replay again and compare sequences. |
| Other fixtures | In delayed timing, seq 5 applies to `seg-1` and keeps the newer `p-2`. Mixed replay shows a two-color gradient. Retraction replay fades the faint cloud away and finalizes it hidden. Pure neutral never draws a cloud. |
| Negative stream | Known malformed replay yields a useful error before state mutation. A stale revision or event after finalization leaves a prior annotation unchanged in live reducer tests. |

A and C jointly record the replay request URLs, fixture ID, successful commands, expected ID/revision samples, and browser evidence on the same commit. B reports that the isolated fake implemented the scored-window contract using synthetic vectors. The replay runtime consumes saved events directly.

## G2 · Real Scribe transcript

On a laptop with permission and an authorized account, select Live and speak continuously with natural pauses for at least two minutes. Observe actual Scribe partial, commit, and timed event shapes and validate timestamp basis for this account/runtime. Confirm no duplicate segments or words from repeated events, a delayed timed patch reaches the correct earlier commit, and mapped words stay within accepted captured samples. Speak the same short sentence twice and verify both genuine commits remain. If timing is missing or mismatched, preserve committed text and record the alignment warning. Share scrubbed ordering/types, measured durations and captured-audio epoch boundaries.

## G3 · Real Large model

On the candidate judging laptop explicitly load `iic/emotion2vec_plus_large` as the sole emotion model. Verify actual `generate` output, normalized nine-label scores, score-kind semantics, and 32,000 samples per window with 16,000 samples hop. Record loaded model identifier, runtime pins, accelerator/CPU, load time, peak RAM and per-window p50/p95. A label-only or unsupported result blocks G3. Use [B-04](prompts/B-04.md) and [the port contract](PIPELINE.md#windowing-and-backpressure).

## G4 · Real live phrase clouds

On the integrated checkout with G2 and G3 evidence, start from an empty Live session. Speak at least three emotional scenarios and one neutral one as listed below. Verify that mic samples actually reach Scribe and the locally loaded Large classifier, that emitted annotations reference actual timed words, and that the UI displays phrase-aligned clouds corresponding to eligible live scores. A verifies models and events through timing-only instrumentation. Record coverage, missing/delayed scores, unintended detections and the observed result in each scenario. Scripted delivery is an expectation for testing. Report actual model output. Readable positioning, neutral suppression, and genuine live service/worker paths are required to pass. Follow with draft revision/finalization and history checks.

## G5 · Resilience and target hardware

| Test | Required observed result |
|---|---|
| Permission denied | Clear local instructions and retry. No audio forwarding. |
| Bad PCM or out-of-state commands | Bad frames or commands rejected. Clock, session, and prior transcript remain consistent. |
| Recoverable Scribe outage | Bounded jittered retry. New upstream epoch, old text and cloud positions preserved. No guessing, replay of old mic chunks, or duplicate commits. |
| Permanent auth, quota or terms error | Fail visibly and stop retrying. Saved replay remains accessible after reset. |
| Delayed/absent timestamp and old work | Stable text without invented word timing. New partial untouched. Finalized history unchanged even when a late score arrives. |
| Model load, score or worker failure | Warning and text-only for new speech while Scribe keeps working. Previous clouds preserved. |
| Slow model | Oldest pending windows dropped under load. At most two pending by default. No event-loop or Scribe starvation. |
| Stop/Pause/Resume/Reset | Tracks and work cleaned up appropriately, resume epoch correct, no phantom cloud after pause/reset, and history retained until reset. |
| UI regressions | Test 1280×720, 1440×900 and a narrower layout. Keyboard focus, touch input and reduced motion work. A text-only state remains readable. |
| Replay regression | Repeat G1 without external network/credentials/weights. |

B runs the standalone target-laptop benchmark and the integrated three-minute live run. Capture model load and peak memory, queue depth and drops, sample counts, browser stability, p50/p95 inference and end-to-end timings, and long continuous speech behavior. Compare measured phrase-end-to-first-cloud with the approximate 3-second target. Report whether the goal was met, and report misses explicitly. A preserves that evidence in the submission.

## G6 · Reproducible submission

From a clean copy of the selected SHA, verify documented setup, offline G1 and the local live launch on the judging laptop. Include exact environment and dependency pins, how to provide your own key and download the tested Large weights, measured latencies and known limits, fixture provenance, and clear replay steps. Rehearse Live first with actual audio and preserve an explicit, labeled Replay backup. Include video or live demonstration instructions as applicable. Sign off G0–G5 evidence and unresolved failures. Use the [judge runbook](DEMO.md).

## Manual live scenario matrix

| Scenario | Expected behavior to check |
|---|---|
| Neutral, conversational speech | Immediate words, then stable text. No category cloud when neutral leads. |
| Clearly angry delivery | Jagged red cloud on the aligned phrase when anger is sufficiently supported. |
| Soft sad delivery | Rounded blue cloud when sadness is sufficiently supported. |
| Joyful delivery | Distinct gold cloud when happiness is sufficiently supported. |
| Anger into sadness | Visual changes are smooth and track the correct phrase anchors. |
| Two strong categories | One coordinated gradient cloud when both pass the backend gate. Use saved mixed fixture for deterministic rendering verification. |
| Long continuous passage | Partial and final text keep arriving. Record any VAD timing delay, verify no speculative cloud. |
| Long emotional phrase | Multiple coordinated line shapes with readable words. |
| Uncertain non-neutral | Faint cloud and accessible score caveat. Marker remains modest and may retract if evidence becomes neutral. |
| Scribe drop, model failure, or offline replay | Follow the dedicated G5 checks and distinguish the visible mode in any recording. |
