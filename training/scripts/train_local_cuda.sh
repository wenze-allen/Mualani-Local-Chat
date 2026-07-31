#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

MODEL_KEY="${1:-4b}"
RUN_ID="${2:-mualani-${MODEL_KEY}-$(date -u +%Y%m%dT%H%M%SZ)}"
RESUME_CHECKPOINT="${3:-}"
MODEL_DIR="$(model_dir "$MODEL_KEY")"
OUTPUT_DIR="$TRAIN_ROOT/models/adapters/$MODEL_KEY/$RUN_ID"
LOG_DIR="$TRAIN_ROOT/logs/train/$MODEL_KEY/$RUN_ID"

if [[ ! -f "$MODEL_DIR/config.json" ]]; then
  printf 'Base model is missing: %s\n' "$MODEL_DIR" >&2
  exit 1
fi
if [[ ! -f "$DATASET_DIR/train.jsonl" ]]; then
  printf 'Dataset is missing: %s\n' "$DATASET_DIR" >&2
  exit 1
fi
if ! "$TRAIN_PYTHON" -c 'import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)'; then
  printf 'PyTorch cannot see a CUDA device.\n' >&2
  exit 1
fi

"$TRAIN_PYTHON" "$TRAINING_DIR/src/verify_dataset.py" \
  --dataset-dir "$DATASET_DIR" --expected-profile chat-v2
mkdir -p "$OUTPUT_DIR" "$LOG_DIR"
cp "$DATASET_DIR/manifest.json" "$OUTPUT_DIR/dataset_manifest.json"

ARGS=(
  --model-dir "$MODEL_DIR"
  --train-file "$DATASET_DIR/train.jsonl"
  --eval-file "$DATASET_DIR/validation.jsonl"
  --output-dir "$OUTPUT_DIR"
  --run-name "$RUN_ID"
  --max-length "${MAX_LENGTH:-2048}"
  --epochs "${NUM_EPOCHS:-2}"
  --learning-rate "${LEARNING_RATE:-3e-5}"
  --batch-size "$(batch_size "$MODEL_KEY")"
  --gradient-accumulation "$(grad_accum "$MODEL_KEY")"
  --lora-r "${LORA_R:-16}"
  --lora-alpha "${LORA_ALPHA:-32}"
  --lora-dropout "${LORA_DROPOUT:-0.05}"
  --seed "${SEED:-3407}"
)
if [[ -n "$RESUME_CHECKPOINT" ]]; then
  ARGS+=(--resume-from-checkpoint "$RESUME_CHECKPOINT")
fi

"$TRAIN_PYTHON" "$TRAINING_DIR/src/train_lora.py" "${ARGS[@]}" \
  2>&1 | tee "$LOG_DIR/train.log"
ln -sfn "$OUTPUT_DIR" "$TRAIN_ROOT/models/adapters/$MODEL_KEY/latest"
