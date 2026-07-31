#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

MODEL_KEY="${1:-4b}"
MERGED_DIR="${2:?Usage: quantize_q4km.sh {4b|9b} MERGED_MODEL_DIR [OUTPUT_DIR]}"
DEFAULT_OUTPUT_DIR="$TRAIN_ROOT/models/quantized/$MODEL_KEY/$(basename "$MERGED_DIR")"
OUTPUT_DIR="${3:-$DEFAULT_OUTPUT_DIR}"
LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-$TRAIN_ROOT/tools/llama.cpp}"
QUANT_TYPE="${GGUF_QUANT:-Q4_K_M}"

if [[ ! -d "$LLAMA_CPP_DIR/.git" ]]; then
  git clone "${LLAMA_CPP_REPO:-https://github.com/ggml-org/llama.cpp.git}" "$LLAMA_CPP_DIR"
fi
git -C "$LLAMA_CPP_DIR" checkout \
  "${LLAMA_CPP_REVISION:-e9fa0781f1c25fc4fe8c86be1edc6970661ad6f0}"
cmake -S "$LLAMA_CPP_DIR" -B "$LLAMA_CPP_DIR/build" \
  -DGGML_CUDA=OFF -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build "$LLAMA_CPP_DIR/build" --parallel "${BUILD_JOBS:-8}"

mkdir -p "$OUTPUT_DIR"
F16_GGUF="$OUTPUT_DIR/mualani-${MODEL_KEY}-f16.gguf"
Q_GGUF="$OUTPUT_DIR/mualani-${MODEL_KEY}-${QUANT_TYPE,,}.gguf"
"$TRAIN_PYTHON" "$LLAMA_CPP_DIR/convert_hf_to_gguf.py" \
  "$MERGED_DIR" --outfile "$F16_GGUF" --outtype f16 --no-mtp
"$LLAMA_CPP_DIR/build/bin/llama-quantize" "$F16_GGUF" "$Q_GGUF" "$QUANT_TYPE"
"$LLAMA_CPP_DIR/build/bin/llama-bench" -m "$Q_GGUF" -p 1 -n 1 -r 1
sha256sum "$F16_GGUF" "$Q_GGUF" > "$OUTPUT_DIR/SHA256SUMS"
printf 'Quantized model: %s\n' "$Q_GGUF"
