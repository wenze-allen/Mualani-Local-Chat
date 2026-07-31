#!/usr/bin/env python3
"""Produce an exhaustive, compact quality review of the Mualani SFT dataset."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DATASET_ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_RE = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")
FILLER_ONLY_RE = re.compile(
    r"^[「『“\"']?(?:嗯+|唔+|呃+|诶+|欸+|啊+|哦+|哎+|哎呀|"
    r"哈哈+|嘿嘿+|好吧|好啊|行吧|是吗|这样啊|原来如此)"
    r"[」』”\"'，,。.!！?？…—~～\s]*$"
)
FILLER_START_RE = re.compile(
    r"^[「『“\"']?(?:嗯+|唔+|呃+|诶+|欸+|啊+|哦+|噢+|"
    r"哇+|咦+|呀+|哟(?:呼|吼|哈)?|呜呼|呼呀|啊哈|(?:哎呀)+|"
    r"哈哈+|嘿嘿+|好吧|好啊)[，,。.!！?？…—~～\s]"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=DATASET_ROOT / "work" / "training_data" / "sft_zh",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=(
            DATASET_ROOT
            / "work"
            / "mualani_corpus"
            / "combined"
            / "zh"
            / "mualani_training_candidates.jsonl"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DATASET_ROOT / "work" / "training_data" / "quality_review",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
    return rows


def one_line(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def semantic_length(text: str) -> int:
    return len(SEMANTIC_RE.findall(text))


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    source_by_id = {
        str(row.get("dialogue_id")): row for row in read_jsonl(args.source)
    }
    dataset_rows: list[tuple[str, dict[str, Any]]] = []
    for split in ("train", "validation", "test"):
        for row in read_jsonl(args.dataset_dir / f"{split}.jsonl"):
            dataset_rows.append((split, row))

    counts: Counter[str] = Counter()
    source_types: Counter[str] = Counter()
    last_speakers: Counter[str] = Counter()
    completion_lengths: list[int] = []
    completion_owners: dict[str, list[str]] = defaultdict(list)
    review_rows: list[dict[str, Any]] = []

    for split, dataset_row in dataset_rows:
        dialogue_id = str(dataset_row["metadata"]["dialogue_id"])
        source = source_by_id[dialogue_id]
        completion = one_line(dataset_row["completion"]["content"])
        context = source.get("context_before") or []
        last = context[-1] if context else {}
        last_speaker = one_line(last.get("speaker"))
        last_text = one_line(last.get("text"))
        source_type = one_line(source.get("source_type"))
        voice_group = one_line(source.get("voice_group"))
        voice_category = one_line(source.get("voice_category"))
        length = semantic_length(completion)
        flags: list[str] = []

        if not context and source_type != "CharacterVoice":
            flags.append("scene_without_context")
        if last_speaker == "玛拉妮":
            flags.append("continues_own_turn")
        if context and last_speaker not in {"旅行者", "Player"}:
            flags.append("last_speaker_not_traveler")
        if length <= 4:
            flags.append("completion_le4")
        elif length <= 8:
            flags.append("completion_le8")
        elif length <= 12:
            flags.append("completion_le12")
        if FILLER_ONLY_RE.fullmatch(completion):
            flags.append("filler_only")
        elif FILLER_START_RE.match(completion):
            flags.append("filler_start")
        if completion.endswith(("…", "——", "—")):
            flags.append("fragment_ending")
        if source_type == "CharacterVoice" and voice_group == "combat":
            flags.append("combat_voice")
        if source_type == "CharacterVoice" and voice_category in {
            "light_hit",
            "heavy_hit",
            "fallen",
            "low_hp",
            "ally_low_hp",
            "elemental_skill",
            "elemental_burst",
            "sprint",
            "climb",
            "glide",
            "open_chest",
        }:
            flags.append("situational_bark")

        for flag in flags:
            counts[flag] += 1
        source_types[source_type] += 1
        last_speakers[last_speaker or "<none>"] += 1
        completion_lengths.append(length)
        completion_owners[completion].append(dialogue_id)
        review_rows.append(
            {
                "id": dialogue_id,
                "split": split,
                "source_type": source_type,
                "scene_id": one_line(source.get("scene_id")),
                "title": one_line(source.get("title")),
                "last_speaker": last_speaker,
                "last_text": last_text,
                "completion": completion,
                "completion_semantic_length": length,
                "voice_group": voice_group,
                "voice_category": voice_category,
                "flags": flags,
            }
        )

    exact_duplicate_rows = sum(
        len(ids) for ids in completion_owners.values() if len(ids) > 1
    )
    exact_duplicate_texts = sum(
        1 for ids in completion_owners.values() if len(ids) > 1
    )
    sorted_lengths = sorted(completion_lengths)

    def percentile(fraction: float) -> int:
        index = round((len(sorted_lengths) - 1) * fraction)
        return sorted_lengths[index]

    summary = {
        "status": "review_generated",
        "dataset_dir": str(args.dataset_dir.resolve()),
        "source": str(args.source.resolve()),
        "rows_read": len(review_rows),
        "source_rows": len(source_by_id),
        "source_type_counts": dict(source_types),
        "last_speaker_counts": dict(last_speakers.most_common()),
        "flag_counts": dict(counts.most_common()),
        "completion_semantic_length": {
            "min": min(sorted_lengths),
            "median": percentile(0.5),
            "p90": percentile(0.9),
            "p95": percentile(0.95),
            "max": max(sorted_lengths),
        },
        "exact_duplicate_completion_texts": exact_duplicate_texts,
        "rows_with_exact_duplicate_completion": exact_duplicate_rows,
        "notes": [
            "Every dataset row and its source row was read.",
            "Flags are triage signals, not automatic deletion decisions.",
            "Semantic alignment still requires human review of last_text/completion.",
        ],
    }

    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (args.output_dir / "all_rows.jsonl").open(
        "w", encoding="utf-8"
    ) as handle:
        for row in review_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (args.output_dir / "all_rows.tsv").open(
        "w", encoding="utf-8"
    ) as handle:
        handle.write(
            "id\tsplit\ttype\tlast_speaker\tlast_text\tcompletion\tflags\n"
        )
        for row in review_rows:
            fields = [
                row["id"],
                row["split"],
                row["source_type"],
                row["last_speaker"],
                row["last_text"],
                row["completion"],
                ",".join(row["flags"]),
            ]
            handle.write("\t".join(field.replace("\t", " ") for field in fields) + "\n")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
