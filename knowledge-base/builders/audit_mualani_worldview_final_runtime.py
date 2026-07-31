#!/usr/bin/env python3
"""Verify the complete three-round runtime-card review lineage."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
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
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def without_runtime(card: dict[str, Any]) -> dict[str, Any]:
    copied = dict(card)
    copied.pop("runtime_injection", None)
    return copied


def main() -> None:
    args = parse_args()
    root = args.root.resolve(strict=True) / "mualani_worldview"
    initial_dir = root / "runtime_cards"
    round1_dir = root / "runtime_reviews"
    reviewed_dir = root / "reviewed_runtime_cards"
    round2_dir = root / "runtime_reviews_round2"
    final_dir = root / "final_runtime_cards"
    round3_dir = root / "runtime_reviews_round3"
    final_paths = sorted(final_dir.glob("*.json"))
    errors: list[dict[str, str]] = []
    verdict_counts: Counter[str] = Counter()
    final_routes: Counter[str] = Counter()
    trigger_owners: dict[str, list[str]] = defaultdict(list)

    if len(final_paths) != 202:
        errors.append(
            {
                "lore_id": "*",
                "error": f"expected 202 final cards, found {len(final_paths)}",
            }
        )
    for final_path in final_paths:
        lore_id = final_path.stem
        initial = load_json(initial_dir / final_path.name)
        reviewed = load_json(reviewed_dir / final_path.name)
        final = load_json(final_path)
        if without_runtime(final) != without_runtime(initial):
            errors.append(
                {
                    "lore_id": lore_id,
                    "error": "non-runtime fields changed during review",
                }
            )
        for trigger in final.get("activation_keys", []):
            trigger_owners[trigger.casefold()].append(lore_id)

        round1 = load_json(round1_dir / final_path.name)
        try:
            validate_review(
                round1,
                lore_id=lore_id,
                runtime_text=initial["runtime_injection"],
            )
        except Exception as exc:
            errors.append(
                {"lore_id": lore_id, "error": f"round1: {exc}"}
            )
            continue
        verdict_counts[f"round1_{round1['verdict']}"] += 1
        if round1["verdict"] == "pass":
            final_routes["round1_pass"] += 1
            expected_runtime = initial["runtime_injection"]
        else:
            round2_path = round2_dir / final_path.name
            if not round2_path.exists():
                errors.append(
                    {"lore_id": lore_id, "error": "missing round2 review"}
                )
                continue
            round2 = load_json(round2_path)
            try:
                validate_review(
                    round2,
                    lore_id=lore_id,
                    runtime_text=reviewed["runtime_injection"],
                )
            except Exception as exc:
                errors.append(
                    {"lore_id": lore_id, "error": f"round2: {exc}"}
                )
                continue
            verdict_counts[f"round2_{round2['verdict']}"] += 1
            if round2["verdict"] == "pass":
                final_routes["round2_pass"] += 1
                expected_runtime = reviewed["runtime_injection"]
            else:
                round3_path = round3_dir / final_path.name
                if not round3_path.exists():
                    errors.append(
                        {
                            "lore_id": lore_id,
                            "error": "missing round3 review",
                        }
                    )
                    continue
                round3 = load_json(round3_path)
                try:
                    validate_review(
                        round3,
                        lore_id=lore_id,
                        runtime_text=round2["safe_replacement"],
                    )
                except Exception as exc:
                    errors.append(
                        {
                            "lore_id": lore_id,
                            "error": f"round3: {exc}",
                        }
                    )
                    continue
                verdict_counts[f"round3_{round3['verdict']}"] += 1
                if round3["verdict"] != "pass":
                    errors.append(
                        {
                            "lore_id": lore_id,
                            "error": "round3 did not pass",
                        }
                    )
                    continue
                final_routes["round3_pass"] += 1
                expected_runtime = round2["safe_replacement"]
        if final["runtime_injection"] != expected_runtime:
            errors.append(
                {
                    "lore_id": lore_id,
                    "error": "final runtime does not match passed lineage",
                }
            )

    collisions = {
        trigger: sorted(set(ids))
        for trigger, ids in trigger_owners.items()
        if len(set(ids)) > 1
    }
    if collisions:
        errors.append(
            {
                "lore_id": "*",
                "error": f"activation collisions remain: {collisions}",
            }
        )
    report = {
        "schema_version": "mualani-worldview-final-audit-v1",
        "final_card_count": len(final_paths),
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "final_routes": dict(sorted(final_routes.items())),
        "activation_collision_count": len(collisions),
        "activation_collisions": collisions,
        "errors": errors,
    }
    dump_json(root / "final_audit_report.json", report)
    print(
        f"Final audit: cards={len(final_paths)}, "
        f"errors={len(errors)}, collisions={len(collisions)}, "
        f"routes={dict(final_routes)}"
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
