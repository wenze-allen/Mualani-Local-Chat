#!/usr/bin/env python3
"""Import the curated research artifacts into the public repository.

This maintainer tool copies only reviewed cards, schemas, prompts, indexes, and
builder source. Raw corpora, evidence bundles, model outputs, and logs are
intentionally outside the allowlist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]

DIRECTORIES = {
    "character_impressions/cards": "knowledge-base/character_impressions/cards",
    "mualani_relationships/cards": "knowledge-base/mualani_relationships/cards",
    "world_lore_cards/raw_results": "knowledge-base/world_lore_cards/cards",
    "mualani_worldview/final_runtime_cards": "knowledge-base/mualani_worldview/cards",
}

FILES = {
    "character_impressions/alias_index.json": "knowledge-base/character_impressions/alias_index.json",
    "character_impressions/excluded_characters.jsonl": "knowledge-base/character_impressions/excluded_characters.jsonl",
    "character_impressions/schema/mualani_impression_result_v2.schema.json": "knowledge-base/schemas/mualani_impression_result_v2.schema.json",
    "character_impressions/prompts/organize_card_zh.txt": "knowledge-base/prompts/organize_character_impression_zh.txt",
    "mualani_relationships/network.json": "knowledge-base/mualani_relationships/network.json",
    "mualani_relationships/runtime_index.json": "knowledge-base/mualani_relationships/runtime_index.json",
    "mualani_relationships/audit_report.json": "knowledge-base/mualani_relationships/audit_report.json",
    "world_lore_cards/catalog.json": "knowledge-base/world_lore_cards/catalog.json",
    "world_lore_cards/schema/world_lore_card_v1.schema.json": "knowledge-base/schemas/world_lore_card_v1.schema.json",
    "world_lore_cards/prompts/organize_world_lore_card_zh.txt": "knowledge-base/prompts/organize_world_lore_card_zh.txt",
    "world_lore_cards/prompts/plan_supplemental_sources_zh.txt": "knowledge-base/prompts/plan_supplemental_sources_zh.txt",
    "world_lore_cards/prompts/select_supplemental_sources_zh.txt": "knowledge-base/prompts/select_supplemental_sources_zh.txt",
    "mualani_worldview/epistemic_profile.json": "knowledge-base/mualani_worldview/epistemic_profile.json",
    "mualani_worldview/schema/mualani_worldview_card_v1.schema.json": "knowledge-base/schemas/mualani_worldview_card_v1.schema.json",
    "mualani_worldview/schema/mualani_worldview_runtime_review_v1.schema.json": "knowledge-base/schemas/mualani_worldview_runtime_review_v1.schema.json",
    "mualani_worldview/prompts/organize_mualani_worldview_card_zh.txt": "knowledge-base/prompts/organize_mualani_worldview_card_zh.txt",
    "mualani_worldview/prompts/review_mualani_worldview_runtime_zh.txt": "knowledge-base/prompts/review_mualani_worldview_runtime_zh.txt",
}

BUILDERS = (
    "build_mualani_impression_evidence.py",
    "run_mualani_impression_cards.py",
    "assemble_mualani_impression_cards.py",
    "extract_mualani_full_scenes.py",
    "build_mualani_worldview_evidence.py",
    "run_mualani_worldview_cards.py",
    "audit_mualani_worldview_cards.py",
    "run_mualani_worldview_runtime_reviews.py",
)

FORBIDDEN_PATTERNS = (
    re.compile(r"/home/users/[^/\s]+/"),
    re.compile(r"/run/media/[^/\s]+/"),
    re.compile(r"\bscrp-login(?:\.[A-Za-z0-9.-]+)?\b"),
    re.compile(r"\boauth-[A-Za-z0-9_-]+\b"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Private research workspace containing the curated source trees.",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked_copy(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix in {".json", ".jsonl", ".txt", ".py"}:
        text = source.read_text(encoding="utf-8")
        hits = [pattern.pattern for pattern in FORBIDDEN_PATTERNS if pattern.search(text)]
        if hits:
            raise RuntimeError(f"{source}: private markers found: {hits}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def iter_allowed_files(directory: Path) -> Iterable[Path]:
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".txt"}:
            yield path


def replace_directory(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(source)
    if destination.exists():
        shutil.rmtree(destination)
    for path in iter_allowed_files(source):
        checked_copy(path, destination / path.relative_to(source))


def write_relationship_roster(source_root: Path, repo_root: Path) -> None:
    """Publish the derived roster, not the downloaded API/page snapshots."""
    network = json.loads(
        (source_root / "mualani_relationships/network.json").read_text(
            encoding="utf-8"
        )
    )
    roster = []
    for node in network["nodes"]:
        roster.append(
            {
                "character_id": node["character_id"],
                "name_zh": node["name_zh"],
                "name_en": node["name_en"],
                "aliases": node["aliases"],
                "region": node["region"],
                "roster_type": node["roster_type"],
                "source_key": node["roster_source_key"],
            }
        )
    roster.sort(key=lambda item: item["character_id"])
    destination = repo_root / "knowledge-base/mualani_relationships/roster.json"
    destination.write_text(
        json.dumps(
            {
                "schema_version": "mualani-relationship-roster-v1",
                "description": (
                    "Derived coverage roster. Regenerate upstream snapshots "
                    "from the URLs recorded in network.json when refreshing it."
                ),
                "characters": roster,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    source_root = args.source_root.resolve(strict=True)
    repo_root = args.repo_root.resolve(strict=True)

    legacy_snapshots = (
        repo_root / "knowledge-base/mualani_relationships/sources"
    )
    if legacy_snapshots.exists():
        shutil.rmtree(legacy_snapshots)

    for source_name, destination_name in DIRECTORIES.items():
        replace_directory(
            source_root / source_name,
            repo_root / destination_name,
        )
    for source_name, destination_name in FILES.items():
        checked_copy(source_root / source_name, repo_root / destination_name)
    write_relationship_roster(source_root, repo_root)
    for name in BUILDERS:
        checked_copy(
            source_root / "scripts" / name,
            repo_root / "knowledge-base" / "builders" / name,
        )

    categories = {
        "character_impressions": repo_root / "knowledge-base/character_impressions/cards",
        "relationships": repo_root / "knowledge-base/mualani_relationships/cards",
        "objective_world": repo_root / "knowledge-base/world_lore_cards/cards",
        "mualani_worldview": repo_root / "knowledge-base/mualani_worldview/cards",
    }
    manifest = {
        "schema_version": "mualani-public-knowledge-base-v1",
        "corpus_revision": "OSCBWin6.7.54",
        "categories": {},
    }
    for category, directory in categories.items():
        files = sorted(directory.glob("*.json"))
        manifest["categories"][category] = {
            "count": len(files),
            "files": [
                {
                    "path": path.relative_to(repo_root).as_posix(),
                    "sha256": sha256(path),
                }
                for path in files
            ],
        }
    destination = repo_root / "knowledge-base/manifest.json"
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: value["count"]
                for key, value in manifest["categories"].items()
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
