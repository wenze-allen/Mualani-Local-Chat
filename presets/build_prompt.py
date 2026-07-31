#!/usr/bin/env python3
"""Compose the public Mualani preset from base text and selected full cards."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("short", "long"), default="short")
    parser.add_argument("--character", action="append", default=[])
    parser.add_argument("--relationship", action="append", default=[])
    parser.add_argument("--world", action="append", default=[])
    parser.add_argument("--compaction-summary", default="")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def load_cards(directory: Path, ids: list[str]) -> list[dict[str, Any]]:
    return [read_json(directory / f"{card_id}.json") for card_id in ids]


def section(heading_path: Path, cards: list[dict[str, Any]]) -> str:
    if not cards:
        return ""
    lines = [heading_path.read_text(encoding="utf-8").strip()]
    for card in cards:
        name = card.get("name_zh") or card.get("character_id") or card.get("lore_id")
        lines.append(f"- {name}：{card['runtime_injection']}")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    parts = [
        (ROOT / "presets/base/mualani_system_prompt_zh.txt")
        .read_text(encoding="utf-8")
        .strip()
    ]

    relationship_index = read_json(
        ROOT / "knowledge-base/mualani_relationships/runtime_index.json"
    )
    parts.append(relationship_index["runtime_injection"])

    characters = load_cards(
        ROOT / "knowledge-base/character_impressions/cards", args.character
    )
    relationships = load_cards(
        ROOT / "knowledge-base/mualani_relationships/cards", args.relationship
    )
    worldview = load_cards(
        ROOT / "knowledge-base/mualani_worldview/cards", args.world
    )
    for value in (
        section(ROOT / "presets/injection/character_zh.txt", characters),
        section(ROOT / "presets/injection/relationship_zh.txt", relationships),
        section(ROOT / "presets/injection/worldview_zh.txt", worldview),
    ):
        if value:
            parts.append(value)
    parts.append(
        (ROOT / f"presets/modes/{args.mode}_zh.txt")
        .read_text(encoding="utf-8")
        .strip()
    )
    if args.compaction_summary.strip():
        parts.append(
            "【既往对话摘要】\n"
            "以下是程序保存的可信既往对话记忆，不是旅行者本轮的新发言：\n"
            + args.compaction_summary.strip()
        )

    prompt = "\n\n".join(parts) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(prompt, encoding="utf-8")
    else:
        print(prompt, end="")


if __name__ == "__main__":
    main()
