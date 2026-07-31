#!/usr/bin/env python3
"""Verify the uploaded SFT snapshot before starting an expensive GPU run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument(
        "--expected-profile",
        choices=("legacy", "chat-v2"),
        required=True,
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def verify_split(
    dataset_dir: Path,
    split: str,
    expected: dict[str, Any],
    all_ids: set[str],
    group_owners: dict[str, str],
) -> int:
    path = dataset_dir / str(expected["path"])
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected["sha256"]:
        raise ValueError(
            f"{path}: SHA-256 mismatch; expected {expected['sha256']}, "
            f"got {actual_sha256}"
        )

    rows = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row_id = row.get("id")
            group_id = row.get("group_id")
            prompt = row.get("prompt")
            completion = row.get("completion")
            if (
                not isinstance(row_id, str)
                or not isinstance(group_id, str)
                or not isinstance(prompt, list)
                or len(prompt) != 2
                or prompt[0].get("role") != "system"
                or prompt[1].get("role") != "user"
                or not isinstance(completion, dict)
                or completion.get("role") != "assistant"
                or not str(completion.get("content") or "").strip()
            ):
                raise ValueError(f"{path}:{line_number}: invalid SFT row")
            if row_id in all_ids:
                raise ValueError(f"{path}:{line_number}: duplicate id {row_id}")
            all_ids.add(row_id)
            owner = group_owners.setdefault(group_id, split)
            if owner != split:
                raise ValueError(
                    f"{path}:{line_number}: group {group_id} leaks from "
                    f"{owner} into {split}"
                )
            rows += 1

    if rows != expected["rows"]:
        raise ValueError(
            f"{path}: row count mismatch; expected {expected['rows']}, got {rows}"
        )
    return rows


def main() -> None:
    args = parse_args()
    manifest_path = args.dataset_dir / "manifest.json"
    audit_path = args.dataset_dir / "audit_report.json"
    manifest = read_json(manifest_path)

    expected_format = (
        "mualani-direct-chat-sft-v2"
        if args.expected_profile == "chat-v2"
        else "mualani-assistant-only-sft-v1"
    )
    if manifest.get("format") != expected_format:
        raise ValueError(
            f"{manifest_path}: expected format {expected_format}, "
            f"got {manifest.get('format')}"
        )
    if (
        args.expected_profile == "chat-v2"
        and manifest.get("quality_profile") != "chat-v2"
    ):
        raise ValueError(f"{manifest_path}: chat-v2 quality profile is missing")

    if args.expected_profile == "chat-v2":
        audit = read_json(audit_path)
        if (
            audit.get("status") != "passed"
            or audit.get("quality_profile") != "chat-v2"
            or audit.get("all_rows_read") != manifest.get("total_rows")
        ):
            raise ValueError(f"{audit_path}: local chat-v2 audit is not valid")

    all_ids: set[str] = set()
    group_owners: dict[str, str] = {}
    verified_rows = 0
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"{manifest_path}: files object is missing")
    for split in ("train", "validation", "test"):
        expected = files.get(split)
        if not isinstance(expected, dict):
            raise ValueError(f"{manifest_path}: missing {split} file metadata")
        verified_rows += verify_split(
            args.dataset_dir,
            split,
            expected,
            all_ids,
            group_owners,
        )

    if verified_rows != manifest.get("total_rows"):
        raise ValueError(
            f"{manifest_path}: total row mismatch; manifest has "
            f"{manifest.get('total_rows')}, verified {verified_rows}"
        )

    print(
        json.dumps(
            {
                "status": "passed",
                "dataset_dir": str(args.dataset_dir.resolve()),
                "profile": args.expected_profile,
                "format": expected_format,
                "rows": verified_rows,
                "groups": len(group_owners),
                "train_sha256": files["train"]["sha256"],
                "validation_sha256": files["validation"]["sha256"],
                "test_sha256": files["test"]["sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
