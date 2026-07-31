#!/usr/bin/env python3
"""Run isolated semantic reviews over Mualani runtime lore cards."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRINT_LOCK = threading.Lock()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--only-from-review-dir", default="")
    parser.add_argument(
        "--only-verdict",
        choices=["pass", "revise"],
        default="",
    )
    parser.add_argument("--cards-dir", default="runtime_cards")
    parser.add_argument("--output-dir", default="runtime_reviews")
    parser.add_argument("--log-dir", default="runtime_review_logs")
    parser.add_argument(
        "--capsule-dir",
        default="runtime_review_capsules",
    )
    parser.add_argument(
        "--report-name",
        default="runtime_review_report.json",
    )
    return parser.parse_args()


def validate_review(
    review: dict[str, Any],
    *,
    lore_id: str,
    runtime_text: str,
) -> None:
    if review.get("lore_id") != lore_id:
        raise ValueError("lore_id mismatch")
    issues = review.get("issues")
    if not isinstance(issues, list):
        raise ValueError("issues must be a list")
    if review.get("verdict") == "pass":
        if issues:
            raise ValueError("pass review contains issues")
        if review.get("safe_replacement") != runtime_text:
            raise ValueError(
                "pass review did not preserve runtime text exactly"
            )
    elif review.get("verdict") == "revise":
        if not issues:
            raise ValueError("revise review contains no issues")
        if not str(review.get("safe_replacement", "")).strip():
            raise ValueError("revise review has empty replacement")
    else:
        raise ValueError("invalid verdict")


def review_one(
    root: Path,
    lore_id: str,
    model: str,
    effort: str,
    retries: int,
    timeout_seconds: int,
    force: bool,
    cards_dir_name: str,
    output_dir_name: str,
    log_dir_name: str,
    capsule_dir_name: str,
) -> dict[str, Any]:
    worldview_root = root / "mualani_worldview"
    runtime_card = load_json(
        worldview_root / cards_dir_name / f"{lore_id}.json"
    )
    objective = load_json(
        root / "world_lore_cards" / "raw_results" / f"{lore_id}.json"
    )
    output_path = worldview_root / output_dir_name / f"{lore_id}.json"
    log_dir = worldview_root / log_dir_name
    capsule_dir = worldview_root / capsule_dir_name / lore_id
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    capsule_dir.mkdir(parents=True, exist_ok=True)
    (capsule_dir / "CAPSULE.txt").write_text(
        "This review capsule contains exactly one lore topic.\n",
        encoding="utf-8",
    )
    runtime_text = runtime_card["runtime_injection"]
    if not force and output_path.exists():
        try:
            existing = load_json(output_path)
            validate_review(
                existing,
                lore_id=lore_id,
                runtime_text=runtime_text,
            )
            return {
                "lore_id": lore_id,
                "status": "cached",
                "verdict": existing["verdict"],
            }
        except Exception:
            pass

    fact_texts = {
        fact["fact_id"]: fact
        for fact in objective.get("canonical_facts", [])
    }
    bundle = {
        "lore_id": lore_id,
        "name_zh": runtime_card["name_zh"],
        "overall_knowledge": runtime_card["overall_knowledge"],
        "perspective_summary": runtime_card["perspective_summary"],
        "fact_assessments": [
            {
                **assessment,
                "objective_fact": fact_texts[assessment["fact_id"]],
            }
            for assessment in runtime_card["fact_assessments"]
        ],
        "runtime_injection": runtime_text,
    }
    template = (
        worldview_root
        / "prompts"
        / "review_mualani_worldview_runtime_zh.txt"
    ).read_text(encoding="utf-8")
    prompt = template.format(
        review_bundle_json=json.dumps(
            bundle, ensure_ascii=False, indent=2
        )
    )
    schema_path = (
        worldview_root
        / "schema"
        / "mualani_worldview_runtime_review_v1.schema.json"
    ).resolve()
    last_error = ""
    for attempt in range(1, retries + 2):
        temporary = output_path.with_suffix(f".attempt-{attempt}.tmp")
        log_path = log_dir / f"{lore_id}.attempt-{attempt}.log"
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
            str(capsule_dir),
            "--output-schema",
            str(schema_path),
            "-o",
            str(temporary),
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
                    cwd=capsule_dir,
                    env=os.environ.copy(),
                    timeout=timeout_seconds,
                    check=False,
                )
            if completed.returncode:
                last_error = f"codex exit {completed.returncode}"
            elif not temporary.exists():
                last_error = "no structured output"
            else:
                try:
                    review = load_json(temporary)
                    validate_review(
                        review,
                        lore_id=lore_id,
                        runtime_text=runtime_text,
                    )
                except Exception as exc:
                    last_error = f"invalid review: {exc}"
                else:
                    temporary.replace(output_path)
                    return {
                        "lore_id": lore_id,
                        "status": "completed",
                        "verdict": review["verdict"],
                        "elapsed_seconds": round(
                            time.monotonic() - started, 1
                        ),
                    }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        finally:
            if temporary.exists():
                temporary.unlink()
        with PRINT_LOCK:
            print(
                f"[retry] {lore_id}: {last_error}",
                flush=True,
            )
    return {
        "lore_id": lore_id,
        "status": "failed",
        "error": last_error,
    }


def main() -> None:
    args = parse_args()
    if not 1 <= args.workers <= 32:
        raise SystemExit("--workers must be between 1 and 32")
    root = args.root.resolve()
    lore_ids = sorted(
        path.stem
        for path in (
            root / "mualani_worldview" / "runtime_cards"
            if args.cards_dir == "runtime_cards"
            else root / "mualani_worldview" / args.cards_dir
        ).glob("*.json")
    )
    if args.only:
        requested = set(args.only)
        missing = sorted(requested - set(lore_ids))
        if missing:
            raise SystemExit(f"Unknown lore IDs: {missing}")
        lore_ids = [item for item in lore_ids if item in requested]
    if args.only_from_review_dir:
        review_root = (
            root
            / "mualani_worldview"
            / args.only_from_review_dir
        )
        selected_ids: set[str] = set()
        for review_path in review_root.glob("*.json"):
            review = load_json(review_path)
            if (
                not args.only_verdict
                or review.get("verdict") == args.only_verdict
            ):
                selected_ids.add(review_path.stem)
        lore_ids = [
            item for item in lore_ids if item in selected_ids
        ]
    print(
        f"Reviewing {len(lore_ids)} runtime cards with {args.workers} "
        f"workers: {args.model}, reasoning={args.reasoning_effort}",
        flush=True,
    )
    started = time.monotonic()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        pending = {
            executor.submit(
                review_one,
                root,
                lore_id,
                args.model,
                args.reasoning_effort,
                args.retries,
                args.timeout_seconds,
                args.force,
                args.cards_dir,
                args.output_dir,
                args.log_dir,
                args.capsule_dir,
            ): lore_id
            for lore_id in lore_ids
        }
        last_report = 0.0
        while pending:
            done, _ = wait(
                pending, timeout=10, return_when=FIRST_COMPLETED
            )
            for future in done:
                lore_id = pending.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "lore_id": lore_id,
                        "status": "failed",
                        "error": str(exc),
                    }
                results.append(result)
                print(
                    f"[{len(results)}/{len(lore_ids)}] {lore_id}: "
                    f"{result['status']} / "
                    f"{result.get('verdict', '-')}",
                    flush=True,
                )
            now = time.monotonic()
            if not done and now - last_report >= 30:
                print(
                    f"[monitor] completed={len(results)} "
                    f"running={len(pending)} "
                    f"elapsed={int(now - started)}s",
                    flush=True,
                )
                last_report = now
    report = {
        "schema_version": "mualani-worldview-runtime-review-report-v1",
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "workers": args.workers,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "results": sorted(results, key=lambda row: row["lore_id"]),
    }
    dump_json(
        root / "mualani_worldview" / args.report_name,
        report,
    )
    failures = [row for row in results if row["status"] == "failed"]
    if failures:
        raise SystemExit(f"{len(failures)} runtime reviews failed")


if __name__ == "__main__":
    main()
