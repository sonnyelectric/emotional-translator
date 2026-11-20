#!/usr/bin/env bash
# Download the pinned emotion2vec+ Large weights (never committed) into
# $EMOTION_MODEL_CACHE_DIR (default $HOME/model-cache/emotion2vec_plus_large).
# Skips files already present; always verifies model.pt by sha256. Re-runnable.
# Optional: HF_TOKEN for an authenticated download (the repo is public).
set -euo pipefail

REPO="emotion2vec/emotion2vec_plus_large"
REVISION="6c303ba987b86b93193de93e34bb2b077a6bedc4"
MODEL_SHA256="be501a01f26fcdc7663a062dff86af839afbaef7c4de32f5e42d7e1ad2784da4"
MODEL_BYTES=1945790254
FILES=(config.yaml configuration.json tokens.txt model.pt)

dest="${EMOTION_MODEL_CACHE_DIR:-$HOME/model-cache/emotion2vec_plus_large}"
mkdir -p "$dest"

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

auth=()
if [[ -n "${HF_TOKEN:-}" ]]; then
    auth=(-H "Authorization: Bearer ${HF_TOKEN}")
fi

for name in "${FILES[@]}"; do
    target="$dest/$name"
    if [[ -s "$target" ]]; then
        echo "present: $target"
        continue
    fi
    url="https://huggingface.co/${REPO}/resolve/${REVISION}/${name}"
    echo "downloading: $name (rev ${REVISION:0:12})"
    # Resume a partial .part file; move into place only after a complete download.
    curl -fL --retry 5 --retry-delay 3 --retry-all-errors -C - ${auth[@]+"${auth[@]}"} \
        -o "$target.part" "$url"
    mv "$target.part" "$target"
done

size=$(wc -c < "$dest/model.pt" | tr -d ' ')
if [[ "$size" != "$MODEL_BYTES" ]]; then
    echo "model.pt is $size bytes, expected $MODEL_BYTES. Delete $dest/model.pt and re-run." >&2
    exit 1
fi
echo "verifying model.pt sha256 ..."
actual=$(sha256_of "$dest/model.pt")
if [[ "$actual" != "$MODEL_SHA256" ]]; then
    echo "model.pt sha256 mismatch: got $actual, expected $MODEL_SHA256." >&2
    echo "Delete $dest/model.pt and re-run." >&2
    exit 1
fi
echo "ok: $dest (model.pt sha256 verified)"
