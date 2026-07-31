#!/usr/bin/env python3
"""Extract complete bilingual dialogue scenes in which Mualani actually appears.

This is intentionally different from the SFT corpus: the SFT extractor stores
Mualani lines plus bounded preceding context, while this audit stores every
dialogue and every branch in each scene containing a Mualani speaker node.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from extract_mualani_corpus import (
    SOURCE_PRIORITY,
    document_metadata,
    iter_scene_containers,
    recursively_count_target_nodes,
)


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "character_impressions" / "scope_audit",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
    temporary.replace(path)


def flatten_sequence(
    items: list[Any],
    *,
    player_name: str,
    branch_path: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "speaker" in item and "text" in item:
            turns.append(
                {
                    "id": str(item.get("id", "")),
                    "speaker": str(item.get("speaker", "")),
                    "text": str(item.get("text", "")),
                    "kind": "dialogue",
                    "branch_path": "/".join(branch_path),
                }
            )
        choices = item.get("choices")
        if not isinstance(choices, list):
            continue
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            choice_id = str(choice.get("id", ""))
            choice_branch = branch_path + (choice_id,)
            turns.append(
                {
                    "id": choice_id,
                    "speaker": player_name,
                    "text": str(choice.get("text", "")),
                    "kind": "choice",
                    "branch_path": "/".join(choice_branch),
                }
            )
            response = choice.get("response")
            if isinstance(response, list):
                turns.extend(
                    flatten_sequence(
                        response,
                        player_name=player_name,
                        branch_path=choice_branch,
                    )
                )
    return turns


def scene_id(scene: dict[str, Any], path: tuple[str, ...]) -> str:
    return str(
        scene.get("id")
        or scene.get("talkId")
        or scene.get("initDialog")
        or "/".join(path)
    )


def extract_language(
    source_root: Path,
    source_files: list[str],
    *,
    target: str,
    player_name: str,
) -> list[dict[str, Any]]:
    scenes: list[dict[str, Any]] = []
    for relative in source_files:
        path = source_root / relative
        if not path.is_file():
            continue
        document = load_json(path)
        metadata = document_metadata(document, Path(relative))
        for container_path, scene in iter_scene_containers(document):
            dialogues = scene.get("dialogues", [])
            if recursively_count_target_nodes(dialogues, target) == 0:
                continue
            turns = flatten_sequence(dialogues, player_name=player_name)
            mualani_ids = sorted(
                {
                    turn["id"]
                    for turn in turns
                    if target in turn["speaker"] and turn["id"]
                }
            )
            metadata_values = (
                str(metadata.get("title", "")),
                str(metadata.get("description", "")),
                str(scene.get("objective", "")),
            )
            scenes.append(
                {
                    "source_type": metadata["source_type"],
                    "source_file": metadata["source_file"],
                    "document_id": str(metadata.get("document_id", "")),
                    "title": str(metadata.get("title", "")),
                    "description": str(metadata.get("description", "")),
                    "chapter": metadata.get("chapter"),
                    "scene_id": scene_id(scene, container_path),
                    "scene_path": list(container_path),
                    "scene_objective": str(scene.get("objective", "")),
                    "mualani_dialogue_ids": mualani_ids,
                    "turns": turns,
                    "flags": {
                        "hidden": any("$HIDDEN" in value for value in metadata_values),
                        "test": any(
                            marker in value.lower()
                            for value in metadata_values
                            for marker in ("(test)", "（test）")
                        ),
                    },
                }
            )
    return scenes


def canonicalize_scenes(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for scene in scenes:
        key = tuple(scene["mualani_dialogue_ids"])
        if not key:
            key = (scene["source_file"], scene["scene_id"])
        grouped[key].append(scene)
    canonical = []
    for rows in grouped.values():
        rows.sort(
            key=lambda row: (
                SOURCE_PRIORITY.get(row["source_type"], 99),
                len(row["source_file"]),
                row["source_file"],
            )
        )
        selected = dict(rows[0])
        selected["duplicate_sources"] = sorted(
            {row["source_file"] for row in rows[1:]}
        )
        canonical.append(selected)
    canonical.sort(
        key=lambda row: (
            row["source_file"],
            row["scene_id"],
            row["mualani_dialogue_ids"],
        )
    )
    return canonical


def pair_scenes(
    zh_scenes: list[dict[str, Any]], en_scenes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    en_by_ids = {
        tuple(scene["mualani_dialogue_ids"]): scene for scene in en_scenes
    }
    output = []
    for zh in zh_scenes:
        en = en_by_ids.get(tuple(zh["mualani_dialogue_ids"]))
        en_turns = {
            turn["id"]: turn for turn in (en or {}).get("turns", []) if turn["id"]
        }
        turns = []
        for turn in zh["turns"]:
            counterpart = en_turns.get(turn["id"], {})
            turns.append(
                {
                    "dialogue_id": turn["id"],
                    "kind": turn["kind"],
                    "branch_path": turn["branch_path"],
                    "speaker_zh": turn["speaker"],
                    "text_zh": turn["text"],
                    "speaker_en": str(counterpart.get("speaker", "")),
                    "text_en": str(counterpart.get("text", "")),
                }
            )
        output.append(
            {
                "source_type": zh["source_type"],
                "source_file": zh["source_file"],
                "document_id": zh["document_id"],
                "title_zh": zh["title"],
                "title_en": str((en or {}).get("title", "")),
                "description_zh": zh["description"],
                "description_en": str((en or {}).get("description", "")),
                "chapter_zh": zh["chapter"],
                "chapter_en": (en or {}).get("chapter"),
                "scene_id": zh["scene_id"],
                "scene_path": zh["scene_path"],
                "scene_objective_zh": zh["scene_objective"],
                "scene_objective_en": str((en or {}).get("scene_objective", "")),
                "mualani_dialogue_ids": zh["mualani_dialogue_ids"],
                "turns": turns,
                "flags": zh["flags"],
                "duplicate_sources": zh["duplicate_sources"],
                "english_scene_found": en is not None,
            }
        )
    return output


def speaker_matches(speaker: str, aliases: list[str]) -> bool:
    folded = speaker.casefold()
    return any(
        folded == alias.casefold() or alias.casefold() in folded
        for alias in aliases
        if alias
    )


def contains_alias(text: str, aliases: list[str]) -> bool:
    folded = text.casefold()
    for alias in aliases:
        if len(alias) < 2:
            continue
        value = alias.casefold()
        if value.isascii() and value.replace(" ", "").isalpha():
            if re.search(rf"(?<![a-z]){re.escape(value)}(?![a-z])", folded):
                return True
        elif value in folded:
            return True
    return False


def inventory(
    scenes: list[dict[str, Any]], candidates: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    speakers: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        seen_in_scene = set()
        for turn in scene["turns"]:
            speaker = turn["speaker_zh"]
            if not speaker:
                continue
            entry = speakers.setdefault(
                speaker,
                {
                    "speaker_zh": speaker,
                    "speaker_en_names": Counter(),
                    "scene_ids": set(),
                    "dialogue_count": 0,
                    "direct_adjacency_with_mualani": 0,
                },
            )
            if turn["speaker_en"]:
                entry["speaker_en_names"][turn["speaker_en"]] += 1
            entry["dialogue_count"] += 1
            seen_in_scene.add(speaker)
        for speaker in seen_in_scene:
            speakers[speaker]["scene_ids"].add(
                f"{scene['source_file']}#{scene['scene_id']}"
            )
        turns = scene["turns"]
        for first, second in zip(turns, turns[1:]):
            if first["branch_path"] != second["branch_path"]:
                continue
            first_m = "玛拉妮" in first["speaker_zh"]
            second_m = "玛拉妮" in second["speaker_zh"]
            if first_m == second_m:
                continue
            other = second if first_m else first
            if other["speaker_zh"]:
                speakers[other["speaker_zh"]][
                    "direct_adjacency_with_mualani"
                ] += 1
    speaker_rows = []
    for entry in speakers.values():
        speaker_rows.append(
            {
                "speaker_zh": entry["speaker_zh"],
                "speaker_en": (
                    entry["speaker_en_names"].most_common(1)[0][0]
                    if entry["speaker_en_names"]
                    else ""
                ),
                "scene_count": len(entry["scene_ids"]),
                "dialogue_count": entry["dialogue_count"],
                "direct_adjacency_with_mualani": entry[
                    "direct_adjacency_with_mualani"
                ],
                "scene_ids": sorted(entry["scene_ids"]),
            }
        )
    speaker_rows.sort(
        key=lambda row: (-row["scene_count"], -row["dialogue_count"], row["speaker_zh"])
    )

    intersections = []
    for candidate in candidates:
        aliases_zh = candidate["aliases_zh"]
        aliases_en = candidate["aliases_en"]
        forbidden = {
            alias.casefold() for alias in candidate.get("forbidden_aliases", [])
        }
        aliases_zh = [
            alias for alias in aliases_zh if alias.casefold() not in forbidden
        ]
        aliases_en = [
            alias for alias in aliases_en if alias.casefold() not in forbidden
        ]
        matched_scenes = []
        direct_count = 0
        mention_ids = []
        speaker_turn_count = 0
        for scene in scenes:
            scene_reasons = set()
            for turn in scene["turns"]:
                if speaker_matches(turn["speaker_zh"], aliases_zh) or speaker_matches(
                    turn["speaker_en"], aliases_en
                ):
                    speaker_turn_count += 1
                    scene_reasons.add("candidate_speaks")
                if "玛拉妮" in turn["speaker_zh"] and (
                    contains_alias(turn["text_zh"], aliases_zh)
                    or contains_alias(turn["text_en"], aliases_en)
                ):
                    mention_ids.append(turn["dialogue_id"])
                    scene_reasons.add("mualani_names_candidate")
            turns = scene["turns"]
            for first, second in zip(turns, turns[1:]):
                if first["branch_path"] != second["branch_path"]:
                    continue
                first_m = "玛拉妮" in first["speaker_zh"]
                second_m = "玛拉妮" in second["speaker_zh"]
                direct = (
                    first_m
                    and (
                        speaker_matches(second["speaker_zh"], aliases_zh)
                        or speaker_matches(second["speaker_en"], aliases_en)
                    )
                ) or (
                    second_m
                    and (
                        speaker_matches(first["speaker_zh"], aliases_zh)
                        or speaker_matches(first["speaker_en"], aliases_en)
                    )
                )
                if direct:
                    direct_count += 1
                    scene_reasons.add("direct_adjacency")
            if scene_reasons:
                matched_scenes.append(
                    {
                        "source_file": scene["source_file"],
                        "scene_id": scene["scene_id"],
                        "title_zh": scene["title_zh"],
                        "reasons": sorted(scene_reasons),
                    }
                )
        intersections.append(
            {
                "character_id": candidate["character_id"],
                "name_zh": candidate["name_zh"],
                "name_en": candidate["name_en"],
                "roster_type": candidate["roster_type"],
                "matched_scene_count": len(matched_scenes),
                "speaker_turn_count": speaker_turn_count,
                "direct_adjacency_count": direct_count,
                "mualani_name_mention_count": len(set(mention_ids)),
                "mualani_name_mention_dialogue_ids": sorted(set(mention_ids)),
                "matched_scenes": matched_scenes,
            }
        )
    intersections.sort(
        key=lambda row: (
            -int(row["matched_scene_count"] > 0),
            -row["direct_adjacency_count"],
            -row["mualani_name_mention_count"],
            row["character_id"],
        )
    )
    return {
        "scene_count": len(scenes),
        "unique_speaker_labels": len(speaker_rows),
        "speakers": speaker_rows,
    }, intersections


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    source_files = [
        line.strip()
        for line in (
            root / "mualani_corpus" / "zh" / "source_files.txt"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    zh_raw = extract_language(
        root / "YuanShenResources" / "DialogsText" / "CHS",
        source_files,
        target="玛拉妮",
        player_name="旅行者",
    )
    en_raw = extract_language(
        root / "YuanShenResources" / "DialogsText" / "EN",
        source_files,
        target="Mualani",
        player_name="Traveler",
    )
    zh_scenes = canonicalize_scenes(zh_raw)
    en_scenes = canonicalize_scenes(en_raw)
    paired = pair_scenes(zh_scenes, en_scenes)
    candidates = load_json(
        root / "character_impressions" / "candidates.json"
    )["candidates"]
    speaker_inventory, intersections = inventory(paired, candidates)
    write_jsonl(output / "mualani_full_scenes.jsonl", paired)
    write_json(output / "speaker_inventory.json", speaker_inventory)
    write_json(output / "candidate_intersections.json", intersections)
    write_json(
        output / "manifest.json",
        {
            "schema_version": "mualani-full-scene-audit-v1",
            "source_commit": (
                root / "mualani_corpus" / "README.md"
            ).read_text(encoding="utf-8").split("`")[1],
            "source_file_count": len(source_files),
            "raw_zh_scene_count": len(zh_raw),
            "raw_en_scene_count": len(en_raw),
            "canonical_scene_count": len(paired),
            "english_paired_scene_count": sum(
                scene["english_scene_found"] for scene in paired
            ),
            "candidate_count": len(candidates),
        },
    )
    print(
        f"Extracted {len(paired)} complete Mualani scenes; "
        f"{speaker_inventory['unique_speaker_labels']} speaker labels."
    )


if __name__ == "__main__":
    main()
