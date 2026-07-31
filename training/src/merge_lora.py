#!/usr/bin/env python3
"""Merge a PEFT LoRA adapter into its Qwen3.5 base model in BF16."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path

import peft
import torch
import transformers
from peft import PeftModel
from transformers import AutoProcessor, AutoTokenizer, Qwen3_5ForConditionalGeneration


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not (args.adapter / "adapter_config.json").is_file():
        raise FileNotFoundError(args.adapter / "adapter_config.json")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    base = Qwen3_5ForConditionalGeneration.from_pretrained(
        args.base_model,
        dtype=torch.bfloat16,
        device_map={"": "cpu"},
        low_cpu_mem_usage=True,
        trust_remote_code=False,
    )
    adapted = PeftModel.from_pretrained(base, args.adapter)
    merged = adapted.merge_and_unload(safe_merge=True)
    merged.config.use_cache = True
    merged.save_pretrained(
        args.output_dir,
        safe_serialization=True,
        max_shard_size="5GB",
    )

    # Preserve all tokenizer/processor assets. AutoProcessor is preferred for
    # the original multimodal architecture; tokenizer fallback covers the 4B
    # abliterated repository's reduced processor metadata.
    try:
        processor = AutoProcessor.from_pretrained(
            args.base_model, trust_remote_code=False
        )
        processor.save_pretrained(args.output_dir)
    except Exception as exc:
        print(f"AutoProcessor fallback: {exc}")
        tokenizer = AutoTokenizer.from_pretrained(
            args.base_model, trust_remote_code=False
        )
        tokenizer.save_pretrained(args.output_dir)

    for name in (
        "chat_template.jinja",
        "generation_config.json",
        "preprocessor_config.json",
        "processor_config.json",
        "video_preprocessor_config.json",
    ):
        source = args.base_model / name
        destination = args.output_dir / name
        if source.is_file() and not destination.exists():
            shutil.copy2(source, destination)

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_model": str(args.base_model.resolve()),
        "adapter": str(args.adapter.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "dtype": "bfloat16",
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "peft": peft.__version__,
        },
    }
    (args.output_dir / "merge_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
