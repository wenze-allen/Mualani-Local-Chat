#!/usr/bin/env python3
"""Build isolated objective-card + Mualani-scene evidence bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CHINESE_RUN = re.compile(r"[\u3400-\u9fff]+")
ASCII_TERM = re.compile(r"[A-Za-z][A-Za-z' -]{2,48}")
QUOTED_TERM = re.compile(r"[「『“]([^」』”]{2,24})[」』”]")
CHINESE_SPLIT = re.compile(r"[、，：；与和及·/（）()]+")
MUALANI_NAMES = {"玛拉妮", "Mualani"}
GENERIC_EXACT_TERMS = {
    "历史",
    "文化",
    "社会",
    "地理",
    "概述",
    "组织",
    "制度",
    "力量",
    "世界",
    "人类",
    "神明",
    "元素",
    "Overview",
    "History",
    "Culture",
    "Society",
    "Geography",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--max-scenes", type=int, default=8)
    parser.add_argument("--max-lines-per-scene", type=int, default=180)
    parser.add_argument("--min-score", type=float, default=9.0)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def flatten_dialogues(items: Any) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    if not isinstance(items, list):
        return lines
    for item in items:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            lines.append(
                {
                    "dialogue_id": str(item.get("id", "")),
                    "speaker": str(item.get("speaker") or "旅行者"),
                    "text": text.strip(),
                }
            )
        for choice in item.get("choices", []) or []:
            if not isinstance(choice, dict):
                continue
            choice_text = choice.get("text")
            if isinstance(choice_text, str) and choice_text.strip():
                lines.append(
                    {
                        "dialogue_id": str(choice.get("id", "")),
                        "speaker": "旅行者",
                        "text": choice_text.strip(),
                    }
                )
            lines.extend(flatten_dialogues(choice.get("response")))
        lines.extend(flatten_dialogues(item.get("response")))
    return lines


def load_mualani_quest_scenes(root: Path) -> list[dict[str, Any]]:
    quest_root = root / "YuanShenResources" / "DialogsText" / "CHS" / "Quest"
    scenes: list[dict[str, Any]] = []
    for path in sorted(quest_root.glob("Quest_*.json")):
        document = load_json(path)
        quest = document.get("quest", {})
        for talk in document.get("talks", []):
            objective = str(talk.get("objective", ""))
            objective_folded = objective.casefold()
            if (
                "$hidden" in objective_folded
                or "(test)" in objective_folded
                or "废弃" in objective
            ):
                continue
            lines = flatten_dialogues(talk.get("dialogues"))
            if not any(line["speaker"] in MUALANI_NAMES for line in lines):
                continue
            scene_id = f"quest_{quest.get('id', path.stem)}_talk_{talk.get('id', '')}"
            scenes.append(
                {
                    "scene_id": scene_id,
                    "source_type": "Quest",
                    "source_file": path.relative_to(root).as_posix(),
                    "document_id": str(quest.get("id", "")),
                    "title": str(quest.get("title", "")),
                    "chapter": quest.get("chapter"),
                    "objective": objective,
                    "lines": lines,
                }
            )
    return scenes


def load_voice_scenes(root: Path) -> list[dict[str, Any]]:
    path = (
        root
        / "mualani_corpus"
        / "character_voice"
        / "zh"
        / "mualani_character_voice.jsonl"
    )
    scenes: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            item = json.loads(raw)
            scenes.append(
                {
                    "scene_id": str(item["dialogue_id"]),
                    "source_type": "CharacterVoice",
                    "source_file": str(item["source_file"]),
                    "document_id": str(item.get("document_id", "")),
                    "title": str(item.get("title", "")),
                    "chapter": None,
                    "objective": str(item.get("scene_objective", "")),
                    "lines": [
                        {
                            "dialogue_id": str(item["dialogue_id"]),
                            "speaker": "玛拉妮",
                            "text": str(item["text"]),
                        }
                    ],
                }
            )
    return scenes


def scene_text(scene: dict[str, Any]) -> str:
    return "\n".join(
        [
            scene.get("title", ""),
            scene.get("objective", ""),
            *(
                f"{line['speaker']}：{line['text']}"
                for line in scene.get("lines", [])
            ),
        ]
    )


def cjk_ngrams(text: str) -> Counter[str]:
    grams: Counter[str] = Counter()
    for run in CHINESE_RUN.findall(text):
        if len(run) < 2:
            continue
        for width in (2, 3, 4):
            for start in range(len(run) - width + 1):
                grams[run[start : start + width]] += 1
    return grams


def exact_terms(card: dict[str, Any]) -> list[str]:
    terms: set[str] = set()
    for key in ("name_zh", "name_en"):
        value = card.get(key)
        if isinstance(value, str):
            terms.add(value.strip())
    for key in ("aliases", "activation_keys"):
        for value in card.get(key, []):
            if isinstance(value, str):
                terms.add(value.strip())
    serialized = json.dumps(
        {
            "summary": card.get("summary", ""),
            "canonical_facts": card.get("canonical_facts", []),
        },
        ensure_ascii=False,
    )
    terms.update(match.strip() for match in QUOTED_TERM.findall(serialized))
    name_zh = str(card.get("name_zh", ""))
    for part in CHINESE_SPLIT.split(name_zh):
        part = part.strip()
        for suffix in ("概述", "地理", "历史", "文化", "制度", "体系"):
            if part.endswith(suffix) and len(part) > len(suffix) + 1:
                part = part[: -len(suffix)]
        if len(part) >= 2:
            terms.add(part)
    filtered = {
        term
        for term in terms
        if (
            term
            and term not in GENERIC_EXACT_TERMS
            and (
                len(term) >= 2
                if CHINESE_RUN.search(term)
                else len(term) >= 3
            )
        )
    }
    return sorted(filtered, key=lambda value: (-len(value), value))


def query_text(card: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(card.get("name_zh", "")),
            str(card.get("name_en", "")),
            str(card.get("summary", "")),
            *[
                str(fact.get("text", ""))
                for fact in card.get("canonical_facts", [])
            ],
        ]
    )


def select_scenes(
    card: dict[str, Any],
    scenes: list[dict[str, Any]],
    *,
    document_frequencies: Counter[str],
    max_scenes: int,
    max_lines: int,
    min_score: float,
) -> list[dict[str, Any]]:
    terms = exact_terms(card)
    query_counts = cjk_ngrams(query_text(card))
    total_documents = len(scenes)
    ranked: list[tuple[float, dict[str, Any], list[str]]] = []
    for scene in scenes:
        text = scene["_search_text"]
        folded = text.casefold()
        matches = [
            term
            for term in terms
            if term.casefold() in folded
        ]
        score = 0.0
        for term in matches:
            count = folded.count(term.casefold())
            score += 18.0 + min(len(term), 16) * 3.0 + min(count, 4) * 4.0
            if any(
                line["speaker"] in MUALANI_NAMES
                and term.casefold() in line["text"].casefold()
                for line in scene["lines"]
            ):
                score += 24.0

        scene_counts = scene["_ngrams"]
        shared = set(query_counts) & set(scene_counts)
        rare_shared = sorted(
            shared,
            key=lambda gram: (
                document_frequencies[gram],
                -len(gram),
                gram,
            ),
        )[:80]
        for gram in rare_shared:
            df = document_frequencies[gram]
            if df > max(8, total_documents // 5):
                continue
            idf = math.log((total_documents + 1) / (df + 1)) + 1.0
            score += (
                idf
                * (len(gram) - 1)
                * min(query_counts[gram], scene_counts[gram], 2)
                * 0.32
            )
        # Character n-grams only rank scenes that already contain a concrete
        # topic term.  They must never manufacture "semantic evidence" from
        # unrelated scenes with generic shared wording.
        if matches and score >= min_score:
            ranked.append((score, scene, matches[:16]))

    ranked.sort(
        key=lambda row: (
            -row[0],
            row[1]["source_type"] != "Quest",
            row[1]["scene_id"],
        )
    )
    selected: list[dict[str, Any]] = []
    for score, scene, matches in ranked[:max_scenes]:
        lines = scene["lines"]
        truncated = len(lines) > max_lines
        if truncated:
            # Preserve the opening and ending plus every line spoken by Mualani
            # and a small local window around it.
            keep: set[int] = set(range(min(24, len(lines))))
            keep.update(range(max(0, len(lines) - 16), len(lines)))
            for index, line in enumerate(lines):
                if line["speaker"] in MUALANI_NAMES:
                    keep.update(
                        range(max(0, index - 8), min(len(lines), index + 9))
                    )
            indices = sorted(keep)[:max_lines]
            lines = [lines[index] for index in indices]
        payload = {
            key: value
            for key, value in scene.items()
            if not key.startswith("_") and key != "lines"
        }
        payload.update(
            {
                "retrieval_score": round(score, 3),
                "matched_terms": matches,
                "retrieval_warning": (
                    "候选场景仅因词面相关而被检索；只有文本明确支持时才可作为玛拉妮知道某事实的证据。"
                ),
                "truncated": truncated,
                "lines": lines,
            }
        )
        selected.append(payload)
    return selected


def prepare_scene_index(
    scenes: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    prepared: list[dict[str, Any]] = []
    frequencies: Counter[str] = Counter()
    for scene in scenes:
        copied = dict(scene)
        copied["_search_text"] = scene_text(copied)
        copied["_ngrams"] = cjk_ngrams(copied["_search_text"])
        frequencies.update(copied["_ngrams"].keys())
        prepared.append(copied)
    return prepared, frequencies


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    lore_root = root / "world_lore_cards"
    output_root = root / "mualani_worldview" / "evidence"
    profile = load_json(root / "mualani_worldview" / "epistemic_profile.json")
    catalog = load_json(lore_root / "catalog.json")
    topics = {item["lore_id"]: item for item in catalog["topics"]}
    scenes, frequencies = prepare_scene_index(
        [
            *load_mualani_quest_scenes(root),
            *load_voice_scenes(root),
        ]
    )

    results: list[dict[str, Any]] = []
    for card_path in sorted((lore_root / "raw_results").glob("*.json")):
        card = load_json(card_path)
        lore_id = card["lore_id"]
        topic = topics[lore_id]
        selected = select_scenes(
            card,
            scenes,
            document_frequencies=frequencies,
            max_scenes=args.max_scenes,
            max_lines=args.max_lines_per_scene,
            min_score=args.min_score,
        )
        bundle = {
            "schema_version": "mualani-worldview-evidence-v1",
            "lore_id": lore_id,
            "target": {
                "lore_id": lore_id,
                "name_zh": topic["name_zh"],
                "name_en": topic["name_en"],
                "aliases": card["aliases"],
                "activation_keys": card["activation_keys"],
            },
            "objective_card_sha256": canonical_sha256(card),
            "objective_card": card,
            "epistemic_profile": profile,
            "candidate_mualani_scenes": selected,
            "isolation_policy": (
                "本证据包只含一张客观资料卡；候选场景是词面检索结果，"
                "不得将其存在本身视为玛拉妮知情的证明。"
            ),
        }
        bundle["evidence_bundle_sha256"] = canonical_sha256(bundle)
        dump_json(output_root / f"{lore_id}.json", bundle)
        results.append(
            {
                "lore_id": lore_id,
                "status": "ready",
                "objective_fact_count": len(card["canonical_facts"]),
                "candidate_scene_count": len(selected),
                "candidate_scene_ids": [
                    item["scene_id"] for item in selected
                ],
                "objective_card_sha256": bundle["objective_card_sha256"],
                "evidence_bundle_sha256": bundle[
                    "evidence_bundle_sha256"
                ],
            }
        )

    manifest = {
        "schema_version": "mualani-worldview-evidence-manifest-v1",
        "objective_card_count": len(results),
        "quest_or_voice_scene_count": len(scenes),
        "results": results,
    }
    dump_json(output_root / "manifest.json", manifest)
    print(
        f"Built {len(results)} isolated bundles from {len(scenes)} "
        f"Mualani-present quest/voice scenes."
    )
    distribution = Counter(item["candidate_scene_count"] for item in results)
    print(
        "Candidate scene distribution: "
        + ", ".join(
            f"{count} scenes={cards}"
            for count, cards in sorted(distribution.items())
        )
    )


if __name__ == "__main__":
    main()
