#!/usr/bin/env python3
"""BF16 LoRA SFT for text-only use of Huihui Qwen3.5 4B/9B."""

from __future__ import annotations

import argparse
import inspect
import json
import math
import os
import platform
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import peft
import torch
import transformers
from peft import LoraConfig, get_peft_model
from torch.utils.data import Dataset
from transformers import (
    AutoTokenizer,
    Qwen3_5ForConditionalGeneration,
    Trainer,
    TrainingArguments,
    set_seed,
)


LANGUAGE_MODEL_LORA_REGEX = (
    r"^model\.language_model\.layers\.\d+\."
    r"(?:"
    r"self_attn\.(?:q_proj|k_proj|v_proj|o_proj)"
    r"|linear_attn\.(?:in_proj_qkv|in_proj_z|in_proj_a|in_proj_b|out_proj)"
    r"|mlp\.(?:gate_proj|up_proj|down_proj)"
    r")$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--train-file", type=Path, required=True)
    parser.add_argument("--eval-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation", type=int, default=16)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--logging-steps", type=int, default=5)
    parser.add_argument("--eval-steps", type=int, default=25)
    parser.add_argument("--save-steps", type=int, default=25)
    parser.add_argument(
        "--resume-from-checkpoint",
        type=Path,
        default=None,
        help="Resume Trainer, optimizer, scheduler, and RNG state from this checkpoint.",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            prompt = row.get("prompt")
            completion = row.get("completion")
            if (
                not isinstance(prompt, list)
                or len(prompt) != 2
                or prompt[0].get("role") != "system"
                or prompt[1].get("role") != "user"
                or not isinstance(completion, dict)
                or completion.get("role") != "assistant"
            ):
                raise ValueError(f"{path}:{line_number}: unexpected SFT schema")
            rows.append(row)
    if not rows:
        raise ValueError(f"no examples found in {path}")
    return rows


def encode(tokenizer: Any, text: str) -> list[int]:
    return tokenizer(text, add_special_tokens=False)["input_ids"]


class AssistantOnlyDataset(Dataset):
    """Pre-tokenized ChatML with labels only on the assistant content."""

    def __init__(self, rows: list[dict[str, Any]], tokenizer: Any, max_length: int):
        self.examples: list[dict[str, list[int]]] = []
        self.truncated_prompts = 0
        self.truncated_completions = 0

        for row in rows:
            system = str(row["prompt"][0]["content"]).strip()
            user = str(row["prompt"][1]["content"]).strip()
            completion = str(row["completion"]["content"]).strip()

            system_ids = encode(
                tokenizer,
                f"<|im_start|>system\n{system}<|im_end|>\n",
            )
            user_ids = encode(
                tokenizer,
                f"<|im_start|>user\n{user}<|im_end|>\n",
            )
            assistant_prefix_ids = encode(
                tokenizer,
                "<|im_start|>assistant\n",
            )
            completion_ids = encode(
                tokenizer,
                f"{completion}<|im_end|>\n",
            )

            minimum_prompt = len(system_ids) + len(assistant_prefix_ids)
            if minimum_prompt >= max_length:
                raise ValueError(
                    f"system prompt consumes the full max length ({max_length})"
                )

            max_completion = max_length - minimum_prompt
            if len(completion_ids) > max_completion:
                completion_ids = completion_ids[:max_completion]
                self.truncated_completions += 1

            room_for_user = (
                max_length
                - len(system_ids)
                - len(assistant_prefix_ids)
                - len(completion_ids)
            )
            if len(user_ids) > room_for_user:
                # Preserve the system profile and the latest part of scene context.
                user_ids = user_ids[-room_for_user:] if room_for_user > 0 else []
                self.truncated_prompts += 1

            prompt_ids = system_ids + user_ids + assistant_prefix_ids
            input_ids = prompt_ids + completion_ids
            labels = [-100] * len(prompt_ids) + completion_ids.copy()
            attention_mask = [1] * len(input_ids)
            self.examples.append(
                {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "labels": labels,
                }
            )

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, list[int]]:
        return self.examples[index]


@dataclass
class AssistantOnlyCollator:
    pad_token_id: int
    pad_to_multiple_of: int = 8

    def __call__(self, features: list[dict[str, list[int]]]) -> dict[str, torch.Tensor]:
        max_length = max(len(item["input_ids"]) for item in features)
        if self.pad_to_multiple_of:
            max_length = (
                math.ceil(max_length / self.pad_to_multiple_of)
                * self.pad_to_multiple_of
            )

        batch: dict[str, list[list[int]]] = {
            "input_ids": [],
            "attention_mask": [],
            "labels": [],
        }
        for item in features:
            padding = max_length - len(item["input_ids"])
            batch["input_ids"].append(
                item["input_ids"] + [self.pad_token_id] * padding
            )
            batch["attention_mask"].append(
                item["attention_mask"] + [0] * padding
            )
            batch["labels"].append(item["labels"] + [-100] * padding)
        return {key: torch.tensor(value, dtype=torch.long) for key, value in batch.items()}


def write_runtime_manifest(
    path: Path,
    args: argparse.Namespace,
    train_dataset: AssistantOnlyDataset,
    eval_dataset: AssistantOnlyDataset,
    model: torch.nn.Module,
) -> None:
    trainable = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    total = sum(parameter.numel() for parameter in model.parameters())
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "arguments": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "peft": peft.__version__,
            "cuda": torch.version.cuda,
        },
        "hardware": {
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count(),
            "cuda_devices": [
                torch.cuda.get_device_name(index)
                for index in range(torch.cuda.device_count())
            ],
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "hostname": platform.node(),
        },
        "dataset": {
            "train_rows": len(train_dataset),
            "eval_rows": len(eval_dataset),
            "train_prompt_truncations": train_dataset.truncated_prompts,
            "train_completion_truncations": train_dataset.truncated_completions,
            "eval_prompt_truncations": eval_dataset.truncated_prompts,
            "eval_completion_truncations": eval_dataset.truncated_completions,
        },
        "lora": {
            "target_modules_regex": LANGUAGE_MODEL_LORA_REGEX,
            "trainable_parameters": trainable,
            "total_parameters": total,
            "trainable_percent": 100 * trainable / total,
        },
    }
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    set_seed(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for this training job")
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("the allocated GPU does not report BF16 support")

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_dir,
        use_fast=True,
        trust_remote_code=False,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    train_dataset = AssistantOnlyDataset(
        read_jsonl(args.train_file), tokenizer, args.max_length
    )
    eval_dataset = AssistantOnlyDataset(
        read_jsonl(args.eval_file), tokenizer, args.max_length
    )

    model = Qwen3_5ForConditionalGeneration.from_pretrained(
        args.model_dir,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        trust_remote_code=False,
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable(
        gradient_checkpointing_kwargs={"use_reentrant": False}
    )
    model.enable_input_require_grads()

    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        target_modules=LANGUAGE_MODEL_LORA_REGEX,
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    trainable = [
        name for name, parameter in model.named_parameters() if parameter.requires_grad
    ]
    if not trainable:
        raise RuntimeError("LoRA target regex matched no modules")
    if any("visual" in name or "mtp" in name for name in trainable):
        raise RuntimeError("LoRA unexpectedly matched a visual or MTP module")
    model.print_trainable_parameters()

    training_kwargs: dict[str, Any] = {
        "output_dir": str(args.output_dir / "checkpoints"),
        "run_name": args.run_name,
        "num_train_epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "per_device_train_batch_size": args.batch_size,
        "per_device_eval_batch_size": args.batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation,
        "bf16": True,
        "tf32": True,
        "gradient_checkpointing": True,
        "gradient_checkpointing_kwargs": {"use_reentrant": False},
        "optim": "adamw_torch_fused",
        "lr_scheduler_type": "cosine",
        "warmup_ratio": 0.05,
        "weight_decay": 0.01,
        "logging_strategy": "steps",
        "logging_steps": args.logging_steps,
        "eval_strategy": "steps",
        "eval_steps": args.eval_steps,
        "save_strategy": "steps",
        "save_steps": args.save_steps,
        "save_total_limit": 3,
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_loss",
        "greater_is_better": False,
        "report_to": "none",
        "remove_unused_columns": False,
        "dataloader_num_workers": 2,
        "dataloader_pin_memory": True,
        "seed": args.seed,
        "data_seed": args.seed,
    }
    # Transformers renamed evaluation_strategy to eval_strategy. This keeps the
    # script usable with either API exposed by the existing serving environment.
    signature = inspect.signature(TrainingArguments.__init__).parameters
    if "eval_strategy" not in signature:
        training_kwargs["evaluation_strategy"] = training_kwargs.pop("eval_strategy")
    training_args = TrainingArguments(**training_kwargs)

    trainer_kwargs: dict[str, Any] = {
        "model": model,
        "args": training_args,
        "train_dataset": train_dataset,
        "eval_dataset": eval_dataset,
        "data_collator": AssistantOnlyCollator(tokenizer.pad_token_id),
    }
    trainer_signature = inspect.signature(Trainer.__init__).parameters
    if "processing_class" in trainer_signature:
        trainer_kwargs["processing_class"] = tokenizer
    elif "tokenizer" in trainer_signature:
        trainer_kwargs["tokenizer"] = tokenizer
    trainer = Trainer(**trainer_kwargs)

    write_runtime_manifest(
        args.output_dir / "run_manifest.json",
        args,
        train_dataset,
        eval_dataset,
        model,
    )
    resume_checkpoint = (
        str(args.resume_from_checkpoint)
        if args.resume_from_checkpoint is not None
        else None
    )
    train_result = trainer.train(resume_from_checkpoint=resume_checkpoint)
    eval_metrics = trainer.evaluate()

    final_dir = args.output_dir / "final"
    trainer.save_model(final_dir)
    tokenizer.save_pretrained(final_dir)
    trainer.save_state()
    metrics = {
        "train": train_result.metrics,
        "eval": eval_metrics,
    }
    (args.output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
