#!/usr/bin/env python3
"""Download a pinned Hugging Face snapshot into the persistent project tree."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--revision",
        help="Commit/tag/branch. If omitted, resolve the current main commit first.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = os.environ.get("HF_TOKEN")
    api = HfApi(token=token)
    info = api.model_info(args.repo_id, revision=args.revision or "main")
    resolved_revision = info.sha
    args.output_dir.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id=args.repo_id,
        revision=resolved_revision,
        local_dir=args.output_dir,
        token=token,
        ignore_patterns=("*.gguf",),
    )

    manifest = {
        "repo_id": args.repo_id,
        "requested_revision": args.revision or "main",
        "resolved_commit": resolved_revision,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(args.output_dir.resolve()),
        "hf_home": os.environ.get("HF_HOME"),
        "ignored_patterns": ["*.gguf"],
    }
    manifest_path = args.output_dir / "download_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
