#!/usr/bin/env python3
"""Apply second-round semantic review replacements to final runtime cards."""

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
    source_dir = worldview_root / "reviewed_runtime_cards"
    review_dir = worldview_root / "runtime_reviews_round2"
    output_dir = worldview_root / "final_runtime_cards"
    source_paths = sorted(source_dir.glob("*.json"))
    if len(source_paths) != 202:
        raise SystemExit(f"Expected 202 cards, found {len(source_paths)}")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    verdicts: Counter[str] = Counter()
    promoted: list[dict[str, Any]] = []
    for source_path in source_paths:
        card = load_json(source_path)
        review_path = review_dir / source_path.name
        verdict = "not_in_round2"
        issue_count = 0
        if review_path.exists():
            review = load_json(review_path)
            validate_review(
                review,
                lore_id=card["lore_id"],
                runtime_text=card["runtime_injection"],
            )
            verdict = review["verdict"]
            issue_count = len(review["issues"])
            card["runtime_injection"] = review["safe_replacement"]
        verdicts[verdict] += 1
        dump_json(output_dir / source_path.name, card)
        promoted.append(
            {
                "lore_id": card["lore_id"],
                "round2_verdict": verdict,
                "round2_issue_count": issue_count,
            }
        )
    manifest = {
        "schema_version": "mualani-worldview-final-runtime-v1",
        "card_count": len(promoted),
        "round2_verdict_counts": dict(sorted(verdicts.items())),
        "cards": promoted,
    }
    dump_json(
        worldview_root / "final_runtime_manifest.json",
        manifest,
    )
    print(
        f"Built {len(promoted)} final runtime cards: "
        + ", ".join(
            f"{key}={value}"
            for key, value in sorted(verdicts.items())
        )
    )


if __name__ == "__main__":
    main()
