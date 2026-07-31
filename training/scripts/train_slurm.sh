#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TRAINING_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$TRAINING_DIR/config/slurm.env" ]]; then
  # shellcheck disable=SC1091
  source "$TRAINING_DIR/config/slurm.env"
fi

MODEL_KEY="${1:-4b}"
RUN_ID="${2:-mualani-${MODEL_KEY}-$(date -u +%Y%m%dT%H%M%SZ)}"
SBATCH_ARGS=(
  --job-name="mualani-$MODEL_KEY"
  --partition="${SLURM_PARTITION:-gpu}"
  --gres="${SLURM_GRES:-gpu:1}"
  --cpus-per-task="${SLURM_CPUS:-8}"
  --mem="${SLURM_MEMORY:-160G}"
  --time="${SLURM_TIME:-06:00:00}"
  --output="${SLURM_LOG:-mualani-%j.log}"
)
if [[ -n "${SLURM_CONSTRAINT:-}" ]]; then
  SBATCH_ARGS+=(--constraint="$SLURM_CONSTRAINT")
fi
if [[ -n "${SLURM_ACCOUNT:-}" ]]; then
  SBATCH_ARGS+=(--account="$SLURM_ACCOUNT")
fi

sbatch "${SBATCH_ARGS[@]}" --wrap="bash '$SCRIPT_DIR/train_local_cuda.sh' '$MODEL_KEY' '$RUN_ID'"
