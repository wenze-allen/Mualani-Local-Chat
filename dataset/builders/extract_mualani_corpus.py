#!/usr/bin/env python3
"""Extract all Mualani dialogue lines from YuanShenResources.

The source repository repeats some dialogue records in aggregate and atomic
files (for example ActivityGroup/Activity and NpcGroup/Npc).  This script keeps
an audit file with every occurrence, then creates a canonical corpus keyed by
the globally stable dialogue id.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


LANGUAGE_CONFIG = {
    "zh": {
        "source_dir": "CHS",
        "target": "玛拉妮",
        "player": "旅行者",
    },
    "en": {
        "source_dir": "EN",
        "target": "Mualani",
        "player": "Traveler",
    },
}

DATASET_ROOT = Path(__file__).resolve().parents[1]

# Prefer files with richer task metadata, and prefer atomic files over their
# aggregate Group equivalents when the same dialogue id occurs more than once.
SOURCE_PRIORITY = {
    "Quest": 0,
    "Activity": 1,
    "Storyboard": 2,
    "FreeGroup": 3,
    "Npc": 4,
    "NpcOther": 5,
    "Gadget": 6,
    "Blossom": 7,
    "ActivityGroup": 20,
    "NpcGroup": 21,
    "GadgetGroup": 22,
}

MARKUP_RE = re.compile(r"(?:\{[^{}]+\}|<[^>]+>|^#)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo",
        type=Path,
        default=DATASET_ROOT / "work" / "YuanShenResources",
        help="Path to the sparse-cloned YuanShenResources repository.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATASET_ROOT / "work" / "mualani_corpus",
        help="Output directory.",
    )
    parser.add_argument(
        "--context-turns",
        type=int,
        default=8,
        help="Maximum number of structurally valid preceding turns to retain.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False))
            handle.write("\n")


def write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line)
            handle.write("\n")


def source_type(relative_path: Path) -> str:
    return relative_path.parts[0] if relative_path.parts else "Unknown"


def document_metadata(document: Any, relative_path: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source_type": source_type(relative_path),
        "source_file": relative_path.as_posix(),
    }
    if not isinstance(document, dict):
        return metadata

    quest = document.get("quest")
    if isinstance(quest, dict):
        chapter = quest.get("chapter")
        metadata.update(
            {
                "document_id": str(quest.get("id", "")),
                "title": quest.get("title", ""),
                "description": quest.get("description", ""),
                "chapter": chapter if isinstance(chapter, dict) else None,
            }
        )
        return metadata

    for field in ("talkId", "groupId", "id"):
        if field in document:
            metadata["document_id"] = str(document[field])
            break
    metadata.setdefault("title", "")
    metadata.setdefault("description", "")
    metadata.setdefault("chapter", None)
    return metadata


def iter_scene_containers(
    value: Any, path: tuple[str, ...] = ()
) -> Iterable[tuple[tuple[str, ...], dict[str, Any]]]:
    """Yield every dict that directly owns a dialogue sequence."""
    if isinstance(value, dict):
        dialogues = value.get("dialogues")
        if isinstance(dialogues, list):
            yield path, value
            # Dialogue entries cannot own another `dialogues` list, but other
            # metadata fields occasionally can contain nested talk containers.
            for key, child in value.items():
                if key != "dialogues":
                    yield from iter_scene_containers(child, path + (str(key),))
            return
        for key, child in value.items():
            yield from iter_scene_containers(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_scene_containers(child, path + (str(index),))


def target_in_speaker(speaker: Any, target: str) -> bool:
    return isinstance(speaker, str) and target in speaker


def compact_turn(item: dict[str, Any], kind: str = "dialogue") -> dict[str, str]:
    return {
        "id": str(item.get("id", "")),
        "speaker": str(item.get("speaker", "")),
        "text": str(item.get("text", "")),
        "kind": kind,
    }


def walk_sequence(
    items: list[Any],
    *,
    target: str,
    player_name: str,
    base_context: list[dict[str, str]],
    branch_path: tuple[str, ...],
    context_turns: int,
    callback: Any,
) -> None:
    """Walk choices without creating a Cartesian product at reconvergence.

    A target line inside a response branch receives that choice and its response
    prefix as context.  Once a branch ends, later common dialogue continues from
    the pre-choice context because the source JSON does not state which branch
    should be considered canonical.
    """
    context = list(base_context)
    for item in items:
        if not isinstance(item, dict):
            continue

        has_dialogue_shape = "speaker" in item and "text" in item
        if has_dialogue_shape:
            turn = compact_turn(item)
            if target_in_speaker(item.get("speaker"), target):
                callback(item, context[-context_turns:], branch_path)
            context.append(turn)
            context = context[-context_turns:]

        choices = item.get("choices")
        if not isinstance(choices, list):
            continue

        for choice in choices:
            if not isinstance(choice, dict):
                continue
            choice_id = str(choice.get("id", ""))
            choice_turn = {
                "id": choice_id,
                "speaker": player_name,
                "text": str(choice.get("text", "")),
                "kind": "choice",
            }
            response = choice.get("response")
            if not isinstance(response, list):
                response = []
            walk_sequence(
                response,
                target=target,
                player_name=player_name,
                base_context=(context + [choice_turn])[-context_turns:],
                branch_path=branch_path + (choice_id,),
                context_turns=context_turns,
                callback=callback,
            )


def recursively_count_target_nodes(value: Any, target: str) -> int:
    if isinstance(value, dict):
        count = int(
            target_in_speaker(value.get("speaker"), target) and "text" in value
        )
        return count + sum(
            recursively_count_target_nodes(child, target) for child in value.values()
        )
    if isinstance(value, list):
        return sum(recursively_count_target_nodes(child, target) for child in value)
    return 0


def extract_language(
    source_root: Path,
    language: str,
    target: str,
    player_name: str,
    context_turns: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    scanned_files = 0
    files_with_target: set[str] = set()
    raw_target_nodes = 0
    parse_errors: list[dict[str, str]] = []

    for path in sorted(source_root.rglob("*.json")):
        scanned_files += 1
        relative_path = path.relative_to(source_root)
        try:
            document = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            parse_errors.append(
                {"source_file": relative_path.as_posix(), "error": str(exc)}
            )
            continue

        file_target_nodes = recursively_count_target_nodes(document, target)
        if not file_target_nodes:
            continue
        raw_target_nodes += file_target_nodes
        files_with_target.add(relative_path.as_posix())
        doc_meta = document_metadata(document, relative_path)
        extracted_in_file = 0

        for scene_path, scene in iter_scene_containers(document):
            scene_id = str(
                scene.get("id")
                or scene.get("talkId")
                or scene.get("initDialog")
                or "/".join(scene_path)
            )
            scene_objective = str(scene.get("objective", ""))

            def collect(
                item: dict[str, Any],
                context_before: list[dict[str, str]],
                branch_path: tuple[str, ...],
            ) -> None:
                nonlocal extracted_in_file
                speaker = str(item.get("speaker", ""))
                text = str(item.get("text", ""))
                dialogue_id = str(item.get("id", ""))
                metadata_values = (
                    str(doc_meta.get("title", "")),
                    str(doc_meta.get("description", "")),
                    scene_objective,
                )
                flags = {
                    "joint_speaker": speaker != target,
                    "contains_markup": bool(MARKUP_RE.search(text)),
                    "contains_hidden_marker": any(
                        "$HIDDEN" in value for value in metadata_values
                    ),
                    "text_test_marker": any(
                        marker in text for marker in ("(test)", "（test）")
                    ),
                    "metadata_test_marker": any(
                        marker in value
                        for marker in ("(test)", "（test）")
                        for value in metadata_values
                    ),
                    "discarded_marker": any(
                        (
                            "(test)" in value.lower()
                            or "（test）" in value.lower()
                        )
                        and (
                            "废弃" in value
                            or "discarded" in value.lower()
                            or "deprecated" in value.lower()
                        )
                        for value in metadata_values
                    ),
                    "empty_text": not bool(text.strip()),
                }
                occurrences.append(
                    {
                        "language": language,
                        "character": target,
                        "dialogue_id": dialogue_id,
                        "speaker": speaker,
                        "text": text,
                        "source_type": doc_meta["source_type"],
                        "source_file": doc_meta["source_file"],
                        "document_id": doc_meta.get("document_id", ""),
                        "title": doc_meta.get("title", ""),
                        "description": doc_meta.get("description", ""),
                        "chapter": doc_meta.get("chapter"),
                        "scene_id": scene_id,
                        "scene_objective": scene_objective,
                        "scene_path": list(scene_path),
                        "branch_path": list(branch_path),
                        "context_before": context_before,
                        "flags": flags,
                    }
                )
                extracted_in_file += 1

            walk_sequence(
                scene["dialogues"],
                target=target,
                player_name=player_name,
                base_context=[],
                branch_path=(),
                context_turns=context_turns,
                callback=collect,
            )

        if extracted_in_file != file_target_nodes:
            raise RuntimeError(
                f"{relative_path}: found {file_target_nodes} target nodes but "
                f"extracted {extracted_in_file} from dialogue containers"
            )

    occurrences.sort(
        key=lambda row: (
            row["source_file"],
            row["scene_id"],
            row["dialogue_id"],
            row["branch_path"],
        )
    )
    report = {
        "language": language,
        "target": target,
        "scanned_json_files": scanned_files,
        "source_files_with_target": len(files_with_target),
        "raw_target_nodes": raw_target_nodes,
        "extracted_occurrences": len(occurrences),
        "parse_errors": parse_errors,
    }
    return occurrences, report


def canonicalize(
    occurrences: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(occurrences):
        dialogue_id = row["dialogue_id"]
        key = dialogue_id if dialogue_id else f"missing-id:{index}:{row['source_file']}"
        grouped[key].append(row)

    canonical_rows: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        rows.sort(
            key=lambda row: (
                SOURCE_PRIORITY.get(row["source_type"], 99),
                len(row["source_file"]),
                row["source_file"],
            )
        )
        distinct_texts = sorted({row["text"] for row in rows})
        distinct_speakers = sorted({row["speaker"] for row in rows})
        if len(distinct_texts) > 1 or len(distinct_speakers) > 1:
            conflicts.append(
                {
                    "dialogue_id": key,
                    "texts": distinct_texts,
                    "speakers": distinct_speakers,
                    "source_files": sorted({row["source_file"] for row in rows}),
                }
            )
        selected = dict(rows[0])
        selected["duplicate_sources"] = sorted(
            {row["source_file"] for row in rows[1:]}
        )
        selected["source_occurrence_count"] = len(rows)
        canonical_rows.append(selected)

    canonical_rows.sort(
        key=lambda row: (
            int(row["dialogue_id"]) if row["dialogue_id"].isdigit() else 10**30,
            row["dialogue_id"],
        )
    )
    conflicts.sort(key=lambda row: row["dialogue_id"])
    return canonical_rows, conflicts


def unique_text_rows(
    canonical_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in canonical_rows:
        normalized = " ".join(row["text"].split())
        grouped[normalized].append(row)

    unique_rows: list[dict[str, Any]] = []
    for normalized_text, rows in grouped.items():
        selected = dict(rows[0])
        selected["normalized_text"] = normalized_text
        selected["duplicate_dialogue_ids"] = [
            row["dialogue_id"] for row in rows[1:]
        ]
        selected["text_occurrence_count"] = len(rows)
        unique_rows.append(selected)
    unique_rows.sort(
        key=lambda row: (
            int(row["dialogue_id"]) if row["dialogue_id"].isdigit() else 10**30,
            row["dialogue_id"],
        )
    )
    return unique_rows


def compact_parallel_side(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "speaker": row["speaker"],
        "text": row["text"],
        "source_type": row["source_type"],
        "source_file": row["source_file"],
        "title": row["title"],
        "scene_id": row["scene_id"],
        "scene_objective": row["scene_objective"],
        "context_before": row["context_before"],
        "flags": row["flags"],
    }


def align_languages(
    zh_rows: list[dict[str, Any]], en_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    zh_by_id = {row["dialogue_id"]: row for row in zh_rows}
    en_by_id = {row["dialogue_id"]: row for row in en_rows}
    paired_ids = sorted(
        zh_by_id.keys() & en_by_id.keys(),
        key=lambda value: int(value) if value.isdigit() else 10**30,
    )
    paired = [
        {
            "dialogue_id": dialogue_id,
            "zh": compact_parallel_side(zh_by_id[dialogue_id]),
            "en": compact_parallel_side(en_by_id[dialogue_id]),
        }
        for dialogue_id in paired_ids
    ]
    zh_only = [
        zh_by_id[key]
        for key in sorted(
            zh_by_id.keys() - en_by_id.keys(),
            key=lambda value: int(value) if value.isdigit() else 10**30,
        )
    ]
    en_only = [
        en_by_id[key]
        for key in sorted(
            en_by_id.keys() - zh_by_id.keys(),
            key=lambda value: int(value) if value.isdigit() else 10**30,
        )
    ]
    return paired, zh_only, en_only


def training_exclusion_reasons(
    zh_row: dict[str, Any],
    en_row: dict[str, Any],
    *,
    strict: bool,
) -> list[str]:
    reasons: list[str] = []
    excluded_flags = [
        "text_test_marker",
        "discarded_marker",
        "empty_text",
        "joint_speaker",
    ]
    if strict:
        excluded_flags.append("metadata_test_marker")
    for flag in excluded_flags:
        if zh_row["flags"].get(flag) or en_row["flags"].get(flag):
            reasons.append(flag)
    return reasons


def source_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(row["source_type"] for row in rows).items()))


def flag_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        for flag, enabled in row["flags"].items():
            if enabled:
                counts[flag] += 1
    return dict(sorted(counts.items()))


def main() -> None:
    args = parse_args()
    repo = args.repo.resolve()
    output = args.output.resolve()
    dialogs_root = repo / "DialogsText"
    if not dialogs_root.is_dir():
        raise SystemExit(f"DialogsText directory not found under {repo}")

    language_outputs: dict[str, dict[str, Any]] = {}
    for language, config in LANGUAGE_CONFIG.items():
        source_root = dialogs_root / config["source_dir"]
        occurrences, scan_report = extract_language(
            source_root,
            language,
            config["target"],
            config["player"],
            args.context_turns,
        )
        canonical, conflicts = canonicalize(occurrences)
        unique = unique_text_rows(canonical)
        language_outputs[language] = {
            "occurrences": occurrences,
            "canonical": canonical,
            "unique": unique,
            "conflicts": conflicts,
            "scan_report": scan_report,
        }

        language_dir = output / language
        write_jsonl(
            language_dir / "mualani_occurrences_with_duplicates.jsonl",
            occurrences,
        )
        write_jsonl(language_dir / "mualani_all.jsonl", canonical)
        write_jsonl(language_dir / "mualani_unique_text.jsonl", unique)
        write_lines(
            language_dir / "source_files.txt",
            sorted({row["source_file"] for row in occurrences}),
        )
        write_json(language_dir / "deduplication_conflicts.json", conflicts)

    paired, zh_only, en_only = align_languages(
        language_outputs["zh"]["canonical"],
        language_outputs["en"]["canonical"],
    )
    write_jsonl(output / "parallel" / "mualani_zh_en.jsonl", paired)
    write_jsonl(output / "reports" / "unpaired_zh.jsonl", zh_only)
    write_jsonl(output / "reports" / "unpaired_en.jsonl", en_only)

    zh_by_id = {
        row["dialogue_id"]: row for row in language_outputs["zh"]["canonical"]
    }
    en_by_id = {
        row["dialogue_id"]: row for row in language_outputs["en"]["canonical"]
    }
    training_ids: list[str] = []
    strict_training_ids: list[str] = []
    excluded_training_rows: list[dict[str, Any]] = []
    strict_excluded_training_rows: list[dict[str, Any]] = []
    for pair in paired:
        dialogue_id = pair["dialogue_id"]
        reasons = training_exclusion_reasons(
            zh_by_id[dialogue_id], en_by_id[dialogue_id], strict=False
        )
        if reasons:
            excluded_training_rows.append(
                {
                    "dialogue_id": dialogue_id,
                    "reasons": reasons,
                    "zh": compact_parallel_side(zh_by_id[dialogue_id]),
                    "en": compact_parallel_side(en_by_id[dialogue_id]),
                }
            )
        else:
            training_ids.append(dialogue_id)

        strict_reasons = training_exclusion_reasons(
            zh_by_id[dialogue_id], en_by_id[dialogue_id], strict=True
        )
        if strict_reasons:
            strict_excluded_training_rows.append(
                {
                    "dialogue_id": dialogue_id,
                    "reasons": strict_reasons,
                    "zh": compact_parallel_side(zh_by_id[dialogue_id]),
                    "en": compact_parallel_side(en_by_id[dialogue_id]),
                }
            )
        else:
            strict_training_ids.append(dialogue_id)

    training_zh = [zh_by_id[dialogue_id] for dialogue_id in training_ids]
    training_en = [en_by_id[dialogue_id] for dialogue_id in training_ids]
    training_id_set = set(training_ids)
    training_parallel = [
        pair for pair in paired if pair["dialogue_id"] in training_id_set
    ]
    strict_training_zh = [
        zh_by_id[dialogue_id] for dialogue_id in strict_training_ids
    ]
    strict_training_en = [
        en_by_id[dialogue_id] for dialogue_id in strict_training_ids
    ]
    strict_training_id_set = set(strict_training_ids)
    strict_training_parallel = [
        pair for pair in paired if pair["dialogue_id"] in strict_training_id_set
    ]
    write_jsonl(
        output / "zh" / "mualani_training_candidates.jsonl", training_zh
    )
    write_jsonl(
        output / "en" / "mualani_training_candidates.jsonl", training_en
    )
    write_jsonl(
        output / "parallel" / "mualani_zh_en_training_candidates.jsonl",
        training_parallel,
    )
    write_jsonl(
        output / "zh" / "mualani_training_candidates_strict.jsonl",
        strict_training_zh,
    )
    write_jsonl(
        output / "en" / "mualani_training_candidates_strict.jsonl",
        strict_training_en,
    )
    write_jsonl(
        output
        / "parallel"
        / "mualani_zh_en_training_candidates_strict.jsonl",
        strict_training_parallel,
    )
    write_jsonl(
        output / "reports" / "excluded_from_training_candidates.jsonl",
        excluded_training_rows,
    )
    write_jsonl(
        output
        / "reports"
        / "excluded_from_training_candidates_strict.jsonl",
        strict_excluded_training_rows,
    )

    stats: dict[str, Any] = {
        "source_repository": "https://gitlab.com/GuraFoundation/YuanShenResources",
        "source_commit": "",
        "context_turns": args.context_turns,
        "languages": {},
        "parallel": {
            "paired_dialogue_ids": len(paired),
            "zh_only_dialogue_ids": len(zh_only),
            "en_only_dialogue_ids": len(en_only),
            "training_candidate_dialogue_ids": len(training_ids),
            "excluded_training_candidate_dialogue_ids": len(
                excluded_training_rows
            ),
            "strict_training_candidate_dialogue_ids": len(strict_training_ids),
            "strict_excluded_training_candidate_dialogue_ids": len(
                strict_excluded_training_rows
            ),
        },
    }
    head_path = repo / ".git" / "HEAD"
    if head_path.exists():
        head_value = head_path.read_text(encoding="utf-8").strip()
        if head_value.startswith("ref: "):
            ref_path = repo / ".git" / head_value.removeprefix("ref: ")
            if ref_path.exists():
                stats["source_commit"] = ref_path.read_text(encoding="utf-8").strip()
        else:
            stats["source_commit"] = head_value

    for language, values in language_outputs.items():
        canonical = values["canonical"]
        stats["languages"][language] = {
            **values["scan_report"],
            "canonical_dialogue_ids": len(canonical),
            "unique_texts": len(values["unique"]),
            "deduplication_conflicts": len(values["conflicts"]),
            "canonical_source_type_counts": source_counts(canonical),
            "canonical_flag_counts": flag_counts(canonical),
        }

    write_json(output / "stats.json", stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
