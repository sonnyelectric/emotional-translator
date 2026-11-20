# Scribe v3 Live preflight (B-03)

Status: adapter and fake-upstream tests done. **No live check has run** (no API key at build time). Everything under "Unverified" must be settled with `scripts/smoke_scribe.py` at the event.

## Sources (fetched 2026-11-20)

- API reference: https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime (query params, `input_audio_chunk`, error schemas `{message_type, error}`, `warning{warning}`)
- Event reference: https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/event-reference (event names, ordering, error names; gives no JSON field lists)
- Commit strategies: https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/transcripts-and-commit-strategies
- Word-item shape (`words[].text/start/end/type`, seconds, `type` = word|spacing) comes from R1 and docs/research/SYNTHESIS.md, which cite the API reference. The summarizing fetch tonight did not re-show it, so treat it as documented-but-recheck.

## What the adapter sends

URL `wss://api.elevenlabs.io/v1/speech-to-text/realtime`, header `xi-api-key`, query `model_id=scribe_v3_live` (default is `scribe_v2_realtime`), `audio_format=pcm_16000`, `commit_strategy=vad`, `vad_silence_threshold_secs=<config>`, `include_timestamps=true`. Chunks: `{"message_type":"input_audio_chunk","audio_base_64":...,"commit":false,"sample_rate":16000}`. `previous_text` is never sent. Never combine `filter_background_audio` with timestamps (invalid_request).

VAD parameter: the spec lists `vad_silence_threshold_secs` as a double with no documented default or range. R1 reports 0.192-3.0 s from the Commit page. Config default 0.65 s; confirm the server accepts it (no `invalid_request`).

## Message mapping

| Provider message | Notice |
|---|---|
| `partial_transcript{text}` | `partial` (empty or unchanged text dropped as keepalive) |
| `committed_transcript{text}` | `commit` (`provider_commit_key=None`: no key is documented) |
| `committed_transcript_with_timestamps{text,language_code,words[]}` | `timed`; spacing and other non-`word` items dropped; items missing numeric start/end skipped, never invented; `start`/`end` seconds -> `round(s*16000)` samples; `timestamp_basis="unknown"`, `segment_origin_samples=None` |
| `session_started`, `warning`, diarization etc. | ignored |
| upstream close not initiated by us | `transient_error` code `upstream_closed` |

Error classification (all 14 documented types, tested):
- fatal: `auth_error`, `quota_exceeded`, `unaccepted_terms`, `invalid_request`. The stream ends after a fatal notice.
- transient: `error`, `input_error`, `commit_throttled`, `rate_limited`, `queue_overflow`, `resource_exhausted`, `session_time_limit_exceeded`, `chunk_size_exceeded`, `insufficient_audio_activity`, `transcriber_error`. A should retry `input_error`, `commit_throttled`, `chunk_size_exceeded` once, then stop (they suggest our bug). The docs give no retry semantics; this split is judgment.
- Handshake failures: `open()` raises `ScribeSetupError(code, fatal)`; HTTP 401/402/403 fatal, others transient. Provider error text is never forwarded.

## Unverified (smoke test must answer)

1. Timestamp basis: connection- vs segment-relative. Documented nowhere. Smoke script prepends lead silence and reports its verdict; paste the output below.
2. Timed event follows each `committed_transcript` in order for back-to-back short commits, and typical delay.
3. Whether `vad_silence_threshold_secs=0.65` is accepted and behaves sensibly.
4. Actual field names on `partial_transcript`/`committed_transcript` (event page names only `text`).
5. Account has service access, quota, accepted terms.
6. Millisecond-level precision of `start`/`end`.

## Smoke command

```
.venv/bin/python scripts/smoke_scribe.py --wav /absolute/path/consented-16k-mono.wav
```
Needs `ELEVENLABS_API_KEY` in `backend/.env`; refuses to run without it. Streams about 15 s at live pace (plus 3 s lead silence, 2.5 s tail) on two fresh connections and prints scrubbed output. Use audio with two phrases separated by a pause of 1.5 s or more. Raw PCM: `... --stdin-pcm`. Convert audio first with `ffmpeg -i in.wav -ac 1 -ar 16000 -sample_fmt s16 out.wav`.

## Observations (fill in at the event)

- Basis verdict:
- Units/precision:
- Event order and delays:
- Second fresh stream:
- Fields seen:
