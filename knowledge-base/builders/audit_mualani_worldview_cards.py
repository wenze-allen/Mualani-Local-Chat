#!/usr/bin/env python3
"""Audit deterministic integrity and epistemic-risk signals."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from run_mualani_worldview_cards import load_json, validate_card


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--only", nargs="*", default=[])
    return parser.parse_args()


def dump_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    worldview_root = root / "mualani_worldview"
    manifest = load_json(worldview_root / "evidence" / "manifest.json")
    lore_ids = [item["lore_id"] for item in manifest["results"]]
    if args.only:
        allowed = set(args.only)
        lore_ids = [item for item in lore_ids if item in allowed]

    statuses: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    tiers: Counter[str] = Counter()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    total_facts = 0
    for lore_id in lore_ids:
        evidence_path = worldview_root / "evidence" / f"{lore_id}.json"
        card_path = worldview_root / "cards" / f"{lore_id}.json"
        if not card_path.exists():
            errors.append({"lore_id": lore_id, "error": "missing card"})
            continue
        evidence = load_json(evidence_path)
        card = load_json(card_path)
        try:
            validate_card(card, evidence)
        except Exception as exc:
            errors.append({"lore_id": lore_id, "error": str(exc)})
            continue
        tiers[card["overall_knowledge"]["tier"]] += 1
        for assessment in card["fact_assessments"]:
            total_facts += 1
            statuses[assessment["epistemic_status"]] += 1
            modes[assessment["response_mode"]] += 1
            fact = next(
                item
                for item in evidence["objective_card"]["canonical_facts"]
                if item["fact_id"] == assessment["fact_id"]
            )
            if (
                fact["visibility"]
                in {"restricted_knowledge", "secret_or_exceptional"}
                and assessment["epistemic_status"]
                in {
                    "professionally_known",
                    "culturally_known",
                }
            ):
                warnings.append(
                    {
                        "lore_id": lore_id,
                        "fact_id": fact["fact_id"],
                        "warning": (
                            f"{fact['visibility']} was classified as "
                            f"{assessment['epistemic_status']}"
                        ),
                    }
                )
            if (
                not evidence["candidate_mualani_scenes"]
                and assessment["epistemic_status"]
                in {"firsthand", "directly_told"}
            ):
                errors.append(
                    {
                        "lore_id": lore_id,
                        "error": (
                            f"{assessment['fact_id']} claims direct evidence "
                            "without candidate scenes"
                        ),
                    }
                )

    report = {
        "schema_version": "mualani-worldview-audit-v1",
        "requested_card_count": len(lore_ids),
        "valid_card_count": len(lore_ids) - len(
            {item["lore_id"] for item in errors}
        ),
        "total_fact_assessments": total_facts,
        "epistemic_status_counts": dict(sorted(statuses.items())),
        "response_mode_counts": dict(sorted(modes.items())),
        "overall_tier_counts": dict(sorted(tiers.items())),
        "errors": errors,
        "warnings": warnings,
    }
    output = worldview_root / (
        "audit_report.partial.json" if args.only else "audit_report.json"
    )
    dump_json(output, report)
    print(
        f"Audited {len(lore_ids)} cards: errors={len(errors)}, "
        f"warnings={len(warnings)}, facts={total_facts}"
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
