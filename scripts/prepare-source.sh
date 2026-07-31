#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${MUALANI_SOURCE_DIR:-$ROOT/.build/llama.cpp}"
UPSTREAM_COMMIT="e9fa0781f1c25fc4fe8c86be1edc6970661ad6f0"

if [[ ! -d "$SOURCE_DIR/.git" ]]; then
  mkdir -p "$(dirname -- "$SOURCE_DIR")"
  git init "$SOURCE_DIR"
  git -C "$SOURCE_DIR" remote add origin https://github.com/ggml-org/llama.cpp.git
  git -C "$SOURCE_DIR" fetch --depth=1 origin "$UPSTREAM_COMMIT"
  git -C "$SOURCE_DIR" checkout --detach FETCH_HEAD
else
  CURRENT="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
  if [[ "$CURRENT" != "$UPSTREAM_COMMIT" ]]; then
    printf 'Unexpected upstream checkout: %s (expected %s)\n' "$CURRENT" "$UPSTREAM_COMMIT" >&2
    exit 1
  fi
fi

cp -a "$ROOT/overlay/." "$SOURCE_DIR/"
printf '%s\n' "$SOURCE_DIR"
