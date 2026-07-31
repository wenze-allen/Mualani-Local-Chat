#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$($ROOT/scripts/prepare-source.sh)"
BUILD_DIR="${MUALANI_BUILD_DIR:-$ROOT/.build/linux-x86_64}"
STAGE_DIR="$ROOT/dist/Mualani-Local-Chat-linux-x86_64"
JOBS="${MUALANI_BUILD_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf 4)}"
CMAKE_EXTRA_ARGS=()
if [[ -n "${MUALANI_VULKAN_INCLUDE_DIR:-}" ]]; then
  CMAKE_EXTRA_ARGS+=("-DVulkan_INCLUDE_DIR=$MUALANI_VULKAN_INCLUDE_DIR")
fi

cmake -S "$SOURCE_DIR" -B "$BUILD_DIR" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DGGML_NATIVE=OFF \
  -DGGML_VULKAN=ON \
  -DMUALANI_TEXT_ONLY=ON \
  "${CMAKE_EXTRA_ARGS[@]}"
cmake --build "$BUILD_DIR" --target llama-cli --parallel "$JOBS"

cmake -E rm -rf "$STAGE_DIR"
cmake -E make_directory "$STAGE_DIR/bin" "$STAGE_DIR/models/4b" "$STAGE_DIR/models/9b"
cmake -E copy "$BUILD_DIR/bin/llama-cli" "$STAGE_DIR/bin/llama-cli"
cmake -E copy_directory "$ROOT/app" "$STAGE_DIR/app"
cmake -E make_directory "$STAGE_DIR/scripts"
cmake -E copy "$ROOT/scripts/context-profile.sh" "$STAGE_DIR/scripts/context-profile.sh"
cmake -E copy_directory "$ROOT/licenses" "$STAGE_DIR/licenses"
cmake -E copy "$ROOT/run.sh" "$ROOT/README.md" "$ROOT/README.zh-CN.md" "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$ROOT/SOURCES.md" "$ROOT/MODEL_SHA256SUMS.txt" "$STAGE_DIR"
chmod +x "$STAGE_DIR/run.sh" "$STAGE_DIR/bin/llama-cli"
if command -v strip >/dev/null 2>&1; then
  strip --strip-unneeded "$STAGE_DIR/bin/llama-cli"
fi

printf 'Linux package staged at %s\n' "$STAGE_DIR"
