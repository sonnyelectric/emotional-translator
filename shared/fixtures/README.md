# Shared JSON fixtures

These inputs are synthetic. They use saved-result playback semantics and serve as deterministic development scenarios. The eventual recorded-result fixture, if the team captures permitted live output later, must carry observed provenance. No audio is required for this kit.

| File | Scenario and expected use |
|---|---|
| [manifest.json](manifest.json) | Data source, default fixture, durations and provenance. Validate with the replay manifest schema. |
| [replay_demo.jsonl](replay_demo.jsonl) | Default G1 fixture. Replacing partial text, committed then timed text, red cloud revision, long blue wrap, a second neutral sentence, then golden cloud and history. |
| [replay_anger_sad.jsonl](replay_anger_sad.jsonl) | Two adjacent phrases in one segment and a draft color/shape morph on the second phrase. |
| [replay_neutral.jsonl](replay_neutral.jsonl) | Timed neutral text with zero annotation events. |
| [replay_mixed.jsonl](replay_mixed.jsonl) | Strong primary and secondary categories within one gradient. |
| [replay_delayed_timing.jsonl](replay_delayed_timing.jsonl) | Timing for an earlier segment arrives after a new partial. A later unresolved segment stays plain. |
| [replay_failures.jsonl](replay_failures.jsonl) | Shows saved model and Scribe warnings while preserving transcript. It still plays in Replay. |
| [replay_retraction.jsonl](replay_retraction.jsonl) | A faint draft appears, is retracted, and is frozen out of view. |
| [client_commands.json](client_commands.json) | Each element conforms to the browser command schema. |
| [server_examples.json](server_examples.json) | Each element conforms to the server event schema. Illustrates one live session, a separately scoped Reset, and a separately scoped fatal setup failure. |
| [http_examples.json](http_examples.json) | Liveness and replay error bodies. |
| [pipeline_examples.json](pipeline_examples.json) | Three fake scored windows, standalone classifier cases, and binary frame length cases. The windows individually conform to `model-window.schema.json`. |
| [invalid/cases.json](invalid/cases.json) | Shared parser, schema, and stream-level negative cases. |

JSONL contains one server envelope per UTF-8 line, including any status events. The file ends with a newline. For negative cases with `layer: parse`, pass the `raw` string to the strict parser. For `layer: schema`, load the named entry point and reject `instance`. For `layer: stream`, apply the ordered `prefix` from a fresh state then test the one `event` and the specified outcome. Rejected live semantic events must not alter transcript/cloud state. The stale-sequence, different-session, and unknown-type cases distinguish the expected ignored paths. Replay validation turns invalid known events and violations of single-session ordering into fixture errors. [Protocol](../../docs/PROTOCOL.md)
