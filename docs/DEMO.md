# Judge demo and reproducibility

## Preflight on the judging laptop

- Record the commit, OS, CPU/GPU, RAM, Python, model runtime and checkpoint identifier, Node and browser. Confirm model cache, ElevenLabs quota and terms, local microphone permission and stable Wi-Fi. Start one local backend worker and the frontend. Preload the real Large model with `--live` before presenting. [Builder setup](SETUP.md)
- Run the live smoke and inspect the real inference/annotation path. Keep a replay fixture ready in the same UI. Rehearse keyless replay once independently with external networking off. [Acceptance](ACCEPTANCE.md)
- Obtain permission for the speakers and disclose the live Scribe audio path. Do not include captured audio or identifying provider payloads in the submission.

## Judge walkthrough

1. Open the clean idle screen, select **LIVE**, and say “Emotional Translator turns detected vocal tone into visual cues alongside speech.”
2. Press Start. Speak a short line in a neutral voice, then angry, sad, and happy examples with natural pauses. Show provisional words, stable transcript, and aligned cloud updates. Explain that shape and color represent the displayed cue, support influences opacity, and visual intensity changes size and saturation.
3. Expand history and inspect a phrase label. Explain that the scores are relative model support, and the two-second audio windows approximate where a cue occurs. Report any observed miss plainly.
4. If live is disrupted, say what failed. Use Stop if active, Reset, then switch to **REPLAY** and play a named fixture. Say that the fixture holds saved events. Identify the provenance shown in the UI.
5. If asked about data or setup, explain that live transcription audio travels to ElevenLabs, emotion inference runs via the real local model, and normal sessions remain ephemeral. Give the measured latency and known limitations from the benchmark.

## Evidence for the final review

| Record | What to include |
|---|---|
| Environment | Commit and dated hardware/software inventory, one backend worker, approved provider settings, model/cache setup |
| Evidence of reality | Scrubbed actual mic/Scribe timestamps and actual scored-window metadata, with route and state; no captured audio or text in normal logs |
| Measurements | Sample counts, p50/p95 per metric, load time, peak RAM, drop count, backlog, phrase-end target assessment and known drift |
| Reproducibility | Clean setup, offline replay invocation, provenance class, tested fixture ID, both language contract checks |
| Known limitations | Long speech can delay VAD commits, voice/accent/noise may affect prediction, model support is relative, and scenario results do not establish clinical or accessibility validation |

Post-core work may consider a radar scoped to the latest analyzed segment after the core gates are met. Phrase inspection is built after the first replay clouds. Speech-to-English translation with original-audio timestamps is future scope. Keep the demo grounded in live transcription and aligned clouds.
