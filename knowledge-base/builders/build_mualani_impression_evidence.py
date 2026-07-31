#!/usr/bin/env python3
"""Build bilingual evidence bundles for Mualani impression-card candidates."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=ROOT, help="Project root containing mualani_corpus."
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=ROOT / "character_impressions" / "candidates.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "character_impressions" / "evidence",
    )
    parser.add_argument("--max-scenes", type=int, default=60)
    parser.add_argument("--max-turns-per-scene", type=int, default=80)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def normalized_aliases(candidate: dict[str, Any], language: str) -> list[str]:
    aliases = candidate[f"aliases_{language}"]
    forbidden = {item.casefold() for item in candidate.get("forbidden_aliases", [])}
    return [
        alias
        for alias in aliases
        if alias and alias.casefold() not in forbidden and alias not in {"Player"}
    ]


def contains_alias(text: str, aliases: Iterable[str]) -> bool:
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


def speaker_matches(speaker: str, aliases: Iterable[str]) -> bool:
    folded = speaker.casefold()
    for alias in aliases:
        value = alias.casefold()
        if value and (folded == value or value in folded):
            return True
    return False


def score_full_scene(
    source_scene: dict[str, Any],
    candidate: dict[str, Any],
    max_turns: int,
) -> tuple[int, dict[str, Any]]:
    zh_aliases = normalized_aliases(candidate, "zh")
    en_aliases = normalized_aliases(candidate, "en")
    turns = source_scene["turns"]
    target_indices: set[int] = set()
    score = 0
    reasons: set[str] = set()

    for index, turn in enumerate(turns):
        speaker_zh = turn["speaker_zh"]
        speaker_en = turn["speaker_en"]
        if speaker_matches(speaker_zh, zh_aliases) or speaker_matches(
            speaker_en, en_aliases
        ):
            target_indices.add(index)
            score += 4
            reasons.add("candidate_speaks_in_scene")
        if "玛拉妮" in speaker_zh and (
            contains_alias(turn["text_zh"], zh_aliases)
            or contains_alias(turn["text_en"], en_aliases)
        ):
            target_indices.add(index)
            score += 20
            reasons.add("mualani_mentions_candidate")

    for index in range(len(turns) - 1):
        if turns[index]["branch_path"] != turns[index + 1]["branch_path"]:
            continue
        first_zh = turns[index]["speaker_zh"]
        first_en = turns[index]["speaker_en"]
        second_zh = turns[index + 1]["speaker_zh"]
        second_en = turns[index + 1]["speaker_en"]
        direct = (
            (
                "玛拉妮" in first_zh
                and (
                    speaker_matches(second_zh, zh_aliases)
                    or speaker_matches(second_en, en_aliases)
                )
            )
            or (
                (
                    speaker_matches(first_zh, zh_aliases)
                    or speaker_matches(first_en, en_aliases)
                )
                and "玛拉妮" in second_zh
            )
        )
        if direct:
            score += 12
            target_indices.update((index, index + 1))
            reasons.add("direct_adjacency_with_mualani")

    if not target_indices:
        return 0, {}

    # Keep complete short scenes. For long scenes, retain windows around every
    # match, then cap deterministically.
    if len(turns) <= max_turns:
        kept_indices = list(range(len(turns)))
    else:
        window: set[int] = set()
        for index in target_indices:
            window.update(range(max(0, index - 8), min(len(turns), index + 9)))
        kept_indices = sorted(window)[:max_turns]

    paired_turns = [turns[index] for index in kept_indices]
    return score, {
        "source_type": source_scene["source_type"],
        "source_file": source_scene["source_file"],
        "document_id": source_scene["document_id"],
        "title_zh": source_scene["title_zh"],
        "title_en": source_scene["title_en"],
        "scene_id": source_scene["scene_id"],
        "scene_objective_zh": source_scene["scene_objective_zh"],
        "scene_objective_en": source_scene["scene_objective_en"],
        "match_reasons": sorted(reasons),
        "retrieval_score": score,
        "turns": paired_turns,
        "scene_turn_count_full": len(turns),
        "scene_turns_truncated": len(kept_indices) < len(turns),
        "scene_flags": source_scene["flags"],
    }


def voice_matches(
    voice_rows: list[dict[str, Any]], candidate: dict[str, Any]
) -> list[dict[str, Any]]:
    zh_aliases = normalized_aliases(candidate, "zh")
    en_aliases = normalized_aliases(candidate, "en")
    output = []
    for row in voice_rows:
        zh = row.get("zh", {})
        en = row.get("en", {})
        category = zh.get("voice_category", "")
        title_match = contains_alias(str(zh.get("title", "")), zh_aliases)
        text_match = contains_alias(str(zh.get("text", "")), zh_aliases)
        en_match = contains_alias(
            f"{en.get('title', '')}\n{en.get('text', '')}", en_aliases
        )
        traveler_match = (
            candidate["character_id"] == "traveler"
            and category == "relationship_with_traveler"
        )
        if not (title_match or text_match or en_match or traveler_match):
            continue
        output.append(
            {
                "source_type": "CharacterVoice",
                "source_file": str(zh.get("source_file", "")),
                "document_id": str(row.get("dialogue_id", "")),
                "dialogue_id": str(row.get("dialogue_id", "")),
                "title_zh": str(zh.get("title", "")),
                "text_zh": str(zh.get("text", "")),
                "title_en": str(en.get("title", "")),
                "text_en": str(en.get("text", "")),
                "voice_category": str(category),
                "match_reasons": [
                    reason
                    for reason, matched in (
                        ("title_alias_match", title_match),
                        ("text_alias_match", text_match),
                        ("english_alias_match", en_match),
                        ("traveler_relationship_voice", traveler_match),
                    )
                    if matched
                ],
            }
        )
    return output


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    candidates_path = args.candidates.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    candidate_document = load_json(candidates_path)
    full_scene_path = (
        root
        / "character_impressions"
        / "scope_audit"
        / "mualani_full_scenes.jsonl"
    )
    if not full_scene_path.exists():
        raise SystemExit(
            "Full-scene audit is missing. Run scripts/extract_mualani_full_scenes.py first."
        )
    full_scenes = load_jsonl(full_scene_path)
    voices = load_jsonl(
        root
        / "mualani_corpus"
        / "character_voice"
        / "parallel"
        / "mualani_zh_en_character_voice.jsonl"
    )
    manifest = {
        "schema_version": "mualani-impression-evidence-manifest-v1",
        "candidate_source": str(candidates_path.relative_to(root)),
        "corpus_source": str(full_scene_path.relative_to(root)),
        "candidate_count": len(candidate_document["candidates"]),
        "bundles": [],
    }

    for candidate in candidate_document["candidates"]:
        ranked_scenes = []
        for source_scene in full_scenes:
            score, scene = score_full_scene(
                source_scene, candidate, args.max_turns_per_scene
            )
            if score:
                key = (source_scene["source_file"], source_scene["scene_id"])
                ranked_scenes.append((score, key, scene))
        ranked_scenes.sort(key=lambda item: (-item[0], item[1]))
        retained_scenes = [item[2] for item in ranked_scenes[: args.max_scenes]]
        voice_evidence = voice_matches(voices, candidate)
        bundle = {
            "schema_version": "mualani-impression-evidence-v1",
            "candidate": candidate,
            "retrieval_policy": {
                "scope": "local bilingual Mualani corpus only",
                "include": [
                    "explicit character voice alias matches",
                    "complete source scenes where Mualani actually appears",
                    "candidate speech anywhere in those complete scenes",
                    "Mualani lines that name the candidate",
                    "direct adjacency between Mualani and the candidate",
                ],
                "warning": (
                    "Retrieval is deliberately broad. Co-presence is not proof of "
                    "an impression; the organizer must apply the inclusion threshold."
                ),
                "max_scenes": args.max_scenes,
                "max_turns_per_scene": args.max_turns_per_scene,
            },
            "counts": {
                "explicit_voice_records": len(voice_evidence),
                "matched_scenes_total": len(ranked_scenes),
                "matched_scenes_retained": len(retained_scenes),
            },
            "explicit_voice_evidence": voice_evidence,
            "scene_evidence": retained_scenes,
        }
        bundle_path = output / f"{candidate['character_id']}.json"
        write_json(bundle_path, bundle)
        manifest["bundles"].append(
            {
                "character_id": candidate["character_id"],
                "path": str(bundle_path.relative_to(root)),
                "explicit_voice_records": len(voice_evidence),
                "matched_scenes_total": len(ranked_scenes),
                "matched_scenes_retained": len(retained_scenes),
            }
        )

    write_json(output / "manifest.json", manifest)
    print(
        f"Wrote {len(manifest['bundles'])} evidence bundles to "
        f"{output.relative_to(root)}"
    )


if __name__ == "__main__":
    main()
