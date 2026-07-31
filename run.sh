#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_CLI="${MUALANI_LLAMA_CLI:-$APP_ROOT/bin/llama-cli}"
PROMPT="$APP_ROOT/app/prompts/mualani_system_prompt_zh.txt"
DATA_DIR="${MUALANI_DATA_DIR:-$APP_ROOT/data}"
PREFERENCES_FILE="${MUALANI_PREFERENCES_FILE:-$DATA_DIR/preferences.conf}"

find_model() {
  local key="$1" override_name="$2" candidate
  candidate="${!override_name:-}"
  if [[ -n "$candidate" ]]; then
    [[ -f "$candidate" ]] && printf '%s\n' "$candidate"
    return
  fi
  shopt -s nullglob
  local matches=("$APP_ROOT/models/$key"/*.gguf)
  shopt -u nullglob
  if ((${#matches[@]} > 0)); then
    printf '%s\n' "${matches[0]}"
  fi
}

MODEL_4B="$(find_model 4b MUALANI_MODEL_4B)"
MODEL_9B="$(find_model 9b MUALANI_MODEL_9B)"
if [[ -z "$MODEL_4B" && -z "$MODEL_9B" ]]; then
  printf 'No GGUF model was found. Put a model in models/4b or models/9b.\n' >&2
  exit 1
fi
if [[ ! -x "$LLAMA_CLI" ]]; then
  printf 'Runtime binary not found or not executable: %s\n' "$LLAMA_CLI" >&2
  exit 1
fi

mkdir -p "$DATA_DIR/sessions"
LAST_MODEL=9b
LAST_RESPONSE_MODE=short
if [[ -r "$PREFERENCES_FILE" ]]; then
  while IFS='=' read -r key value; do
    value="${value%$'\r'}"
    case "$key" in
      model) [[ "$value" == 4b || "$value" == 9b ]] && LAST_MODEL="$value" ;;
      response_mode) [[ "$value" == short || "$value" == long ]] && LAST_RESPONSE_MODE="$value" ;;
    esac
  done < "$PREFERENCES_FILE"
fi

START_MODEL="${MUALANI_START_MODEL:-$LAST_MODEL}"
RESPONSE_MODE="${MUALANI_RESPONSE_MODE:-$LAST_RESPONSE_MODE}"
if [[ "$START_MODEL" == 4b && -z "$MODEL_4B" ]]; then START_MODEL=9b; fi
if [[ "$START_MODEL" == 9b && -z "$MODEL_9B" ]]; then START_MODEL=4b; fi
if [[ "$RESPONSE_MODE" != short && "$RESPONSE_MODE" != long ]]; then
  printf 'MUALANI_RESPONSE_MODE must be short or long.\n' >&2
  exit 1
fi

REQUESTED_BACKEND="${MUALANI_BACKEND:-auto}"
case "$REQUESTED_BACKEND" in
  auto)
    if "$LLAMA_CLI" --list-devices 2>&1 | grep -qi vulkan; then
      MUALANI_ACTIVE_BACKEND=vulkan
    else
      MUALANI_ACTIVE_BACKEND=cpu
    fi
    ;;
  vulkan|cpu) MUALANI_ACTIVE_BACKEND="$REQUESTED_BACKEND" ;;
  *) printf 'MUALANI_BACKEND must be auto, vulkan, or cpu.\n' >&2; exit 1 ;;
esac
export MUALANI_ACTIVE_BACKEND

source "$APP_ROOT/scripts/context-profile.sh"
if [[ "$START_MODEL" == 4b ]]; then
  MODEL="$MODEL_4B"
  MODEL_CTX="$MUALANI_CTX_4B"
else
  MODEL="$MODEL_9B"
  MODEL_CTX="$MUALANI_CTX_9B"
fi

export LLAMA_CLI_SESSION_DIR="$DATA_DIR/sessions"
export LLAMA_CLI_PREFERENCES_FILE="$PREFERENCES_FILE"
export LLAMA_CLI_CURRENT_MODEL="$START_MODEL"
export LLAMA_CLI_RESPONSE_MODE="$RESPONSE_MODE"
export LLAMA_CLI_CHARACTER_CARDS_DIR="$APP_ROOT/app/cards/characters"
export LLAMA_CLI_CHARACTER_CARD_DEFAULTS="${LLAMA_CLI_CHARACTER_CARD_DEFAULTS:-traveler}"
export LLAMA_CLI_RELATIONSHIP_CARDS_DIR="$APP_ROOT/app/cards/relationships"
export LLAMA_CLI_RELATIONSHIP_INDEX_FILE="$APP_ROOT/app/cards/relationships/runtime_index.json"
export LLAMA_CLI_RELATIONSHIP_MAX_ACTIVE="${LLAMA_CLI_RELATIONSHIP_MAX_ACTIVE:-4}"
export LLAMA_CLI_WORLD_LORE_CARDS_DIR="$APP_ROOT/app/cards/world"
export LLAMA_CLI_WORLD_LORE_MAX_ACTIVE="${LLAMA_CLI_WORLD_LORE_MAX_ACTIVE:-6}"
[[ -n "$MODEL_4B" ]] && export LLAMA_CLI_MODEL_4B="$MODEL_4B"
[[ -n "$MODEL_9B" ]] && export LLAMA_CLI_MODEL_9B="$MODEL_9B"

GPU_LAYERS=0
[[ "$MUALANI_ACTIVE_BACKEND" == vulkan ]] && GPU_LAYERS=99
THREADS="${MUALANI_THREADS:-8}"

printf 'Starting %s model in %s mode (%s backend, %s-token context).\n' \
  "$START_MODEL" "$RESPONSE_MODE" "$MUALANI_ACTIVE_BACKEND" "$MODEL_CTX"

exec "$LLAMA_CLI" \
  --model "$MODEL" \
  --system-prompt-file "$PROMPT" \
  --conversation \
  --color on \
  --reasoning off \
  --reasoning-format deepseek \
  --chat-template-kwargs '{"enable_thinking":false}' \
  --ctx-size "$MODEL_CTX" \
  --predict 2048 \
  --n-gpu-layers "$GPU_LAYERS" \
  --flash-attn auto \
  --threads "$THREADS" \
  --threads-batch "$THREADS" \
  --temp 0.55 \
  --top-p 0.85 \
  --min-p 0.05 \
  --repeat-last-n 128 \
  --repeat-penalty 1.08 \
  --logit-bias 248046-1.5 \
  "$@"
