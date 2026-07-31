#!/usr/bin/env python3
"""Validate the checked-in knowledge base, dataset design, and training assets."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "knowledge-base"

EXPECTED_COUNTS = {
    "character_impressions": 21,
    "relationships": 119,
    "objective_world": 202,
    "mualani_worldview": 202,
}

CARD_DIRS = {
    "character_impressions": KB / "character_impressions/cards",
    "relationships": KB / "mualani_relationships/cards",
    "objective_world": KB / "world_lore_cards/cards",
    "mualani_worldview": KB / "mualani_worldview/cards",
}

PRIVATE_PATTERNS = (
    re.compile(r"/home/users/[^/\s]+/"),
    re.compile(r"/run/media/[^/\s]+/"),
    re.compile(r"\bscrp-login(?:\.[A-Za-z0-9.-]+)?\b"),
    re.compile(r"\boauth-[A-Za-z0-9_-]+\b"),
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_fields(path: Path, payload: dict[str, Any], fields: set[str]) -> None:
    missing = sorted(fields - set(payload))
    if missing:
        raise RuntimeError(f"{path}: missing fields: {missing}")


def validate_cards() -> None:
    manifest = read_json(KB / "manifest.json")
    for category, expected in EXPECTED_COUNTS.items():
        directory = CARD_DIRS[category]
        paths = sorted(directory.glob("*.json"))
        if len(paths) != expected:
            raise RuntimeError(
                f"{category}: expected {expected} cards, found {len(paths)}"
            )
        entry = manifest["categories"][category]
        if entry["count"] != expected:
            raise RuntimeError(f"manifest count mismatch for {category}")
        expected_hashes = {
            item["path"]: item["sha256"] for item in entry["files"]
        }
        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            if expected_hashes.get(relative) != sha256(path):
                raise RuntimeError(f"manifest hash mismatch: {relative}")
            payload = read_json(path)
            if category == "character_impressions":
                require_fields(
                    path,
                    payload,
                    {
                        "character_id", "mualani_impression", "evidence",
                        "behavioral_boundaries", "runtime_injection",
                    },
                )
            elif category == "relationships":
                require_fields(
                    path,
                    payload,
                    {
                        "character_id", "personal_acquaintance", "familiarity",
                        "contact_policy", "evidence", "runtime_injection",
                    },
                )
            elif category == "objective_world":
                require_fields(
                    path,
                    payload,
                    {"lore_id", "canonical_facts", "sources", "activation_keys"},
                )
            else:
                require_fields(
                    path,
                    payload,
                    {
                        "lore_id", "overall_knowledge", "fact_assessments",
                        "natural_expression", "review", "runtime_injection",
                    },
                )
                objective = read_json(CARD_DIRS["objective_world"] / path.name)
                if payload["objective_card_sha256"] != canonical_hash(objective):
                    raise RuntimeError(f"objective-card hash mismatch: {path}")

    roster_path = KB / "mualani_relationships/roster.json"
    roster = read_json(roster_path)
    if roster.get("schema_version") != "mualani-relationship-roster-v1":
        raise RuntimeError("unexpected relationship roster schema")
    roster_ids = [row["character_id"] for row in roster.get("characters", [])]
    if len(roster_ids) != EXPECTED_COUNTS["relationships"]:
        raise RuntimeError("relationship roster count mismatch")
    if len(roster_ids) != len(set(roster_ids)):
        raise RuntimeError("relationship roster contains duplicate IDs")
    if (KB / "mualani_relationships/sources").exists():
        raise RuntimeError("raw relationship source snapshots must not be published")


def validate_runtime_projection() -> None:
    pairs = (
        ("characters", "character_impressions"),
        ("relationships", "relationships"),
        ("world", "mualani_worldview"),
    )
    for runtime_category, full_category in pairs:
        for runtime_path in sorted((ROOT / "app/cards" / runtime_category).glob("*.json")):
            if runtime_path.name == "runtime_index.json":
                continue
            full_path = CARD_DIRS[full_category] / runtime_path.name
            runtime = read_json(runtime_path)
            full = read_json(full_path)
            for key, value in runtime.items():
                if full.get(key) != value:
                    raise RuntimeError(
                        f"runtime projection differs from full card: {runtime_path}:{key}"
                    )


def validate_public_boundaries() -> None:
    scan_roots = (KB, ROOT / "dataset", ROOT / "training", ROOT / "presets")
    for scan_root in scan_roots:
        for path in scan_root.rglob("*"):
            if not path.is_file() or path.suffix not in {
                ".json", ".jsonl", ".md", ".txt", ".py", ".sh", ".example"
            }:
                continue
            if path.name == "import-research-assets.py":
                continue
            text = path.read_text(encoding="utf-8")
            hits = [
                pattern.pattern
                for pattern in PRIVATE_PATTERNS
                if pattern.search(text)
            ]
            if hits:
                raise RuntimeError(f"{path}: private markers found: {hits}")


def validate_synthetic_example() -> None:
    path = ROOT / "dataset/examples/synthetic_sft.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != 1:
        raise RuntimeError("synthetic dataset must contain exactly one example")
    row = rows[0]
    if [message.get("role") for message in row["prompt"]] != ["system", "user"]:
        raise RuntimeError("synthetic prompt must contain system then user")
    if row["completion"].get("role") != "assistant":
        raise RuntimeError("synthetic completion must be assistant")


def validate_prompt_builder() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "prompt.txt"
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "presets/build_prompt.py"),
                "--mode", "short",
                "--character", "kachina",
                "--relationship", "yoimiya",
                "--world", "inazuma_overview",
                "--output", str(output),
            ],
            check=True,
        )
        text = output.read_text(encoding="utf-8")
        for required in ("卡齐娜", "宵宫", "稻妻", "回答模式：短回答"):
            if required not in text:
                raise RuntimeError(f"composed prompt is missing {required}")


def validate_training_baseline() -> None:
    baseline = read_json(ROOT / "training/benchmarks/a800_80gb_chat_v2.json")
    if baseline.get("device") != "NVIDIA A800-SXM4-80GB":
        raise RuntimeError("unexpected training baseline device")
    for model_key, expected_runtime in (("4b", 888.0978), ("9b", 1673.8572)):
        run = baseline["runs"][model_key]
        if run.get("optimizer_steps") != 64:
            raise RuntimeError(f"unexpected {model_key} optimizer-step count")
        if run.get("train_runtime_seconds") != expected_runtime:
            raise RuntimeError(f"unexpected {model_key} measured runtime")
    artifacts = baseline["measurement_provenance"]["artifacts"]
    if not artifacts or any(
        len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
        for value in artifacts.values()
    ):
        raise RuntimeError("invalid training-artifact provenance hashes")


def main() -> None:
    validate_cards()
    validate_runtime_projection()
    validate_public_boundaries()
    validate_synthetic_example()
    validate_prompt_builder()
    validate_training_baseline()
    print(
        "Research validation passed: 544 full cards, runtime projection, "
        "dataset example, prompt composition, and public boundaries."
    )


if __name__ == "__main__":
    main()
