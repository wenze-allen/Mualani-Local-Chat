#!/usr/bin/env python3
"""Exhaustively validate every generated SFT row and audit gender branches."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DATASET_ROOT = Path(__file__).resolve().parents[1]
PREPARE_PATH = DATASET_ROOT / "builders" / "prepare_mualani_sft.py"
SPEC = importlib.util.spec_from_file_location("prepare_mualani_sft", PREPARE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {PREPARE_PATH}")
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


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
        "--report",
        type=Path,
        default=DATASET_ROOT / "work" / "training_data" / "sft_zh" / "audit_report.json",
    )
    parser.add_argument(
        "--gender-review",
        type=Path,
        default=DATASET_ROOT / "work" / "training_data" / "sft_zh" / "gender_review.jsonl",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AssertionError(f"{path}:{line_number}: invalid JSON") from exc
            row["_audit_line"] = line_number
            rows.append(row)
    return rows


def iter_source_strings(row: dict[str, Any]):
    yield "completion", str(row.get("text") or "")
    for index, context in enumerate(row.get("context_before") or []):
        yield f"context_before[{index}]", str(context.get("text") or "")


def assert_clean_text(text: str, location: str) -> None:
    if not text.strip():
        raise AssertionError(f"{location}: empty content")
    if re.search(r"\{(?:M|F|RUBY|NICKNAME)#?", text):
        raise AssertionError(f"{location}: unresolved game markup: {text}")
    if "{NICKNAME}" in text:
        raise AssertionError(f"{location}: unresolved nickname: {text}")
    if re.search(r"(?m)^#+", text):
        raise AssertionError(f"{location}: leading game marker on a line: {text}")
    if "\ufffd" in text:
        raise AssertionError(f"{location}: Unicode replacement character")
    if any(ord(character) < 32 and character not in "\n\t" for character in text):
        raise AssertionError(f"{location}: forbidden control character")


def main() -> None:
    args = parse_args()
    manifest_path = args.dataset_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    quality_profile = str(manifest.get("quality_profile") or "legacy")
    split_rows: dict[str, list[dict[str, Any]]] = {}
    all_ids: set[str] = set()
    covered_source_ids: set[str] = set()
    group_owners: dict[str, str] = {}
    completion_owners: dict[tuple[str, str], str] = {}
    text_characters = 0
    completion_characters = 0

    for split in ("train", "validation", "test"):
        path = args.dataset_dir / f"{split}.jsonl"
        rows = read_jsonl(path)
        split_rows[split] = rows
        for row in rows:
            line_number = row.pop("_audit_line")
            location = f"{path}:{line_number}"
            row_id = row.get("id")
            if not isinstance(row_id, str) or row_id in all_ids:
                raise AssertionError(f"{location}: missing or duplicate id: {row_id}")
            all_ids.add(row_id)

            group = row.get("group_id")
            if not isinstance(group, str):
                raise AssertionError(f"{location}: invalid group_id")
            owner = group_owners.setdefault(group, split)
            if owner != split:
                raise AssertionError(
                    f"{location}: group leakage between {owner} and {split}: {group}"
                )

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
                raise AssertionError(f"{location}: invalid assistant-only schema")

            for message_index, message in enumerate(prompt):
                content = message.get("content")
                if not isinstance(content, str):
                    raise AssertionError(f"{location}: prompt content is not text")
                assert_clean_text(content, f"{location}:prompt[{message_index}]")
                text_characters += len(content)
            content = completion.get("content")
            if not isinstance(content, str):
                raise AssertionError(f"{location}: completion is not text")
            assert_clean_text(content, f"{location}:completion")
            if PREPARE.substantive_completion(content):
                completion_key = (
                    str(row.get("language")),
                    re.sub(r"\s+", " ", content).strip(),
                )
                completion_owner = completion_owners.setdefault(
                    completion_key, split
                )
                if completion_owner != split:
                    raise AssertionError(
                        f"{location}: exact substantive completion leakage "
                        f"between {completion_owner} and {split}: {content}"
                    )
            text_characters += len(content)
            completion_characters += len(content)
            merged_ids = row.get("metadata", {}).get("merged_dialogue_ids")
            if isinstance(merged_ids, list):
                covered_source_ids.update(str(value) for value in merged_ids)
            else:
                dialogue_id = row.get("metadata", {}).get("dialogue_id")
                if dialogue_id is not None:
                    covered_source_ids.add(str(dialogue_id))

            if quality_profile == "chat-v2":
                source_type = row.get("metadata", {}).get("source_type")
                user_content = str(prompt[1].get("content") or "")
                semantic_length = len(
                    re.findall(r"[\u3400-\u9fffA-Za-z0-9]", content)
                )
                if semantic_length < 10:
                    raise AssertionError(
                        f"{location}: chat-v2 completion below minimum length"
                    )
                if content.rstrip().endswith(("…", "——", "—")):
                    raise AssertionError(
                        f"{location}: chat-v2 completion has fragment ending"
                    )
                if (
                    source_type != "CharacterVoice"
                    and "【必须回应的最后一句】" not in user_content
                ):
                    raise AssertionError(
                        f"{location}: chat-v2 scene lacks explicit last line"
                    )
                if row.get("metadata", {}).get("voice_category") and re.search(
                    r"【战斗情景：", user_content
                ):
                    raise AssertionError(
                        f"{location}: chat-v2 retained combat voice"
                    )

    gender_entries: dict[str, dict[str, Any]] = {}
    raw_gender_occurrences = 0
    raw_nickname_occurrences = 0
    male_forms: Counter[str] = Counter()
    female_forms: Counter[str] = Counter()
    pair_pattern = re.compile(r"\{M#([^{}]*)\}\{F#([^{}]*)\}")
    source_rows = read_jsonl(args.source)
    source_ids = {str(source_row.get("dialogue_id")) for source_row in source_rows}
    if quality_profile == "legacy":
        expected_ids = {f"zh:{source_id}" for source_id in source_ids}
        if all_ids != expected_ids:
            missing = sorted(expected_ids - all_ids)
            unexpected = sorted(all_ids - expected_ids)
            raise AssertionError(
                f"generated/source ID mismatch; missing={missing[:10]}, "
                f"unexpected={unexpected[:10]}"
            )
    elif not covered_source_ids <= source_ids:
        raise AssertionError(
            "chat-v2 references source dialogue IDs absent from the source corpus"
        )

    for source_row in source_rows:
        source_row.pop("_audit_line")
        for location, raw in iter_source_strings(source_row):
            raw_nickname_occurrences += raw.count("{NICKNAME}")
            pairs = pair_pattern.findall(raw)
            if not pairs:
                continue
            raw_gender_occurrences += 1
            for male, female in pairs:
                male_forms[male] += 1
                female_forms[female] += 1
            resolved = PREPARE.resolve_game_markup(raw, "zh", "male")
            assert_clean_text(resolved, f"gender resolution:{source_row.get('dialogue_id')}")
            entry = gender_entries.setdefault(
                raw,
                {
                    "raw": raw,
                    "resolved_male": resolved,
                    "male_branches": [male for male, _ in pairs],
                    "female_branches": [female for _, female in pairs],
                    "occurrences": 0,
                    "examples": [],
                },
            )
            entry["occurrences"] += 1
            if len(entry["examples"]) < 5:
                entry["examples"].append(
                    {
                        "dialogue_id": source_row.get("dialogue_id"),
                        "location": location,
                    }
                )

    with args.gender_review.open("w", encoding="utf-8") as handle:
        for entry in gender_entries.values():
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    report = {
        "status": "passed",
        "dataset_dir": str(args.dataset_dir.resolve()),
        "quality_profile": quality_profile,
        "all_rows_read": sum(len(rows) for rows in split_rows.values()),
        "split_rows": {split: len(rows) for split, rows in split_rows.items()},
        "unique_ids": len(all_ids),
        "unique_groups": len(group_owners),
        "all_message_characters_read": text_characters,
        "completion_characters_read": completion_characters,
        "unresolved_game_markup": 0,
        "cross_split_group_leakage": 0,
        "cross_split_exact_substantive_completion_leakage": 0,
        "gender_audit": {
            "source_strings_with_gender_branches": raw_gender_occurrences,
            "unique_source_strings": len(gender_entries),
            "male_branch_forms": dict(male_forms),
            "female_branch_forms": dict(female_forms),
            "selected_branch": "male",
            "review_file": str(args.gender_review.resolve()),
        },
        "nickname_audit": {
            "source_occurrences": raw_nickname_occurrences,
            "replacement": "旅行者",
            "unresolved_output_occurrences": 0,
        },
        "source_coverage": {
            "source_rows": len(source_ids),
            "covered_source_rows": len(covered_source_ids),
            "excluded_source_rows": len(source_ids - covered_source_ids),
        },
    }
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
