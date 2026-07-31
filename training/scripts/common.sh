#!/usr/bin/env bash
set -Eeuo pipefail

TRAINING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd -- "$TRAINING_DIR/.." && pwd)"

if [[ -f "$TRAINING_DIR/config/local.env" ]]; then
  # shellcheck disable=SC1091
  source "$TRAINING_DIR/config/local.env"
fi

absolute_from_repo() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$REPO_ROOT" "$1" ;;
  esac
}

TRAIN_PYTHON="${TRAIN_PYTHON:-python3}"
TRAIN_ROOT="$(absolute_from_repo "${TRAIN_ROOT:-training/work}")"
DATASET_DIR="$(absolute_from_repo "${DATASET_DIR:-dataset/work/training_data/sft_zh_chat_v2}")"
MODEL_4B_REPO="${MODEL_4B_REPO:-huihui-ai/Huihui-Qwen3.5-4B-abliterated}"
MODEL_9B_REPO="${MODEL_9B_REPO:-huihui-ai/Huihui-Qwen3.5-9B-abliterated}"
MODEL_4B_DIR="$(absolute_from_repo "${MODEL_4B_DIR:-$TRAIN_ROOT/models/base/Huihui-Qwen3.5-4B-abliterated}")"
MODEL_9B_DIR="$(absolute_from_repo "${MODEL_9B_DIR:-$TRAIN_ROOT/models/base/Huihui-Qwen3.5-9B-abliterated}")"

mkdir -p "$TRAIN_ROOT/models/base" "$TRAIN_ROOT/models/adapters" \
  "$TRAIN_ROOT/models/merged" "$TRAIN_ROOT/models/quantized" \
  "$TRAIN_ROOT/logs" "$TRAIN_ROOT/tools"

model_repo() {
  case "$1" in
    4b) printf '%s\n' "$MODEL_4B_REPO" ;;
    9b) printf '%s\n' "$MODEL_9B_REPO" ;;
    *) printf 'Expected model key 4b or 9b, got: %s\n' "$1" >&2; return 2 ;;
  esac
}

model_dir() {
  case "$1" in
    4b) printf '%s\n' "$MODEL_4B_DIR" ;;
    9b) printf '%s\n' "$MODEL_9B_DIR" ;;
    *) printf 'Expected model key 4b or 9b, got: %s\n' "$1" >&2; return 2 ;;
  esac
}

batch_size() {
  case "$1" in
    4b) printf '%s\n' "${PER_DEVICE_BATCH_4B:-2}" ;;
    9b) printf '%s\n' "${PER_DEVICE_BATCH_9B:-1}" ;;
  esac
}

grad_accum() {
  case "$1" in
    4b) printf '%s\n' "${GRAD_ACCUM_4B:-8}" ;;
    9b) printf '%s\n' "${GRAD_ACCUM_9B:-16}" ;;
  esac
}
