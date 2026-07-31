#!/usr/bin/env python3
"""Run one Codex organizer per candidate with bounded parallelism and retries."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRINT_LOCK = threading.Lock()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--only",
        nargs="*",
        default=[],
        help="Optional character IDs to run.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def valid_existing(path: Path, character_id: str) -> bool:
    try:
        value = load_json(path)
        return (
            value.get("decision") in {"include", "exclude"}
            and value.get("card", {}).get("character_id") == character_id
        )
    except Exception:
        return False


def organize_one(
    *,
    root: Path,
    candidate: dict[str, Any],
    model: str,
    effort: str,
    retries: int,
    timeout_seconds: int,
    force: bool,
) -> dict[str, Any]:
    character_id = candidate["character_id"]
    evidence_path = root / "character_impressions" / "evidence" / f"{character_id}.json"
    raw_path = root / "character_impressions" / "raw_results" / f"{character_id}.json"
    log_dir = root / "character_impressions" / "logs"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    if not force and valid_existing(raw_path, character_id):
        return {"character_id": character_id, "status": "cached", "attempt": 0}

    prompt_template = (
        root / "character_impressions" / "prompts" / "organize_card_zh.txt"
    ).read_text(encoding="utf-8")
    prompt = prompt_template.format(
        evidence_path=evidence_path.relative_to(root).as_posix(),
        character_id=character_id,
    )
    schema_path = (
        root
        / "character_impressions"
        / "schema"
        / "mualani_impression_result_v2.schema.json"
    )
    env = os.environ.copy()

    last_error = ""
    for attempt in range(1, retries + 2):
        temp_output = raw_path.with_suffix(f".attempt-{attempt}.tmp")
        log_path = log_dir / f"{character_id}.attempt-{attempt}.log"
        command = [
            "codex",
            "exec",
            "-m",
            model,
            "-c",
            f'model_reasoning_effort="{effort}"',
            "-s",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--color",
            "never",
            "-C",
            str(root),
            "--output-schema",
            str(schema_path),
            "-o",
            str(temp_output),
            "-",
        ]
        started = time.monotonic()
        try:
            with log_path.open("w", encoding="utf-8") as log_handle:
                completed = subprocess.run(
                    command,
                    input=prompt,
                    text=True,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    cwd=root,
                    env=env,
                    timeout=timeout_seconds,
                    check=False,
                )
            elapsed = time.monotonic() - started
            if completed.returncode != 0:
                last_error = f"codex exit {completed.returncode}"
            elif not temp_output.exists():
                last_error = "codex produced no output file"
            else:
                try:
                    value = load_json(temp_output)
                    if value.get("card", {}).get("character_id") != character_id:
                        raise ValueError("character_id mismatch")
                    if value.get("decision") not in {"include", "exclude"}:
                        raise ValueError("invalid decision")
                except Exception as exc:
                    last_error = f"invalid structured result: {exc}"
                else:
                    temp_output.replace(raw_path)
                    return {
                        "character_id": character_id,
                        "status": "completed",
                        "attempt": attempt,
                        "elapsed_seconds": round(elapsed, 1),
                    }
        except subprocess.TimeoutExpired:
            last_error = f"timeout after {timeout_seconds}s"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        finally:
            if temp_output.exists():
                temp_output.unlink()

        with PRINT_LOCK:
            print(
                f"[retry] {character_id}: attempt {attempt} failed: {last_error}",
                flush=True,
            )

    return {
        "character_id": character_id,
        "status": "failed",
        "attempt": retries + 1,
        "error": last_error,
    }


def main() -> None:
    args = parse_args()
    if not 1 <= args.workers <= 32:
        raise SystemExit("--workers must be between 1 and 32")
    root = args.root.resolve()
    candidate_path = root / "character_impressions" / "candidates.json"
    candidates = load_json(candidate_path)["candidates"]
    if args.only:
        allowed = set(args.only)
        candidates = [item for item in candidates if item["character_id"] in allowed]
        missing = sorted(allowed - {item["character_id"] for item in candidates})
        if missing:
            raise SystemExit(f"Unknown --only character IDs: {missing}")

    evidence_manifest = root / "character_impressions" / "evidence" / "manifest.json"
    if not evidence_manifest.exists():
        raise SystemExit(
            "Evidence bundles are missing. Run scripts/build_mualani_impression_evidence.py first."
        )

    print(
        f"Starting {len(candidates)} Codex organizers with up to {args.workers} "
        f"parallel workers: {args.model}, reasoning={args.reasoning_effort}",
        flush=True,
    )
    started = time.monotonic()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        pending = {
            executor.submit(
                organize_one,
                root=root,
                candidate=candidate,
                model=args.model,
                effort=args.reasoning_effort,
                retries=args.retries,
                timeout_seconds=args.timeout_seconds,
                force=args.force,
            ): candidate["character_id"]
            for candidate in candidates
        }
        last_report = 0.0
        while pending:
            done, _ = wait(pending, timeout=10, return_when=FIRST_COMPLETED)
            for future in done:
                character_id = pending.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "character_id": character_id,
                        "status": "failed",
                        "error": f"worker exception: {exc}",
                    }
                results.append(result)
                print(
                    f"[{len(results)}/{len(candidates)}] {character_id}: "
                    f"{result['status']} (attempt {result.get('attempt', '?')})",
                    flush=True,
                )
            now = time.monotonic()
            if not done and now - last_report >= 30:
                print(
                    f"[monitor] completed={len(results)} running={len(pending)} "
                    f"elapsed={int(now - started)}s",
                    flush=True,
                )
                last_report = now

    report_path = root / "character_impressions" / "run_report.json"
    report = {
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "workers": args.workers,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "results": sorted(results, key=lambda item: item["character_id"]),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    failures = [item for item in results if item["status"] == "failed"]
    if failures:
        print(f"{len(failures)} organizers failed; see {report_path}", flush=True)
        raise SystemExit(1)

    assemble = subprocess.run(
        [sys.executable, str(root / "scripts" / "assemble_mualani_impression_cards.py")],
        cwd=root,
        check=False,
    )
    if assemble.returncode:
        raise SystemExit(assemble.returncode)
    print(
        f"All organizer jobs completed in {time.monotonic() - started:.1f}s.",
        flush=True,
    )


if __name__ == "__main__":
    main()
