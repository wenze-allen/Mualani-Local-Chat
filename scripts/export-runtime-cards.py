#!/usr/bin/env python3
"""Export only fields consumed by the Mualani text runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CHARACTER_FIELDS = (
    "schema_version",
    "character_id",
    "name_zh",
    "name_en",
    "region",
    "evidence_types",
    "mualani_impression",
    "address_terms",
    "behavioral_boundaries",
    "activation_keys",
    "runtime_injection",
)
RELATIONSHIP_FIELDS = (
    "schema_version",
    "character_id",
    "name_zh",
    "name_en",
    "region",
    "familiarity",
    "personal_acquaintance",
    "contact_policy",
    "aliases",
    "runtime_injection",
)
WORLD_FIELDS = (
    "schema_version",
    "lore_id",
    "name_zh",
    "name_en",
    "aliases",
    "activation_keys",
    "runtime_injection",
)


def export_directory(source: Path, destination: Path, fields: tuple[str, ...]) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(source.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        runtime_payload = {key: payload[key] for key in fields if key in payload}
        (destination / path.name).write_text(
            json.dumps(runtime_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--characters", type=Path, required=True)
    parser.add_argument("--relationships", type=Path, required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    counts = {
        "characters": export_directory(
            args.characters,
            args.output / "characters",
            CHARACTER_FIELDS,
        ),
        "relationships": export_directory(
            args.relationships,
            args.output / "relationships",
            RELATIONSHIP_FIELDS,
        ),
        "world": export_directory(
            args.world,
            args.output / "world",
            WORLD_FIELDS,
        ),
    }
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
