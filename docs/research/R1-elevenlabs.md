# R1: ElevenLabs research (accessed 2026-11-20)

Method: official docs fetched through a summarizing fetcher (small model), so exact wording may be paraphrased. Where I could not verify, it says "unverified".

Primary sources (all accessed 2026-11-20):
- [API ref] https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime
- [Events] https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/event-reference
- [Commit] https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/transcripts-and-commit-strategies
- [Lang] https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/language-options
- [Models] https://elevenlabs.io/docs/overview/models.md
- [STT cap] https://elevenlabs.io/docs/overview/capabilities/speech-to-text.md
- [Server] https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/server-side-streaming
- [Client] https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/client-side-streaming
- [Pricing] https://elevenlabs.io/pricing/api
- [PyPI] https://pypi.org/pypi/elevenlabs/json
- [Guide] Hacker Guide Google Doc (read via Google Docs connector)

## 1. Scribe v3 Live realtime WebSocket

**Endpoint** `wss://api.elevenlabs.io/v1/speech-to-text/realtime` [API ref][Models]. Regional hosts also listed (api.us, api.eu.residency, api.in.residency, api.sg.residency) [API ref].

**Auth** either header `xi-api-key`, or query param `token` = single-use token from the tokens endpoint (for client-side use) [API ref]. Token expires after 15 minutes [Client]. Server-side relay with the API key matches the TDD.

**Query params** [API ref] (defaults as listed there):
| param | default | notes |
|---|---|---|
| model_id | `scribe_v2_realtime` | must pass `scribe_v3_live` explicitly |
| audio_format | `pcm_16000` | also pcm_8000/22050/24000/44100/48000, ulaw_8000 |
| language_code | none | ISO 639-1/639-3; restricts recognition |
| secondary_languages | none | repeat param per language |
| commit_strategy | `manual` | `manual`, `vad`, `turn_prediction` (turn_prediction only on v3 live; SDK enums lack it) [Commit] |
| vad_silence_threshold_secs | none documented | range 0.192-3.0 s on the API; JS/React SDKs accept only 0.3-3.0 [Commit] |
| vad_threshold | none (0.15 if filter_background_audio=true) | |
| min_speech_duration_ms, min_silence_duration_ms | none documented | examples use 100 |
| include_timestamps | false | required for committed_transcript_with_timestamps |
| include_language_detection | false | also triggers the timestamped event [Events] |
| keyterms | none | up to 50 terms, 20 chars each in realtime [STT cap] |
| multilang_mode | false | v3 live only; SDKs unsupported [Lang] |
| diarize, entity_detection, entity_redaction, transcript_edit, no_verbatim, filter_background_audio, keepalive_interval_ms (500-10000), enable_logging | various | |

Gotcha: `filter_background_audio=true` + `include_timestamps` => `invalid_request` and close [Commit]. `no_verbatim` is not available on v3 live [Models].

**Client message** `input_audio_chunk` [API ref]:
`{"message_type":"input_audio_chunk","audio_base_64":"...","commit":false,"sample_rate":16000,"previous_text":"(first chunk only)"}`. All four main fields required. Matches TDD.

**Server messages** [API ref][Events]:
- `session_started`: `{message_type, session_id, config{sample_rate, audio_format, commit_strategy, vad_*..., model_id, include_timestamps, ...}}`
- `partial_transcript`: `{message_type, text}`; later partials replace earlier. Also used as keepalive (empty or repeated text). `language_code` present only with include_language_detection; null until ~4 words [Events]. With turn_prediction each partial carries `turn_probability` [Commit].
- `committed_transcript`: `{message_type, text}` (plus zero-based `segment_index` when diarize=true) [Events].
- `committed_transcript_with_timestamps`: `{message_type, text, language_code|null, words:[{text, start, end, type:"word"|"spacing", speaker_id, logprob, characters:[...]}]}`. Sent AFTER `committed_transcript`, only when include_timestamps or include_language_detection is true [Events]. `start`/`end` are SECONDS (doubles) [API ref].
- Note `words` includes `spacing` items: filter `type=="word"` before alignment.
- Other: `diarized_transcript` (has `segment_index`, word type may be `audio_event`), `speakers_merged`, `committed_transcript_entities`, `redacted_transcript`, `edited_transcript`, `warning{warning}`.

**Errors** (all `{message_type, error}`; sent before close) [API ref][Events]: `error`, `auth_error`, `quota_exceeded`, `commit_throttled`, `unaccepted_terms`, `rate_limited`, `queue_overflow`, `resource_exhausted`, `session_time_limit_exceeded`, `input_error`, `invalid_request`, `chunk_size_exceeded`, `insufficient_audio_activity` (not enough activity to keep the connection open), `transcriber_error`.

**Timestamp basis (connection- vs segment-relative): NOT documented.** The Commit page explicitly does not say. Must be settled by the smoke test (B-03), as the TDD already plans. I did not find a source either way. Unverified.

**Session limits:** an error `session_time_limit_exceeded` exists but no number is documented in anything I fetched. Max chunk size also not documented (only the `chunk_size_exceeded` error). Docs example sends 1 s (32,000 bytes) chunks [Server]. Manual mode auto-commits after ~36 s of accumulated audio [Commit]. Unverified: whether VAD mode has a different cap.

**Concurrency (realtime STT)** [Models][help-center page https://elevenlabs.io/docs/help-center/product/core-capabilities/speech-to-text/how-many-speech-to-text-requests-can-i-make-and-can-i-increase-it]: Free 6, Starter 9, Creator 15, Pro 30, Scale 45. Both official pages agree. (A different help page seen via search snippet listed 4/6/10/20/30; the pricing page fetcher inferred 10 for Creator. These conflict; the two docs pages saying 15 are the more consistent. Either way one demo session is far below it.)

## 2. Pricing and credits

- API pricing page: Scribe v3 Live $0.22/hour (Scribe v3 batch $0.20/hour). "API usage is billed in US dollars, not credits" [Pricing]. Page fetcher also suggested Creator includes ~100 h of realtime STT (stated as inferred from a garbled table; unverified).
- Billing counts every second of audio sent, including silence [STT cap]. Keyterm prompting costs extra [STT cap].
- Credit rate for realtime API: unverified. Secondary sources say the web app's transcription costs ~330 credits/min (not an official page I could open). If realtime API drew from credits at that rate, 131k credits = ~397 min = ~6.6 h. Treat as a pessimistic floor.
- Creator credit count: official figure not verified. One search result lists Creator as 100k credits/$22; I found no source for 131k (the Hacker Guide says only "1 free month of our Creator Plan ($22 value)"). Verify in the dashboard after redeeming.
- Budget at $0.22/h: a full day of testing (say 4 h of streamed audio) is ~$0.88; even at the pessimistic 330 credits/min, 4 h = ~79k credits, so a day of testing plus a demo likely fits, but only if mic streaming is stopped while idle (silence is billed). Mark as estimate.

## 3. Features that could honestly strengthen the prize entry

Only documented items:
- **Audio events (laughter, applause):** documented for batch Scribe (`audio_event` word type) [STT cap]. For realtime, the only mention is `audio_event` as a possible word type inside `diarized_transcript` (requires diarize=true) [API ref]. Realtime support is therefore UNVERIFIED; do not promise it. Test with diarize=true and laughter in the smoke test, only if cheap.
- **Keyterm prompting:** realtime supports up to 50 terms x 20 chars, extra cost [STT cap]. Cheap win: names/sponsor terms for the demo.
- **Language detection / multilingual:** `include_language_detection`, `multilang_mode=true` (v3 live; follows mid-sentence switches; SDK lacks it) [Lang]. **Scribe does not translate** ("Speech is transcribed in the language it is spoken in") [Lang], matching TDD line 484. No per-word language labels documented.
- **Translation stretch:** ElevenLabs Dubbing ("Translate audio while preserving the emotion, timing & tone") is listed in the Hacker Guide [Guide] but is a file/audio product; I did not verify a realtime API. A realistic stretch is: Scribe multilang transcript + an LLM translation + emotion2vec on original audio. TTS is not needed.
- **Turn prediction** (`commit_strategy=turn_prediction`) could reduce premature VAD commits; v3 live only; needs raw WebSocket [Commit]. Not unlocked by SDK.
- **Realtime diarization** (`diarize=true`) is available, relevant if the demo is ever two speakers; TDD says single-speaker.
- **TTS / Agents platform:** exist (Hacker Guide lists Agents in 32 languages, TTS in 32 languages) [Guide]. I did not research voice/emotion settings; they don't fit the project's core. Unverified for emotion control, skip unless asked.
- Honest framing: Scribe v3 Live is central (live words + timestamps drive the visualization), which is a legitimate "built with ElevenLabs" story.

## 4. Hacker Guide summary [Guide]

- Free credits: 1 month of Creator plan ($22 value). Redeem via ElevenLabs Discord (https://discord.com/invite/VnBvbbcdEC): join, open #coupon-codes, click "Start Redemption", choose the event, enter the registration email, bot sends a unique coupon code. Support: #hackathon-support in Discord.
- The guide does NOT mention 131k credits, a "Best Project Built with ElevenLabs" prize, or judging criteria. Unverified from my side.
- Showcase: submit at https://showcase.elevenlabs.io/ ; fork the GitHub repo, add a project MDX file per template, open a PR, and fill the form. Selected projects get limited-edition swag. Separate 20-second anonymous feedback form for merch.
- Core products listed: speech generation, transcription, music, sound effects, dubbing, voices, agents. Past (2025) winners are mostly voice-assistant apps.
- No recommended API order beyond the product list.

## 5. Python SDK

- Package `elevenlabs`, latest 2.79.0 (uploaded 2026-11-16), requires Python >=3.8 [PyPI].
- Docs show `from elevenlabs import AudioFormat, CommitStrategy, ElevenLabs, RealtimeEvents, RealtimeAudioOptions`; `conn = await client.speech_to_text.realtime.connect(RealtimeAudioOptions(model_id="scribe_v3_live", audio_format=AudioFormat.PCM_16000, sample_rate=16000, commit_strategy=CommitStrategy.MANUAL, include_timestamps=True))`; `conn.on(RealtimeEvents.PARTIAL_TRANSCRIPT, cb)` etc. (also SESSION_STARTED, COMMITTED_TRANSCRIPT, COMMITTED_TRANSCRIPT_WITH_TIMESTAMPS, ERROR, CLOSE); `await conn.send({"audio_base_64":..., "sample_rate":16000})`; `await conn.commit()` [Server].
- Gaps: SDK enums lack `turn_prediction`, `multilang_mode`, keyterm library [Models][Commit]. Whether `vad_silence_threshold_secs` and `CommitStrategy.VAD` pass through the Python options is not shown in the docs I read (JS SDK restricts to 0.3-3.0). Unverified for Python.
- Recommendation (judgment): the raw WebSocket (`websockets` lib, ~50 lines) gives full control, exposes all message types including errors with exact `message_type`, and is already what the TDD/PIPELINE ScribeAdapter assumes. The SDK is a reasonable fallback; it hides raw frames, which B needs for the timing smoke test.

## Contradictions with TDD

1. TDD says the `committed_transcript_with_timestamps` "later" message; docs confirm it follows `committed_transcript` but it is only sent if `include_timestamps=true` (or language detection). Consistent.
2. TDD `.env` `SCRIBE_VAD_SILENCE_SECS=0.65` is within the API range (0.192-3.0). OK. No documented default, so always set it explicitly.
3. TDD does not mention that `words` contains `type:"spacing"` items; alignment code must filter them. Also `start`/`end` are seconds (floats), while the TDD clock is ms/samples: convert.
4. TDD error handling lists auth_error, quota_exceeded, unaccepted_terms, rate_limited. Docs list more: `session_time_limit_exceeded`, `queue_overflow`, `resource_exhausted`, `commit_throttled`, `chunk_size_exceeded`, `insufficient_audio_activity`, `input_error`, `invalid_request`, `transcriber_error`, `error`. Add `session_time_limit_exceeded` (probably reconnect with new epoch) and `insufficient_audio_activity` (connection may be closed during long silence: handle as transient).
5. `model_id` defaults to `scribe_v2_realtime`; the adapter must always send `scribe_v3_live` (TDD does).
6. TDD sentence "Scribe's multilingual transcription is not itself English translation" is confirmed by docs.
7. TDD footnote that Creator = 131k credits: unverified (see section 2). Realtime API is billed in USD per audio hour per the pricing page; the credit mapping is unclear.

## Open questions

- Are word `start`/`end` relative to connection start or segment start? (Undocumented; smoke test.)
- `session_time_limit_exceeded`: what is the limit in VAD mode?
- Does realtime emit `audio_event` words outside diarize mode (laughter)? Unverified.
- How many credits per hour does realtime STT draw from the Creator pool, and how many credits does the hackathon coupon actually grant (131k vs ~100k)? Check dashboard after redeeming.
- Does the "Best Project Built with ElevenLabs" prize have published criteria? Not in the Hacker Guide.
- Does Python SDK `RealtimeAudioOptions` accept `vad_silence_threshold_secs` and `CommitStrategy.VAD`? Verify by import or use raw WebSocket.
- Does `commit_strategy=vad` also deliver `committed_transcript` and the timestamped event in order for back-to-back short commits? Smoke test.
