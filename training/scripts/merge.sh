#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

MODEL_KEY="${1:-4b}"
ADAPTER_RUN="${2:-latest}"
OUTPUT_RUN="${3:-mualani-${MODEL_KEY}-merged-$(date -u +%Y%m%dT%H%M%SZ)}"
"$TRAIN_PYTHON" "$TRAINING_DIR/src/merge_lora.py" \
  --base-model "$(model_dir "$MODEL_KEY")" \
  --adapter "$TRAIN_ROOT/models/adapters/$MODEL_KEY/$ADAPTER_RUN/final" \
  --output-dir "$TRAIN_ROOT/models/merged/$MODEL_KEY/$OUTPUT_RUN"
printf '%s\n' "$TRAIN_ROOT/models/merged/$MODEL_KEY/$OUTPUT_RUN"
