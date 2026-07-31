#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

MODEL_KEY="${1:-all}"
for key in 4b 9b; do
  if [[ "$MODEL_KEY" != "all" && "$MODEL_KEY" != "$key" ]]; then
    continue
  fi
  "$TRAIN_PYTHON" "$TRAINING_DIR/src/download_models.py" \
    --repo-id "$(model_repo "$key")" \
    --output-dir "$(model_dir "$key")"
done
