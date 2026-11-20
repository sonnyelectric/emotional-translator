#!/usr/bin/env bash
# Replit deployment build: Python 3.11 venv with the Linux CPU live stack, then the pinned
# model weights. Everything lands inside the project directory, which is what a deployment
# keeps. Re-runnable: an existing venv is reused and present weights are only re-verified.
set -euo pipefail
cd "$(dirname "$0")/.."

python_bin="${PYTHON_BIN:-}"
if [[ -z "$python_bin" ]]; then
    python_bin=$(command -v python3.11 || command -v python3)
fi
"$python_bin" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else "Python 3.11 required (modules = [\"python-3.11\"] in .replit).")'

if [[ ! -x .venv/bin/python ]]; then
    "$python_bin" -m venv .venv
fi
.venv/bin/python -m pip install --no-cache-dir -r backend/requirements-live-linux.txt
.venv/bin/python -c 'import torch, torchaudio, funasr; print("torch", torch.__version__, "cuda", torch.cuda.is_available(), "funasr", funasr.__version__)'

export EMOTION_MODEL_CACHE_DIR="${EMOTION_MODEL_CACHE_DIR:-$PWD/model-cache/emotion2vec_plus_large}"
bash scripts/fetch_model.sh
