# Deploy: live backend on a Replit Reserved VM, frontend on Vercel

This runs the **live** backend (real emotion2vec+ Large on CPU + ElevenLabs Scribe v3 Live) on a
public URL. The ElevenLabs key stays on the server. Browsers reach the backend only from the
frontend origins you allow.

Terms used below:

- **Reserved VM**: a Replit deployment type that keeps one always-on virtual machine for the app.
  We need it because the model must stay loaded in memory and the WebSocket must stay open.
- **Secret**: a Replit environment variable whose value is hidden. The app reads its settings
  from environment variables, so Secrets are where configuration goes. Never commit the values.
- **Origin**: the scheme and host of a web page, for example `https://my-app.vercel.app`.
  The backend refuses WebSockets and replay requests from any origin it was not told about.

## 1. Import the code into the existing Repl

1. Open https://replit.com/@justinwang221/emotional-translator.
2. Connect it to the GitHub repo (Git pane, or Import from GitHub). Check out branch
   `dev/hackathon-build`. The repo is private, so Replit needs GitHub access to it.
3. Confirm `.replit` from the repo is in place. Its content:

   ```toml
   modules = ["python-3.11"]
   run = "bash scripts/replit_start.sh"

   [deployment]
   build = ["bash", "scripts/replit_build.sh"]
   run = ["bash", "scripts/replit_start.sh"]
   deploymentTarget = "gce"

   [[ports]]
   localPort = 8000
   externalPort = 80
   ```

   No `replit.nix` is needed. The build uses only Python 3.11, `curl` and wheels from PyPI and the
   PyTorch CPU index.

## 2. Set the Secrets (names only; values described)

Open **Tools > Secrets** and add these. Then check they also appear under the deployment's
Secrets in the Publishing tool, because the deployment reads its own copy.

| Secret name | Value to use | Required |
|---|---|---|
| `ELEVENLABS_API_KEY` | The team's ElevenLabs API key. Paste it only into Replit. | yes |
| `ALLOWED_ORIGINS` | `https://hueq-ovti8l6xq-sonny1106-4950.vercel.app` (comma-separate more exact origins, e.g. a Vercel production domain) | yes |
| `ALLOWED_ORIGIN_REGEX` | `^https://[a-z0-9-]+-sonny1106-4950\.vercel\.app$` (covers every Vercel preview URL of this team, because the preview URL changes on each deploy) | recommended |
| `SCRIBE_TIMESTAMP_BASIS` | `connection` (already the default in `scripts/replit_start.sh`; the Scribe smoke test proved it) | no |
| `SESSION_MAX_SECONDS` | `300` (default). A live session stops itself after this many seconds. | no |
| `LIVE_DAILY_MAX_SECONDS` | e.g. `3600`. Caps live time per UTC day; new sessions are refused after that. | recommended |

Do **not** set `ALLOWED_ORIGIN` or `ENABLE_TUNE_ROUTE` on Replit. `ALLOWED_ORIGIN` would add a
localhost origin back. `ENABLE_TUNE_ROUTE` would expose a developer page;
`scripts/replit_start.sh` clears it anyway.

Why the guards matter: the endpoint is public and every live second spends ElevenLabs credit.
Only one live session runs at a time (others get "Another live session is already active").

## 3. Try it in the workspace (optional)

Press **Run**. The first run calls `scripts/replit_build.sh`. It creates `.venv`, installs
`backend/requirements-live-linux.txt` (CPU-only torch) and downloads the 1.95 GB weights into
`model-cache/emotion2vec_plus_large/` inside the project, checked by sha256. This takes several
minutes. Then the backend listens on `0.0.0.0:8000`. Open the webview at `/healthz`.

## 4. Deploy as a Reserved VM

1. Open **Publishing** (Deployments) and choose **Reserved VM**, type **Web server**.
2. Machine size: pick at least **4 GB RAM**; **2 vCPU / 8 GB** is the safer choice.
   Because: the loaded model needs about 2.4 GB of resident memory (RSS) at peak, plus the
   torch runtime, Python and the web server. On the Mac, one idle process with the model loaded
   measured 1.5 GB RSS; inference and Linux allocator behavior add to that. 2 GB would run out of memory. One vCPU may also be
   too slow: the model scores a 2-second window every second, and slow scoring shows as
   "Emotion cues delayed". Take the exact size list and prices from the Publishing tool.
3. Build command `bash scripts/replit_build.sh`, run command `bash scripts/replit_start.sh`
   (both come from `.replit`). Port: local 8000 to external 80.
4. Publish. The build installs the packages and fetches the weights. The app then answers `/`
   at once (Replit's health check probes the homepage). The model finishes loading in the
   background, which takes about 20 seconds or more on a cold start.
5. Copy the deployment domain, for example `https://<name>.replit.app`, from the Publishing tool.
6. Check health: `https://<replit-deploy-domain>/healthz` should return
   `{"schema_version":"1.0","status":"ok"}`.

Exactly one uvicorn worker runs. The live lease, the loaded model and the daily cap all live in
that one process. Restarting the deployment resets the daily cap.

## 5. Point the Vercel frontend at it

In the Vercel project, open **Settings > Environment Variables** and add, for Production and
Preview:

```
VITE_BACKEND_HTTP_ORIGIN=https://<replit-deploy-domain>
```

Then **redeploy**. `VITE_*` values are baked in at build time, so changing the variable has no
effect until a new build runs. The frontend derives `wss://<domain>/ws/v1/session` from it. It
accepts any `https://` origin here; plain `http://` only for loopback.

Each Vercel redeploy can get a new preview URL. `ALLOWED_ORIGIN_REGEX` already allows the new
URL. If you drop the regex, add the new URL to `ALLOWED_ORIGINS` and restart the deployment.

## Unverified

- The Linux install has not been run by us. `backend/requirements-live-linux.txt` was resolved
  for `x86_64-manylinux_2_28` / Python 3.11 with `uv pip compile` to exactly the pinned set. Every
  pin exists: 96 have Linux x86_64 wheels on PyPI, and `torch==2.15.0+cpu` and
  `torchaudio==2.11.1+cpu` exist on the PyTorch CPU index. Four are source-only packages
  (`antlr4-python3-runtime`, `crcmod`, `jieba`, `oss2`; pure Python) that pip builds during install.
- `deploymentTarget = "gce"`: current Replit docs show only `"cloudrun"` in examples and do not
  list values. `"gce"` is what we expect the Publishing tool to write for Reserved VM. If Replit
  rewrites it when you pick Reserved VM, keep Replit's value.
- Whether `$HOME` survives from the build into the deployment is not documented. So the scripts
  keep the venv and the weights inside the project directory. `replit_start.sh` reruns the
  build if either is missing, which delays startup.
- Replit says published apps are limited to 8 GB. Our estimate is about 4 GB: weights 1.95 GB,
  plus CPU torch and other packages.
- Real-model CPU latency on Replit hardware has not been measured.

## Sources (Replit docs, checked 2026-11-20)

- Configuration reference (`modules`, `run`, `[deployment]` `build`/`run`/`deploymentTarget`,
  `[[ports]]`): https://docs.replit.com/references/project-setup/configuration.md
- Reserved VM deployments (build/run commands, port mappings, set in the Publishing tool):
  https://docs.replit.com/references/publishing/reserved-vm-deployments.md
- Troubleshooting ("server must listen on `0.0.0.0`"; "You must specify a port with
  `externalPort` set to `80`"; health check sends an HTTP request to the homepage and can time
  out after five seconds; filesystem "is not persistent and resets every time you publish";
  apps up to 8 GB): https://docs.replit.com/cloud-services/deployments/troubleshooting
- Machine configuration (CPU and RAM picked under Adjust settings):
  https://docs.replit.com/features/publishing/machine-configuration
