#!/usr/bin/env python3
"""Validate public runtime data and repository boundaries."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_CARD_FIELDS = {
    "evidence",
    "excerpt",
    "source_file",
    "dialogue_ids",
    "evidence_bundle_sha256",
    "objective_card_sha256",
    "fact_assessments",
    "review",
}


def walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(key)
            keys.update(walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(walk_keys(child))
    return keys


def main() -> None:
    expected_counts = {"characters": 21, "relationships": 119, "world": 202}
    for category, expected in expected_counts.items():
        directory = ROOT / "app" / "cards" / category
        paths = [path for path in directory.glob("*.json") if path.name != "runtime_index.json"]
        if len(paths) != expected:
            raise RuntimeError(f"{category}: expected {expected} cards, found {len(paths)}")
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            forbidden = sorted(walk_keys(payload) & FORBIDDEN_CARD_FIELDS)
            if forbidden:
                raise RuntimeError(f"{path}: private/audit fields remain: {forbidden}")
            if not payload.get("runtime_injection"):
                raise RuntimeError(f"{path}: missing runtime_injection")

    index = json.loads(
        (ROOT / "app" / "cards" / "relationships" / "runtime_index.json").read_text(encoding="utf-8")
    )
    if not index.get("runtime_injection"):
        raise RuntimeError("relationship runtime index is incomplete")

    gguf_files = list(ROOT.glob("models/**/*.gguf"))
    if gguf_files:
        raise RuntimeError(f"model weights must not be committed: {gguf_files}")

    checksum_lines = (ROOT / "MODEL_SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    expected_shards = {
        "Mualani-Qwen3.5-4B-Chat-v2-Q4_K_M-00001-of-00002.gguf",
        "Mualani-Qwen3.5-4B-Chat-v2-Q4_K_M-00002-of-00002.gguf",
        "Mualani-Qwen3.5-9B-Chat-v2-Q4_K_M-00001-of-00003.gguf",
        "Mualani-Qwen3.5-9B-Chat-v2-Q4_K_M-00002-of-00003.gguf",
        "Mualani-Qwen3.5-9B-Chat-v2-Q4_K_M-00003-of-00003.gguf",
    }
    parsed_shards: set[str] = set()
    for line in checksum_lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (\S+)", line)
        if not match:
            raise RuntimeError(f"invalid model checksum line: {line!r}")
        parsed_shards.add(match.group(2))
    if parsed_shards != expected_shards:
        raise RuntimeError(
            f"model checksum manifest mismatch: expected={expected_shards}, actual={parsed_shards}"
        )

    print("Package validation passed: 342 cards, model checksums, no committed weights.")


if __name__ == "__main__":
    main()
