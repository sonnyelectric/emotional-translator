# Builder setup

These commands are for the developers and their agents during implementation. K0 is the initial commit of this kit. Application files and scripts become available only after the owning prompt lands.

## Builder A · backend and integration

1. Create an empty GitHub repository under your account and give B and C write access. Unzip this kit and use its inner directory contents as the repo root, including `.env.example`. Commit the kit on `main` as K0. Share the repository URL and K0 SHA with both teammates. Configure protected `main` and PR review as soon as repository settings allow.
2. Start `dev/a-01-foundation` at K0. Complete [A-01](prompts/A-01.md). Start with Python 3.11 and Node 22.12+ as candidate toolchains. Use the same validated major/minor choices in local setup and CI. Record exact tested versions and adjust with B if the Large model runtime requires it. Prefer Chromium for the demo and UI acceptance.
3. A-01 provides backend dependencies, local checks and launch scripts. C-01 provides the frontend lock. After both merge, bootstrap from the repository root with the first command below. Later enable live only after B documents the working model stack and makes the live lock available.

```bash
bash scripts/setup.sh
bash scripts/start_backend.sh --replay
```

In a separate terminal after C-01:

```bash
bash scripts/start_frontend.sh
```

Open `http://localhost:5173`. Backend health is at `http://127.0.0.1:8000/healthz`. A-01 implements the script options `--backend-only` (core), `--frontend-only`, and `--live` (core plus optional live Python lock and frontend). Use one Uvicorn worker. `--replay` is the default backend mode and skips model imports, weights, and provider startup.

## Builder B · audio and AI

1. Clone the repository, fetch K0, and create `dev/b-01-model-preflight` from the supplied SHA. Inventory the candidate laptop and model installation paths using [B-01](prompts/B-01.md). With A-01 still in flight you can use an isolated venv and the standard library check. No ElevenLabs key is needed for B-01 or the test-only B-02.
2. After A-01, run `bash scripts/setup.sh --backend-only` from the repo root. The backend interpreter is `.venv/bin/python`. Once B-04's live lock is available, run `.venv/bin/python -m pip install -r backend/requirements.lock -r backend/requirements-live.lock` on the supported laptop. If you're running the whole stack use `bash scripts/setup.sh --live`.
3. For live credentials, copy the root template to the ignored `backend/.env`. Fill `ELEVENLABS_API_KEY` locally with your own authorized key. Confirm Scribe access, quota and terms in the account, then run the opt-in provider smoke from B-03. Share scrubbed findings and never share the actual key in a prompt, chat, PR, shell trace, or frontend setting.
4. For the real model, verify licensing and distribution terms, choose an out-of-repo cache, and pin usable dependencies. The later `scripts/inspect_emotion.py` supports `--check` for offline environment inspection, `--download` for explicit model-cache preparation, and `--score <local-wav>` for actual output inspection. Use a permitted short local sample for this diagnostic, or a permitted live test via UI once available. The judging and replay flows do not require saved audio. Hand A the tested command, cache location convention, platform, and dependencies.

## Builder C · frontend

1. Clone the repository and create `dev/c-01-frontend-contracts` from K0. Use a supported Node toolchain per [C-01](prompts/C-01.md). C-01 sets up Vite, React, TypeScript, the runtime contract checker and npm scripts. Keep `package-lock.json` committed. Run the commands below after the package files exist.
2. Use the checked-in fixture files with an HTTP test stub until A-02 lands. Follow [C-02](prompts/C-02.md). No keys or weights are needed for any frontend task. Run C-03 with fake media and local/mock socket commands until the actual integrated checkout is ready.
3. For the later real mic smoke, open the Vite UI at the exact configured local origin, grant mic access explicitly, and select Live. Use only public frontend config. C-03 can allow `VITE_BACKEND_HTTP_ORIGIN` for a coordinated loopback origin override. Never set or place the ElevenLabs key in a `VITE_*` variable.

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
npm --prefix frontend run test:contract
npm --prefix frontend run typecheck
```

C-02 adds the local browser test harness and the `install:browsers`, `test:unit`, and `test:e2e` workflow, with `test:unit` available from C-01. Install Chromium before offline tests. App acceptance runs in the review checkout after bootstrap. [G1 instructions](ACCEPTANCE.md#g1--offline-vertical-slice)

## Shared live launch after the integrations land

1. On the candidate judging laptop prepare core/frontend and the optional Large-model runtime. Keep the backend key only in `backend/.env`. Follow B's recorded smoke and benchmark commands. Record the OS, CPU/GPU, RAM and exact Python, model library, Node and Chromium versions.
2. Run `bash scripts/start_backend.sh --live` and `bash scripts/start_frontend.sh` in separate terminals. Check the configured model cache. Its explicit preflight download is a separate step. A reports model load state without blocking transcript startup.
3. Test mic and Wi-Fi before the demo, and inspect service/configuration state. The local backend sends live audio to ElevenLabs for transcription. Emotion inference and normal session storage stay on the laptop. Live provider handling follows the account configuration and applicable terms.
4. For keyless verification, use the earlier replay launch, remove the key from that process's environment, use a cache location with no model weights, and disconnect external internet while keeping loopback available. Use the installed venv/frontend assets. No cloud account is needed in that run.

## Test entry points after the named prompts

| Check | Command from repo root | Available after |
|---|---|---|
| Core Python suite | `.venv/bin/python -m pytest backend/tests/core -q` | A-01 |
| Offline adapter suite | `.venv/bin/python -m pytest backend/tests/audio_ai -q` | B-02 |
| Frontend contract/types | `npm --prefix frontend run test:contract` and `npm --prefix frontend run typecheck` | C-01 |
| Frontend unit/build | `npm --prefix frontend run test:unit` and `npm --prefix frontend run build` | C-01 |
| Local browser test | `npm --prefix frontend run test:e2e` | C-02 |
| Local replay smoke | `bash scripts/verify_replay.sh` using the running replay backend | A-02 |
| Opt-in Scribe/real model/laptop checks | See B-03, B-04 and B-06 | Corresponding B prompt |

Test manifests use the shared directory as data. Package setup and CI validate schema references locally without retrieving schema IDs from the internet.
