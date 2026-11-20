# Local protocol v1.0

The [TDD](TDD.md) supplies product behavior. This document and the [Draft 2020-12 schemas](../shared/schemas/v1/server-event.schema.json) specify the implementable wire contract. See [fixtures](../shared/fixtures/README.md) for sample frames and a shared test corpus. A owns changes.

## Routes and transport

| Operation | Local URL and response |
|---|---|
| UI | `http://localhost:5173` |
| Liveness | `GET http://127.0.0.1:8000/healthz` → HTTP 200 JSON `{"status":"ok","schema_version":"1.0"}`. It checks only whether the local process can respond. |
| Live session | `ws://127.0.0.1:8000/ws/v1/session`. Text frames are JSON commands inbound and events outbound. Binary frames are browser-to-backend raw PCM. |
| Replay catalog | `GET http://127.0.0.1:8000/api/v1/replay/manifest` → HTTP 200 JSON conforming to `replay-manifest.schema.json`. |
| Replay fixture | `GET http://127.0.0.1:8000/api/v1/replay/{fixture_id}` → HTTP 200 UTF-8 JSONL with `Content-Type: application/x-ndjson`. |

A binds the backend to IPv4 loopback and explicitly allows frontend origin `http://localhost:5173` for WebSocket and replay HTTP. Reject a disallowed WebSocket origin before accepting the upgrade. C derives the WebSocket URL from the configured local backend HTTP origin and uses the same origin for replay. Endpoints stay local. The browser contacts only the local backend after deliberate mic activation. Upstream credentials are available to B's adapter from backend configuration.

### Binary PCM

Each frame is raw signed sixteen-bit little-endian samples with no header. The channel count is one and the rate is 16,000 Hz. Frame size is 640–3,200 bytes inclusive and even, equivalent to 20–100 ms. Default to 40 ms (640 samples, 1,280 bytes), retaining resampler phase across buffers. Clamp float samples to [-1, 1], use the full negative and positive PCM range, and write low byte first. Drop a final remainder shorter than 20 ms on Stop or Pause. Send all complete queued audio before the Stop/Pause control in WebSocket order.

A advances canonical `sample_offset` by `bytes / 2` only for accepted frames. Sizes alone cannot establish the actual device rate. C validates conversion on 44.1 kHz and 48 kHz inputs, including downmix, continuity, quantization and long-run sample count. A bounds server ingest and rejects an invalid frame without advancing time. Capture and relay backlog are bounded. If browser congestion forces abandonment of samples, pause/stop with a warning to avoid silently splicing audio. For upstream overflow/reconnect use a new epoch. [Backend clock and epochs](PIPELINE.md#clock-epochs-and-fan-out)

### Browser command messages

Use [client-command.schema.json](../shared/schemas/v1/client-command.schema.json); commands have only `schema_version`, `type`, and `payload`.

| Command | Payload | Legal input state | Ack or effect |
|---|---|---|---|
| `session.start` | `{"mode":"live"}` | Idle or unbound | New server session, `connecting` then `listening` or `error`. An already bound idle session established by Reset is used for its first Start. |
| `session.pause` | `{}` | Listening | Stop capture and forwarding. A acknowledges `paused`. |
| `session.resume` | `{}` | Paused | Connect a new upstream epoch, then acknowledge `listening`. |
| `session.stop` | `{}` | Connecting, listening, or paused | Enter `stopping`, allow bounded drain, send `stopped`, then close with code 1000. |
| `session.reset` | `{}` | Unbound, idle, stopped, or error if transport is still open | Clear server state. Send a `session.reset` event under a new ID, then `session.status` with `idle`. |

Reject known malformed commands, with `INVALID_COMMAND` if a session is bound. For known commands sent in an unsuitable state, use `INVALID_STATE`. Invalid/forbidden binary frames are dropped with `INVALID_AUDIO_FRAME` or `AUDIO_NOT_ACCEPTED` if bound. With no bound session, use policy close 1008 for invalid known input or audio before initialization. Unknown v1 command types with well-formed common fields are ignored and warned in developer diagnostics. An unsupported version fails boundary validation. Never create a live provider connection on receipt of binary, reset, an unknown command, or a replay request.

### Session lifecycle

- After permission is granted, C opens the WebSocket and starts live. Gate AudioWorklet sending on explicit live `listening` and the matching `sample_rate_hz:16000`, `channels:1`, `sample_format:"s16le"`. Permission denial stays inside the frontend and leaves prior committed data visible until reset.
- Live states are `idle → connecting → listening ↔ paused`, `stopping → stopped`, and `error`. Resume briefly returns to `connecting` before sending again. A new upstream Scribe connection can reconnect under the same browser session with new audio epoch and `scribe:"reconnecting"`. A browser socket reconnect starts a new session ID. Preserve prior committed content on a browser disconnect pending explicit reset.
- Pause suspends browser forwarding, fences outstanding cloud work for the paused epoch and preserves visible clouds. Resume opens a fresh upstream epoch. Stop releases browser tracks immediately, drains server results for a bounded interval, closes live resources, and leaves committed content and clouds visible. A fatal error sends `session.error`, then status `error`, then ends the live transport. Clean up tasks on disconnect.
- Clear transcript, provisional text, scores, queues, clocks, epochs, errors and history on Reset. Open transport reset is acknowledged with the new server ID and starts `seq=1`, `issued_at_ms=0`. After the live transport is closed, the UI can reset locally. Its next live start receives a fresh server ID. Ignore callbacks from superseded sockets or replay jobs.
- Keep live and replay exclusive. Initial idle can switch modes. Following a run, use Stop where applicable and then Reset before switching. Reset is unavailable during active recording. Replay controls such as Pause and Reset act locally.

### Server envelope and events

The envelope has `schema_version:"1.0"`, `type`, `session_id`, `seq`, `issued_at_ms`, and `payload`. `seq` starts at 1 per session and increases on each emission. `issued_at_ms` is nondecreasing session elapsed time from a monotonic clock, rounded to whole milliseconds. Multiple events may share a clock tick. Sort by `(issued_at_ms, seq)`; gaps in sequence are accepted by a client although A normally emits consecutively. IDs are opaque strings and stable for their entity lifetime. Interval fields are half-open audio milliseconds on the captured-sample timeline, possibly fractional. Word-anchor IDs on an annotation are inclusive.

| Event | Payload and reducer effect |
|---|---|
| `session.status` | `state, mode, scribe, emotion_model, detail`. Detail is a nullable short string. Live `listening` also requires the three flat PCM fields. Replay statuses use `mode:"replay"`, both services `not_required`, and carry no PCM fields. |
| `transcript.partial` | `partial_id, text, language_code`. Replace the pending partial in place. A partial ID remains stable until its matching commit. The empty string clears stale provisional text when an epoch is lost without completing it. |
| `transcript.committed` | `segment_id, text, timing_state:"pending", language_code`. Append stable text once and clear its provisional state. Serialize the commit ahead of any next partial in the same upstream stream. |
| `transcript.timed` | `segment_id, language_code, words`. Replace timing projection of an existing commit. Leave newer provisional text alone. A word has `word_id, text, start_ms, end_ms`. Preserve provider punctuation and use joined whitespace. Optional `text`: present only when the provider's timed words differ from the committed text beyond case, punctuation or spacing; it replaces the segment text, and the joined words must equal it. |
| `emotion.updated` | Render-ready draft with `annotation_id, revision, segment_id, start_word_id, end_word_id, start_ms, end_ms, state:"draft", primary, secondary, scores, support, visual_intensity, opacity, shape, color, blend`. Details below. |
| `emotion.retracted` | `annotation_id, revision`. Hide a previously visible draft and retain its identity and revision. |
| `emotion.finalized` | `annotation_id, revision`. Freeze the current visible or retracted state. |
| `alignment.warning` | `segment_id, code, message`. Keep prior text. Used for missing, ambiguous or mismatched timing evidence. |
| `session.warning` | `code, message, recoverable:true`. Continue the allowed parts of the session. |
| `session.error` | `code, message, recoverable:false`. Fatal live or setup failure. Keep prior committed data if present. |
| `session.reset` | Empty object. Clear reducer state and bind the new server ID only as the acknowledged reply to Reset. |

Use nullable strings for language codes and treat them as descriptive. Keep warnings safe for display and logs. Known warning codes include `SCRIBE_RECONNECTING`, `EMOTION_MODEL_UNAVAILABLE`, `EMOTION_INFERENCE_SLOW`, `ALIGNMENT_TIMESTAMPS_MISSING`, and `ALIGNMENT_TIMESTAMP_MISMATCH`. Fatal setup codes include `LIVE_NOT_CONFIGURED`, `SCRIBE_AUTH`, `SCRIBE_QUOTA`, `SCRIBE_TERMS`, and `SCRIBE_RETRY_EXHAUSTED`. Display the supplied message for other recognized-code formats. Keep provider details, credentials, and audio out of user-facing error payloads.

### Annotations

| Primary | `shape` | `color` |
|---|---|---|
| `angry` | `jagged` | `#DC4545` |
| `sad` | `rounded` | `#478CD4` |
| `happy` | `radial` | `#EDB94B` |
| `fearful` | `trembling` | `#9975D8` |
| `surprised` | `burst` | `#EF9858` |
| `disgusted` | `wavy` | `#68A876` |

All nine model labels occur in `scores`. Visible primary/secondary categories come from the table. Neutral, other, and unknown evidence can suppress a cloud. `support` is the primary relative score. `visual_intensity` drives size and saturation. `opacity` is a positive visual parameter in (0, 1] and is monotonic with relative support under the configured mapping. With a single category, `secondary` and `blend` are both null. For two categories, `blend.secondary` equals `secondary` and `blend.weight` is the secondary color fraction in (0, .5]. A chooses which two categories meet the backend gate using B's score classifier. The shape and color fields refer to the primary.

The first visible version of an ID has revision 1. Each Update, Retract, or Finalize then has a strictly larger revision. Word bounds and segment are stable within an annotation ID. Retract is legal only while visible and draft. A higher-revision Update may restore a retracted draft with the same anchors before finalization. If A freezes a retracted draft, it stays hidden. Finalization contains no replacement geometry. Emit a final Update first if geometry changed. Ignore any mutation after Finalize, regardless of its revision.

### Validation order

1. Limit input size, decode the expected frame type, parse strict JSON and recursively reject non-finite numeric values. Test nonstandard NaN and Infinity tokens and overflowing exponent values. Validate the common envelope and version. For unknown v1 event types with valid common envelope, ignore the event, record a developer warning, and advance the seen sequence for that bound session.
2. Validate known structural shapes against the local Draft 2020-12 registry. Python uses Pydantic 2 plus a JSON Schema parity test. C uses generated or checked-equivalent TypeScript types plus a runtime Draft 2020-12 validator. The schema `$id` URLs are identifiers. Register the local files and resolve references from disk/build assets without fetching URLs.
3. Check semantic constraints. Establish session scope only from the first expected status on the active transport/replay or a pending Reset acknowledgement. Discard events from prior transport generations/session IDs and ignore duplicate or older sequence. Within the session reject a decreasing `issued_at_ms`; reject duplicate committed IDs, timing a nonexistent or already timed segment, duplicate word IDs, out-of-order word starts or ends, nonpositive intervals, and a tested normalized-text mismatch. Exact or NFC plus collapsed-whitespace text reconciliation is allowed. Keep case and punctuation. A also rejects Scribe intervals outside sent audio in that epoch. Annotation anchor IDs must occur in ordered contiguous timed words in the referenced segment. Verify interval equality to the outer words, stable anchors for revisions, secondary agreement, `support` equality to primary score to 1e-4, and legal draft/final state. Probability-like vectors sum to 1 within 1e-3 in B's adapter checks and all included score fixtures. Comparable non-probability vectors may have a different sum.
4. For invalid known live events C ignores the event, logs a developer diagnostic, and keeps the last valid state. A validates before emitting known events. Replay prevalidates the whole stream before changing playback state. Fail replay on known invalid, cross-session, or unordered data. A valid unknown event type may be skipped after header/sequence validation. [Invalid examples](../shared/fixtures/invalid/cases.json)

## Replay HTTP

Read only from the local shared manifest and exact fixture files it names. Confirm unique IDs and filenames, a present default ID, `file = id + ".jsonl"`, and duration equal to last minus first `issued_at_ms`. Treat each fixture as one session, require an opening replay `listening` status and a terminal replay `stopped` status, and validate in order. Resolve IDs via a manifest map. Return 404 with `REPLAY_NOT_FOUND` for an unknown fixture. Return 422 with `REPLAY_INVALID` if an authorized-by-manifest fixture or the manifest fails to parse or validate, with a safe error body. Serve successful JSONL without reissuing event timestamps and with `Cache-Control: no-store`.

The frontend loads and validates using local HTTP, then uses relative `issued_at_ms` time to schedule events into the same reducer as live. A local fake clock should produce the same ordering and output on repeated runs. Pause preserves the scheduling cursor and remaining delay. Stop cancels timers and keeps rendered content. Reset clears local state and cancels pending fetches and callbacks. Display `REPLAY` and saved-result provenance from the manifest. The replay scheduler owns `replay_idle`, `replay_playing`, `replay_paused`, and `replay_done`. Recorded statuses and warnings are display inputs. The replay view does not connect to microphone, WebSocket, Scribe, or model. In replay-only launch, the process does not import the optional model runtime.
