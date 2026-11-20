# Repository and ownership

Use one GitHub monorepo and local runtime. The tree is the target after development. K0 contains the Markdown, schemas, JSON fixtures, and environment template present in this kit.

```text
emotional-translator/
  README.md                            A
  .env.example  .gitignore              A
  .github/
    CODEOWNERS                          A
    workflows/checks.yml                A
  docs/
    TDD.md  DECISIONS.md                A
    REPOSITORY.md  SETUP.md              A
    PROTOCOL.md  PIPELINE.md             A, with B/C review
    DEPENDENCIES.md  ACCEPTANCE.md       A
    HANDOFFS.md  DEMO.md                 A
    live/
      model-preflight.md  scribe-preflight.md  B
      model-runtime.md  benchmark.md          B
    frontend-demo.md                    C
    prompts/{A-01..06,B-01..07,C-01..06}.md   A, with builder review
  scripts/
    setup.sh  start_backend.sh          A
    start_frontend.sh  verify_replay.sh A
    smoke_scribe.py  inspect_emotion.py B
    benchmark_emotion.py               B
  shared/
    schemas/v1/                        A
    fixtures/                          A
  backend/
    pyproject.toml  requirements.lock    A, core
    requirements-live.lock              B, optional model runtime
    .env                                local only
    app/
      main.py  config.py                A, composition and config
      schemas.py  replay.py             A, parser and local replay delivery
      ws.py  session.py                 A, commands and lifecycle
      audio_ai_ports.py                 A, reviewed by B
      audio/{clock,relay}.py            A, accepted samples and fan-out
      audio/window_scheduler.py         B, inference window extraction
      adapters/{scribe,emotion2vec}.py   B
      emotion/{smoothing,worker}.py     B
      alignment/{segments,phrases}.py   A
      metrics.py                        A, runtime spans and privacy
    tests/
      core/                             A
      fakes/emotion.py                   B, test-only
      audio_ai/                         B
      live/                             A for integration, B for adapters (prefix below)
  frontend/
    package.json  package-lock.json     C
    index.html  vite.config.ts          C
    tsconfig*.json  playwright.config.ts C
    src/
      main.tsx  app/App.tsx             C
      protocol/{events,validate,liveClient,replayClient}.ts C
      replay/clock.ts  state/reducer.ts  C
      state/selectors.ts                C
      audio/{capture,pcm,capture.worklet}.ts C
      components/
        Transcript.tsx  CloudLayer.tsx  C
        TranscriptHistory.tsx           C
        SessionControls.tsx             C
        EmotionInspector.tsx            C
      visual/lineRuns.ts                C
      styles/{tokens,clouds,controls}.css C
    tests/                              C
```

Use explicit package markers where Python needs them. A owns package markers for shared directories and package structure. B may create markers in its exclusive directories when required. Test paths under `backend/tests/live/` use `test_a_*` for integrated flows and `test_b_*` for opt-in provider checks. Put environment, dependencies, and fixture tools under the named owners instead of modifying a teammate's file from a feature branch.

| Interface | Author and approver | Consumers and change handoff |
|---|---|---|
| Schemas, event fixture manifest, and command behavior | A | B and C review before A freezes. C owns generated or checked TS equivalents under `frontend/`. A owns Pydantic equivalents. |
| In-process PCM, Scribe, scores, and worker ports | A | B implements the ports. B supplies observed provider event shape and timestamps. A maps them into the session clock. |
| Backend core dependencies and launch scripts | A | C provides Vite commands, B provides live lock and validated runtime details. A ties them together. |
| Browser capture and cloud rendering | C | A reviews PCM and sequencing behavior. A ships word references and visual parameters. C derives layout positions from the DOM. |
| Review, merge, and system evidence | A | B sends preflight and performance evidence. C sends reducer and visual evidence. Pair on G1, G2/G4, G5, and the rehearsal. |

A uses actual GitHub handles in `CODEOWNERS`. Have A review shared files and cross-lane changes. Keep model weights, local environment files, virtual environments, build output, raw provider data, and captured audio out of Git.
