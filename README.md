# Emotional Translator implementation kit

Use this kit to start a fresh GitHub monorepo with three developers and three coding agents. The included TDD is the product baseline. The kit supplies the work orders, interfaces, and synthetic example data each agent needs before implementation. The K0 snapshot means these kit files are available to all three builders.

## Start here

1. **Developer A, backend and integration:** Create the shared repository and publish K0 as described in [Setup](docs/SETUP.md). Give each teammate access and the same base commit. Start [A-01](docs/prompts/A-01.md).
2. **Developer B, audio and AI:** Clone the shared repository and start [B-01](docs/prompts/B-01.md) using the B setup instructions. B owns the Scribe adapter, real emotion2vec+ Large adapter, scheduling, smoothing, and benchmarks. [Setup](docs/SETUP.md#builder-b--audio-and-ai)
3. **Developer C, frontend:** Clone the shared repository and start [C-01](docs/prompts/C-01.md) using the C setup instructions. C owns the browser microphone, React state and UI, SVG clouds, and visual checks. [Setup](docs/SETUP.md#builder-c--frontend)

Give each agent one prompt file at a time, the repo checkout with the listed prerequisites, and the applicable files under `docs/` and `shared/`. Bring results back with the PR evidence template. [Prompt schedule](docs/DEPENDENCIES.md) · [Handoff workflow](docs/HANDOFFS.md)

## What the team delivers

- **First development milestone:** Once the dependencies have been installed, A starts a keyless local FastAPI process and C starts the frontend. A synthetic saved event stream drives the real shared reducer and shows partial-to-final text, animated phrase clouds, multiline wrap, and history through loopback. See the exact checks for segments, revisions, and controls. [G1 acceptance](docs/ACCEPTANCE.md#g1--offline-vertical-slice)
- **Hackathon centerpiece:** Live microphone audio reaches ElevenLabs Scribe v3 Live in VAD mode and the real, locally loaded emotion2vec+ Large model. Timestamped phrases receive clouds driven by scored windows. Show live first and use visibly labeled saved replay if needed. [Live gates and rehearsal](docs/ACCEPTANCE.md) · [Demo runbook](docs/DEMO.md)

## Files

| Need | Start with |
|---|---|
| Product requirements and the 16 frozen decisions | [TDD](docs/TDD.md), [decision traceability](docs/DECISIONS.md) |
| Ownership, paths, and machine setup | [Repository plan](docs/REPOSITORY.md), [builder setup](docs/SETUP.md), [environment template](.env.example) |
| Browser and backend agreement | [Protocol](docs/PROTOCOL.md), [JSON Schemas](shared/schemas/v1/server-event.schema.json), [fixture guide](shared/fixtures/README.md) |
| Backend and adapter agreement | [Pipeline interfaces](docs/PIPELINE.md) |
| Parallel work and evidence | [Dependency graph](docs/DEPENDENCIES.md), [acceptance checks](docs/ACCEPTANCE.md), [handoff workflow](docs/HANDOFFS.md) |

The repository tree describes files the builders will create. Start from K0 and reviewed prerequisite commits, even if you have an exploratory prototype elsewhere. The example fixture provenance is `synthetic_example`. The copy of the TDD in this kit is verbatim.
