#!/usr/bin/env python3
"""Validate organizer results and assemble runtime card indexes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--raw",
        type=Path,
        default=ROOT / "character_impressions" / "raw_results",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=ROOT / "character_impressions" / "candidates.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "character_impressions",
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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
    temporary.replace(path)


def validate_result(
    result: dict[str, Any], candidate: dict[str, Any]
) -> list[str]:
    errors = []
    if result.get("decision") not in {"include", "exclude"}:
        errors.append("invalid decision")
    card = result.get("card")
    if not isinstance(card, dict):
        return errors + ["card is not an object"]
    expected = {
        "schema_version": "mualani-impression-card-v2",
        "character_id": candidate["character_id"],
        "name_zh": candidate["name_zh"],
        "name_en": candidate["name_en"],
        "roster_type": candidate["roster_type"],
    }
    for key, value in expected.items():
        if card.get(key) != value:
            errors.append(f"{key} mismatch: expected {value!r}, got {card.get(key)!r}")
    aliases = card.get("aliases", [])
    activation_keys = card.get("activation_keys", [])
    address_terms = card.get("address_terms", [])
    for key, values in (
        ("aliases", aliases),
        ("activation_keys", activation_keys),
        ("address_terms", address_terms),
    ):
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
            errors.append(f"{key} must be a string array")
            continue
        forbidden = {x.casefold() for x in candidate.get("forbidden_aliases", [])}
        bad = sorted({x for x in values if x.casefold() in forbidden})
        if bad:
            errors.append(f"{key} contains forbidden bare aliases: {bad}")
    if candidate["name_zh"] not in aliases or candidate["name_en"] not in aliases:
        errors.append("aliases must contain both formal Chinese and English names")
    if result.get("decision") == "include":
        if not card.get("evidence"):
            errors.append("included card has no evidence")
        if not str(card.get("mualani_impression", {}).get("text", "")).strip():
            errors.append("included card has no impression text")
        if not str(card.get("runtime_injection", "")).strip():
            errors.append("included card has no runtime injection")
    return errors


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    raw = args.raw.resolve()
    output = args.output.resolve()
    relationship_cards_dir = root / "mualani_relationships" / "cards"
    candidate_rows = load_json(args.candidates.resolve())["candidates"]
    candidates = {item["character_id"]: item for item in candidate_rows}

    cards = []
    excluded = []
    conflicts = []
    human_review = []
    failures = []

    for character_id, candidate in candidates.items():
        path = raw / f"{character_id}.json"
        if not path.exists():
            failures.append({"character_id": character_id, "error": "missing raw result"})
            continue
        try:
            result = load_json(path)
        except Exception as exc:
            failures.append({"character_id": character_id, "error": f"invalid JSON: {exc}"})
            continue
        errors = validate_result(result, candidate)
        if errors:
            failures.append({"character_id": character_id, "errors": errors})
            continue
        card = result["card"]
        if result["decision"] == "include":
            # Runtime lookup is entity-based. Keep activation keys aligned with
            # the reviewed name/alias set instead of allowing topical phrases
            # such as "X's invention" to masquerade as aliases.
            card["aliases"] = list(dict.fromkeys(card["aliases"]))
            card["activation_keys"] = list(card["aliases"])
            card["address_terms"] = list(dict.fromkeys(card["address_terms"]))
            card["behavioral_boundaries"] = list(
                dict.fromkeys(card["behavioral_boundaries"])
            )
            card["evidence_types"] = list(dict.fromkeys(card["evidence_types"]))
            relationship_card_path = (
                relationship_cards_dir / f"{character_id}.json"
            )
            if relationship_card_path.exists():
                relationship_card = load_json(relationship_card_path)
                card["region"] = relationship_card.get("region", "Other")
            cards.append(card)
            write_json(output / "cards" / f"{character_id}.json", card)
            review = card["review"]
            if review["conflicting_evidence"]:
                conflicts.append(
                    {
                        "character_id": character_id,
                        "items": review["conflicting_evidence"],
                    }
                )
            if review["needs_human_review"] or review["uncertain_claims"]:
                human_review.append(
                    {
                        "character_id": character_id,
                        "uncertain_claims": review["uncertain_claims"],
                        "needs_human_review": review["needs_human_review"],
                    }
                )
        else:
            excluded.append(
                {
                    "character_id": character_id,
                    "name_zh": candidate["name_zh"],
                    "name_en": candidate["name_en"],
                    "roster_type": candidate["roster_type"],
                    "reason": result.get("exclusion_reason") or "证据不足",
                }
            )

    cards.sort(key=lambda item: item["character_id"])
    excluded.sort(key=lambda item: item["character_id"])

    alias_map: dict[str, list[str]] = {}
    for card in cards:
        for alias in dict.fromkeys(
            [card["name_zh"], card["name_en"], *card["aliases"]]
        ):
            alias_map.setdefault(alias, []).append(card["character_id"])
    alias_map = {key: sorted(set(value)) for key, value in sorted(alias_map.items())}
    forbidden_aliases: dict[str, list[str]] = {}
    for candidate in candidate_rows:
        for alias in candidate.get("forbidden_aliases", []):
            forbidden_aliases.setdefault(alias, []).append(candidate["character_id"])
    forbidden_aliases = {
        key: sorted(set(value)) for key, value in sorted(forbidden_aliases.items())
    }

    index_rows = [
        {
            "character_id": card["character_id"],
            "name_zh": card["name_zh"],
            "name_en": card["name_en"],
            "aliases": card["aliases"],
            "roster_type": card["roster_type"],
            "region": card.get("region", "Other"),
            "familiarity": card["familiarity"],
            "evidence_strength": card["mualani_impression"]["evidence_strength"],
            "path": f"cards/{card['character_id']}.json",
        }
        for card in cards
    ]
    write_jsonl(output / "index.jsonl", index_rows)
    write_jsonl(output / "excluded_characters.jsonl", excluded)
    write_jsonl(output / "review" / "conflicts.jsonl", conflicts)
    write_jsonl(output / "review" / "needs_human_review.jsonl", human_review)
    write_json(
        output / "alias_index.json",
        {
            "schema_version": "mualani-impression-alias-index-v1",
            "aliases": alias_map,
            "blocked_ambiguous_aliases": forbidden_aliases,
            "lookup_rule": (
                "Use exact alias keys. A key mapped to multiple character IDs is "
                "ambiguous and must not trigger a card without more context."
            ),
        },
    )
    write_json(
        output / "assembly_report.json",
        {
            "candidate_count": len(candidates),
            "included_count": len(cards),
            "excluded_count": len(excluded),
            "failure_count": len(failures),
            "failures": failures,
        },
    )
    print(
        f"Assembled {len(cards)} cards; excluded {len(excluded)} candidates; "
        f"{len(failures)} validation failures."
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
