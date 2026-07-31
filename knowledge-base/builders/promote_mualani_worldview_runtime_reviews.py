#!/usr/bin/env python3
"""Promote semantic-review replacements into a separate runtime tree."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from run_mualani_worldview_runtime_reviews import validate_review


ROOT = Path(__file__).resolve().parents[1]


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


def main() -> None:
    args = parse_args()
    root = args.root.resolve(strict=True)
    worldview_root = root / "mualani_worldview"
    source_dir = worldview_root / "runtime_cards"
    review_dir = worldview_root / "runtime_reviews"
    output_dir = worldview_root / "reviewed_runtime_cards"
    source_paths = sorted(source_dir.glob("*.json"))
    if len(source_paths) != 202:
        raise SystemExit(
            f"Expected 202 source runtime cards, found {len(source_paths)}"
        )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    verdicts: Counter[str] = Counter()
    issue_types: Counter[str] = Counter()
    promoted: list[dict[str, Any]] = []
    for source_path in source_paths:
        card = load_json(source_path)
        review_path = review_dir / source_path.name
        if not review_path.exists():
            raise SystemExit(f"Missing semantic review: {review_path}")
        review = load_json(review_path)
        validate_review(
            review,
            lore_id=card["lore_id"],
            runtime_text=card["runtime_injection"],
        )
        verdicts[review["verdict"]] += 1
        for issue in review["issues"]:
            issue_types[issue["issue_type"]] += 1
        original_runtime = card["runtime_injection"]
        card["runtime_injection"] = review["safe_replacement"]
        if review["verdict"] == "revise":
            card["runtime_injection"] = card["runtime_injection"].replace(
                "她只可明确说成听闻或他人说明的具体内容：",
                "以下内容只能作为未核实的外界说法转述，不得声称"
                "某个具体人物确实向她说明过：",
            )
        dump_json(output_dir / source_path.name, card)
        promoted.append(
            {
                "lore_id": card["lore_id"],
                "verdict": review["verdict"],
                "issue_count": len(review["issues"]),
                "original_runtime_chars": len(original_runtime),
                "reviewed_runtime_chars": len(card["runtime_injection"]),
            }
        )

    manifest = {
        "schema_version": "mualani-worldview-reviewed-runtime-v1",
        "card_count": len(promoted),
        "verdict_counts": dict(sorted(verdicts.items())),
        "issue_type_counts": dict(sorted(issue_types.items())),
        "cards": promoted,
    }
    dump_json(
        worldview_root / "reviewed_runtime_manifest.json",
        manifest,
    )
    print(
        f"Promoted {len(promoted)} reviewed runtime cards: "
        + ", ".join(
            f"{verdict}={count}"
            for verdict, count in sorted(verdicts.items())
        )
    )


if __name__ == "__main__":
    main()
