#!/usr/bin/env bash
set -Eeuo pipefail

DATASET_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORK_ROOT="${MUALANI_DATA_WORK_ROOT:-$DATASET_ROOT/work}"
SOURCE_REPO="${YUANSHEN_RESOURCES_DIR:-$WORK_ROOT/YuanShenResources}"
CORPUS_ROOT="${MUALANI_CORPUS_DIR:-$WORK_ROOT/mualani_corpus}"
OUTPUT_ROOT="${MUALANI_SFT_OUTPUT_DIR:-$WORK_ROOT/training_data}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -d "$SOURCE_REPO/DialogsText" ]]; then
  printf 'Missing YuanShenResources checkout: %s\n' "$SOURCE_REPO" >&2
  printf 'Set YUANSHEN_RESOURCES_DIR or place the repository under dataset/work/.\n' >&2
  exit 1
fi

"$PYTHON_BIN" "$DATASET_ROOT/builders/extract_mualani_corpus.py" \
  --repo "$SOURCE_REPO" \
  --output "$CORPUS_ROOT" \
  --context-turns "${CONTEXT_TURNS:-8}"

if [[ "${INCLUDE_BWIKI_VOICE:-1}" == "1" ]]; then
  "$PYTHON_BIN" "$DATASET_ROOT/builders/add_mualani_bwiki_voice.py" \
    --corpus-root "$CORPUS_ROOT" \
    --revision "${BWIKI_VOICE_REVISION:-611723}"
fi

"$PYTHON_BIN" "$DATASET_ROOT/builders/prepare_mualani_sft.py" \
  --corpus-root "$CORPUS_ROOT" \
  --output-root "$OUTPUT_ROOT" \
  --language "${DATASET_LANGUAGE:-zh}" \
  --quality-profile "${DATASET_PROFILE:-chat-v2}" \
  --traveler-gender "${TRAVELER_GENDER:-male}" \
  --validation-ratio "${VALIDATION_RATIO:-0.05}" \
  --test-ratio "${TEST_RATIO:-0.05}" \
  --seed "${SPLIT_SEED:-mualani-sft-v1}"

if [[ "${DATASET_LANGUAGE:-zh}" == "zh" ]]; then
  PROFILE_SUFFIX=""
  if [[ "${DATASET_PROFILE:-chat-v2}" == "chat-v2" ]]; then
    PROFILE_SUFFIX="_chat_v2"
  fi
  DATASET_DIR="$OUTPUT_ROOT/sft_zh$PROFILE_SUFFIX"
  "$PYTHON_BIN" "$DATASET_ROOT/builders/audit_mualani_sft.py" \
    --dataset-dir "$DATASET_DIR" \
    --source "$CORPUS_ROOT/combined/zh/mualani_training_candidates.jsonl" \
    --report "$DATASET_DIR/audit_report.json" \
    --gender-review "$DATASET_DIR/gender_review.jsonl"
  "$PYTHON_BIN" "$DATASET_ROOT/builders/review_mualani_sft_quality.py" \
    --dataset-dir "$DATASET_DIR" \
    --source "$CORPUS_ROOT/combined/zh/mualani_training_candidates.jsonl" \
    --output-dir "$OUTPUT_ROOT/quality_review$PROFILE_SUFFIX"
fi

printf 'Dataset build completed under: %s\n' "$OUTPUT_ROOT"
