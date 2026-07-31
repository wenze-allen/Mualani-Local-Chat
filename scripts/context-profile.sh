#!/usr/bin/env bash

detect_linux_vram_bytes() {
  local candidate value largest=0
  shopt -s nullglob
  for candidate in /sys/class/drm/card*/device/mem_info_vram_total; do
    if [[ -r "$candidate" ]]; then
      value="$(<"$candidate")"
      if [[ "$value" =~ ^[0-9]+$ ]] && (( value > largest )); then
        largest="$value"
      fi
    fi
  done
  shopt -u nullglob

  if (( largest == 0 )) && command -v nvidia-smi >/dev/null 2>&1; then
    value="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | sort -nr | head -n 1 || true)"
    if [[ "$value" =~ ^[0-9]+$ ]]; then
      largest=$((value * 1024 * 1024))
    fi
  fi
  printf '%s\n' "$largest"
}

detect_linux_ram_gib() {
  local kib=0
  if [[ -r /proc/meminfo ]]; then
    read -r _ kib _ < <(grep -m1 '^MemTotal:' /proc/meminfo)
  fi
  if [[ ! "$kib" =~ ^[0-9]+$ ]]; then
    kib=0
  fi
  printf '%s\n' "$(( (kib + 524288) / 1048576 ))"
}

select_gpu_contexts() {
  local gib="$1"
  case "$gib" in
    0|1|2|3|4|5) DEFAULT_CTX_4B=16384;  DEFAULT_CTX_9B=4096 ;;
    6|7)         DEFAULT_CTX_4B=32768;  DEFAULT_CTX_9B=4096 ;;
    8|9|10|11)  DEFAULT_CTX_4B=65536;  DEFAULT_CTX_9B=16384 ;;
    12|13|14|15) DEFAULT_CTX_4B=131072; DEFAULT_CTX_9B=65536 ;;
    16|17|18|19|20|21|22|23)
                  DEFAULT_CTX_4B=196608; DEFAULT_CTX_9B=131072 ;;
    *)            DEFAULT_CTX_4B=262144; DEFAULT_CTX_9B=262144 ;;
  esac
}

select_cpu_contexts() {
  local gib="$1"
  case "$gib" in
    0|1|2|3|4|5|6|7)
                  DEFAULT_CTX_4B=8192;   DEFAULT_CTX_9B=4096 ;;
    8|9|10|11)   DEFAULT_CTX_4B=16384;  DEFAULT_CTX_9B=4096 ;;
    12|13|14|15) DEFAULT_CTX_4B=32768;  DEFAULT_CTX_9B=16384 ;;
    16|17|18|19|20|21|22|23)
                  DEFAULT_CTX_4B=65536;  DEFAULT_CTX_9B=32768 ;;
    24|25|26|27|28|29|30|31)
                  DEFAULT_CTX_4B=131072; DEFAULT_CTX_9B=65536 ;;
    *)            DEFAULT_CTX_4B=262144; DEFAULT_CTX_9B=131072 ;;
  esac
}

if [[ "$MUALANI_ACTIVE_BACKEND" == "vulkan" ]]; then
  MUALANI_MEMORY_GIB="${MUALANI_VRAM_GIB:-0}"
  if [[ ! "$MUALANI_MEMORY_GIB" =~ ^[0-9]+$ ]] || (( MUALANI_MEMORY_GIB == 0 )); then
    MUALANI_VRAM_BYTES="$(detect_linux_vram_bytes)"
    MUALANI_MEMORY_GIB=$(( (MUALANI_VRAM_BYTES + 536870912) / 1073741824 ))
  fi
  select_gpu_contexts "$MUALANI_MEMORY_GIB"
else
  MUALANI_MEMORY_GIB="${MUALANI_RAM_GIB:-$(detect_linux_ram_gib)}"
  select_cpu_contexts "$MUALANI_MEMORY_GIB"
fi

export MUALANI_CTX_4B="${MUALANI_CTX_4B:-$DEFAULT_CTX_4B}"
export MUALANI_CTX_9B="${MUALANI_CTX_9B:-$DEFAULT_CTX_9B}"
export LLAMA_CLI_CTX_4B="$MUALANI_CTX_4B"
export LLAMA_CLI_CTX_9B="$MUALANI_CTX_9B"
