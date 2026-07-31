#!/usr/bin/env python3
"""Build trigger-enriched runtime copies without changing audited cards."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from build_mualani_worldview_evidence import CHINESE_SPLIT


ROOT = Path(__file__).resolve().parents[1]
GENERIC_TRIGGERS = {
    "事情",
    "情况",
    "力量",
    "规则",
    "机制",
    "历史",
    "文化",
    "社会",
    "组织",
    "国家",
    "地区",
    "世界",
    "人类",
    "神明",
    "元素",
    "生命",
    "战争",
    "传说",
    "研究",
    "计划",
    "过去",
    "现在",
    "未来",
    "现实",
    "Overview",
    "History",
    "Culture",
    "Society",
    "Geography",
}
RUNTIME_FACT_PREFIXES = {
    # Personal facts that are part of Mualani's own character profile rather
    # than the objective world's topic facts.
    "power_vision": "玛拉妮自己的神之眼是水元素。",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
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


def safe_trigger(value: str) -> bool:
    value = value.strip()
    if not value or value in GENERIC_TRIGGERS:
        return False
    contains_non_ascii = any(ord(char) >= 128 for char in value)
    if contains_non_ascii:
        return len(value) >= 2
    return len(value) >= 4


def derived_title_triggers(objective: dict[str, Any]) -> list[str]:
    values: list[str] = []
    name_zh = str(objective.get("name_zh", ""))
    for part in CHINESE_SPLIT.split(name_zh):
        part = part.strip()
        for suffix in ("概述", "地理", "历史", "文化", "制度", "体系"):
            if part.endswith(suffix) and len(part) > len(suffix) + 1:
                part = part[: -len(suffix)]
        if safe_trigger(part):
            values.append(part)
    name_en = str(objective.get("name_en", ""))
    for part in re.split(r",|\\band\\b|&|/", name_en, flags=re.IGNORECASE):
        part = part.strip()
        if safe_trigger(part):
            values.append(part)
    return values


def main() -> None:
    args = parse_args()
    root = args.root.resolve(strict=True)
    worldview_root = root / "mualani_worldview"
    source_dir = worldview_root / "cards"
    output_dir = worldview_root / "runtime_cards"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    prepared: list[dict[str, Any]] = []
    candidates: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for source_path in sorted(source_dir.glob("*.json")):
        card = load_json(source_path)
        objective = load_json(
            root
            / "world_lore_cards"
            / "raw_results"
            / source_path.name
        )
        original_activation = card.get("activation_keys", [])
        original_aliases = card.get("aliases", [])
        original = [*original_activation, *original_aliases]
        derived = derived_title_triggers(objective)
        trigger_values: dict[str, tuple[str, int]] = {}
        names = {
            str(card.get("name_zh", "")).casefold(),
            str(card.get("name_en", "")).casefold(),
        }
        activation_folded = {
            item.casefold()
            for item in original_activation
            if isinstance(item, str)
        }
        alias_folded = {
            item.casefold()
            for item in original_aliases
            if isinstance(item, str)
        }
        for value in [*original, *derived]:
            if not isinstance(value, str):
                continue
            value = value.strip()
            folded = value.casefold()
            if not safe_trigger(value):
                continue
            priority = (
                100
                if folded in names
                else 90
                if folded in activation_folded
                else 80
                if folded in alias_folded
                else 20
            )
            previous = trigger_values.get(folded)
            if previous is None or priority > previous[1]:
                trigger_values[folded] = (value, priority)
        for folded, (_, priority) in trigger_values.items():
            candidates[folded].append((card["lore_id"], priority))
        prepared.append(
            {
                "source_path": source_path,
                "card": card,
                "trigger_values": trigger_values,
                "lore_id": card["lore_id"],
                "original_trigger_count": len(
                    {
                        item.casefold()
                        for item in original
                        if isinstance(item, str) and item
                    }
                ),
                "original_folded": {
                    value.casefold()
                    for value in original
                    if isinstance(value, str)
                },
            }
        )

    allowed_owners: dict[str, set[str]] = {}
    dropped_ambiguous_derived: dict[str, list[str]] = {}
    shared_triggers: dict[str, list[str]] = {}
    for trigger, rows in candidates.items():
        maximum = max(priority for _, priority in rows)
        winners = {
            lore_id
            for lore_id, priority in rows
            if priority == maximum
        }
        if maximum <= 20 and len(winners) > 1:
            allowed_owners[trigger] = set()
            dropped_ambiguous_derived[trigger] = sorted(winners)
        else:
            allowed_owners[trigger] = winners
            if len(winners) > 1:
                shared_triggers[trigger] = sorted(winners)

    report_cards: list[dict[str, Any]] = []
    for item in prepared:
        card = item["card"]
        triggers: list[str] = []
        for folded, (display, _) in item["trigger_values"].items():
            if card["lore_id"] in allowed_owners[folded]:
                triggers.append(display)
        card["activation_keys"] = triggers
        prefix = RUNTIME_FACT_PREFIXES.get(card["lore_id"], "")
        if prefix and not card["runtime_injection"].startswith(prefix):
            card["runtime_injection"] = prefix + card["runtime_injection"]
        objective = load_json(
            root
            / "world_lore_cards"
            / "raw_results"
            / item["source_path"].name
        )
        objective_facts = {
            fact["fact_id"]: fact["text"]
            for fact in objective.get("canonical_facts", [])
        }
        by_mode: dict[str, list[str]] = defaultdict(list)
        for assessment in card.get("fact_assessments", []):
            fact_text = objective_facts.get(assessment["fact_id"])
            if fact_text:
                by_mode[assessment["response_mode"]].append(fact_text)
        detail_sections: list[str] = []
        for mode, heading in (
            ("state_naturally", "她可以自然确认的具体事实"),
            (
                "state_with_attribution",
                "她只可明确说成听闻或他人说明的具体内容",
            ),
            (
                "frame_as_inference",
                "她只可明确作为个人判断提出的内容",
            ),
        ):
            facts = by_mode.get(mode, [])
            if facts:
                detail_sections.append(
                    heading + "：" + "；".join(facts)
                )
        if detail_sections:
            card["runtime_injection"] += "\n" + "\n".join(detail_sections)
        dump_json(output_dir / item["source_path"].name, card)
        report_cards.append(
            {
                "lore_id": card["lore_id"],
                "original_trigger_count": item["original_trigger_count"],
                "runtime_trigger_count": len(triggers),
                "added_triggers": [
                    trigger
                    for trigger in triggers
                    if trigger.casefold() not in item["original_folded"]
                ],
            }
        )

    report = {
        "schema_version": "mualani-worldview-runtime-build-v1",
        "card_count": len(report_cards),
        "shared_trigger_count": len(shared_triggers),
        "shared_triggers": shared_triggers,
        "dropped_ambiguous_derived_count": len(
            dropped_ambiguous_derived
        ),
        "dropped_ambiguous_derived": dropped_ambiguous_derived,
        "cards": report_cards,
    }
    dump_json(worldview_root / "runtime_build_report.json", report)
    print(
        f"Built {len(report_cards)} runtime cards; "
        f"intentional shared triggers={len(shared_triggers)}; "
        f"dropped ambiguous derived triggers="
        f"{len(dropped_ambiguous_derived)}."
    )


if __name__ == "__main__":
    main()
