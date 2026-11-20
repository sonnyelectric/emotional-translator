# Decision traceability

The decision wording below is carried over from §1.1 of the [TDD](TDD.md). The links point to the prompts that implement or verify each decision.

| # | Approved decision | Implementation prompts |
|---|---|---|
| 1 | Phrase-level emotion mapping with overlapping audio windows; size and saturation increase with visual intensity; opacity tracks confidence. | [B-04](prompts/B-04.md), [A-04](prompts/A-04.md), [C-04](prompts/C-04.md) |
| 2 | Clouds animate gently; emotion-specific silhouette (anger spiky, sadness rounded); greater confidence means greater opacity. | [C-02](prompts/C-02.md), [C-04](prompts/C-04.md) |
| 3 | Blend two emotions only if both strongly supported; neutral speech gets **no** cloud; continuous emotional speech can use multiple coordinated clouds. | [B-05](prompts/B-05.md), [A-04](prompts/A-04.md), [C-04](prompts/C-04.md) |
| 4 | Transcription appears immediately, emotion follows; approximately three newest sentences centered; older text and clouds persist in scrollable history. | [A-04](prompts/A-04.md), [C-02](prompts/C-02.md), [C-05](prompts/C-05.md) |
| 5 | Radar deferred, showing latest analyzed segment and relevant emotion categories; phrase hover/click can inspect scores; no timeline; speech-to-English translation future stretch. | [C-04](prompts/C-04.md), [C-06](prompts/C-06.md), [A-06](prompts/A-06.md) |
| 6 | 2-second analysis windows with 1-second hop; balance responsiveness and stability; hardware undecided. | [B-04](prompts/B-04.md), [B-06](prompts/B-06.md) |
| 7 | Moderate temporal smoothing; faint clouds for uncertain **non-neutral** evidence; smoothly morph changes; backend-configurable thresholds. | [B-05](prompts/B-05.md), [A-04](prompts/A-04.md), [C-04](prompts/C-04.md) |
| 8 | Browser audio goes to backend, which fans out to Scribe and local model; live microphone and saved-result replay; session memory only. | [C-03](prompts/C-03.md), [A-02](prompts/A-02.md), [A-03](prompts/A-03.md), [A-04](prompts/A-04.md) |
| 9 | Backend owns phrase alignment; subtly show provisional words; update and finalize clouds; versioned JSON contracts/fixtures/tests. | [A-01](prompts/A-01.md), [A-04](prompts/A-04.md), [C-01](prompts/C-01.md), [C-02](prompts/C-02.md) |
| 10 | A backend/orchestration, B audio/AI, C frontend; small numbered AI-agent prompts with acceptance tests; integrate each milestone; first vertical slice uses saved events. | [Handoffs](HANDOFFS.md), [A-02](prompts/A-02.md), [B-02](prompts/B-02.md), [C-02](prompts/C-02.md) |
| 11 | One local monorepo, local frontend/backend, offline replay without keys or weights plus documented live setup, local install scripts. | [A-01](prompts/A-01.md), [A-02](prompts/A-02.md), [C-01](prompts/C-01.md), [A-06](prompts/A-06.md) |
| 12 | Approximate 3-second post-phrase emotion annotation target; model failure → text-only warning; Scribe failure → retry and preserve transcript; automated contract/unit + manual live checklist. | [A-05](prompts/A-05.md), [B-06](prompts/B-06.md), [C-05](prompts/C-05.md) |
| 13 | Proposed distinct emotion colors/shapes; coordinated multiline clouds; gradient mixed-emotion blend; shape plus optional inspectable labels. | [C-02](prompts/C-02.md), [C-04](prompts/C-04.md), [C-05](prompts/C-05.md) |
| 14 | Centered dark navy transcript; start/pause/resume/stop/reset/live-replay; collapsible history below; minimal idle prompt. | [C-02](prompts/C-02.md), [C-03](prompts/C-03.md), [C-05](prompts/C-05.md) |
| 15 | Judges see live microphone first, replay backup; scenario-based testing; cautious vocal-cue wording; replay fixtures contain text/timestamps/scores/annotations, no audio required. | [B-06](prompts/B-06.md), [B-07](prompts/B-07.md), [A-06](prompts/A-06.md) |
| 16 | Scribe `commit_strategy=vad`; prioritize genuine live transcription and emotion visualization above all presentation extras. | [B-03](prompts/B-03.md), [A-04](prompts/A-04.md), [A-06](prompts/A-06.md) |

## Engineering choices for the initial contract freeze

| Choice | How to apply it |
|---|---|
| Replay delivery | Serve the manifest and original JSONL from two local HTTP routes. The frontend schedules saved events by `issued_at_ms` and uses the live reducer. The fixtures carry `source: saved_result` with `provenance: synthetic_example`. [Protocol](PROTOCOL.md#replay-http) |
| Audio acknowledgement and reset | Put all three negotiated PCM constants on every live `listening` status. Stop closes the live transport and keeps the UI history. Reset on an open idle or terminal control socket starts a new session. After transport closure the UI can reset locally and the next start gets a new server ID. [Protocol](PROTOCOL.md#session-lifecycle) |
| Draft suppression | Add `emotion.retracted` before the v1 freeze. Higher-revision retraction hides a draft when eligible evidence disappears, including a shift to neutral. It preserves the annotation identity until finalization. [Protocol](PROTOCOL.md#annotations) |
| Time and score checks | Use JSON Schema for payload structure and explicit semantic checks for cross-field and cross-event rules. Keep `score_kind` in backend diagnostics. The fixture vectors use probability-like normalization and do not represent observed model output. [Protocol](PROTOCOL.md#validation-order) · [Pipeline](PIPELINE.md#scores-and-visual-classification) |
| Initial tuning and machine versions | Use the TDD defaults and the templates as starting values. A and B record tested runtime versions and tune with the judging laptop. Treat provider timestamps, scoring shape, actual performance, and license as evidence from live preflight. [Setup](SETUP.md) · [Release gates](ACCEPTANCE.md) |
| Inspector sequence | Implement phrase focus, hover, and click in C-04 after the core clouds. Keep the latest-segment radar post-core and English translation as future work. [C-04](prompts/C-04.md) |

A publishes the schemas at G0. To revise the contract after G0, open a decision PR with the migration, fixture changes, and signoff from B and C. Adopt an explicit version per TDD §5.3 and keep existing v1 field meanings stable. If provider evidence conflicts with the assumed pipeline, bring that evidence to A before changing the interface.
