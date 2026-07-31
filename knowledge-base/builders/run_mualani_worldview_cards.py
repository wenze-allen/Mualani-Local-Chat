#!/usr/bin/env python3
"""Generate isolated Mualani-perspective lore cards with Codex."""

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", nargs="*", default=[])
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def require_unique_strings(values: Any, field: str) -> None:
    if not isinstance(values, list) or not all(
        isinstance(item, str) for item in values
    ):
        raise ValueError(f"{field} must be a list of strings")
    if len(values) != len(set(values)):
        raise ValueError(f"{field} contains duplicate values")


def validate_card(card: dict[str, Any], evidence: dict[str, Any]) -> None:
    objective = evidence["objective_card"]
    target = evidence["target"]
    lore_id = evidence["lore_id"]
    expected = {
        "schema_version": "mualani-worldview-card-v1",
        "lore_id": lore_id,
        "name_zh": target["name_zh"],
        "name_en": target["name_en"],
        "aliases": target["aliases"],
        "activation_keys": target["activation_keys"],
        "objective_card_sha256": evidence["objective_card_sha256"],
        "evidence_bundle_sha256": evidence["evidence_bundle_sha256"],
    }
    for key, value in expected.items():
        if card.get(key) != value:
            raise ValueError(
                f"{key} mismatch: {card.get(key)!r} != {value!r}"
            )
    require_unique_strings(card["aliases"], "aliases")
    require_unique_strings(card["activation_keys"], "activation_keys")

    expected_fact_ids = [
        item["fact_id"] for item in objective["canonical_facts"]
    ]
    assessments = card.get("fact_assessments")
    if not isinstance(assessments, list):
        raise ValueError("fact_assessments must be a list")
    output_fact_ids = [item.get("fact_id") for item in assessments]
    if len(output_fact_ids) != len(set(output_fact_ids)):
        raise ValueError("fact_assessments contains duplicate fact IDs")
    if set(output_fact_ids) != set(expected_fact_ids):
        missing = sorted(set(expected_fact_ids) - set(output_fact_ids))
        foreign = sorted(set(output_fact_ids) - set(expected_fact_ids))
        raise ValueError(
            f"fact coverage mismatch: missing={missing}, foreign={foreign}"
        )

    allowed_scene_ids = {
        item["scene_id"]
        for item in evidence["candidate_mualani_scenes"]
    }
    for assessment in assessments:
        scene_ids = assessment.get("evidence_scene_ids")
        require_unique_strings(
            scene_ids,
            f"fact_assessments[{assessment.get('fact_id')}]."
            "evidence_scene_ids",
        )
        foreign_scenes = sorted(set(scene_ids) - allowed_scene_ids)
        if foreign_scenes:
            raise ValueError(
                f"foreign scene IDs for {assessment['fact_id']}: "
                f"{foreign_scenes}"
            )
        status = assessment["epistemic_status"]
        mode = assessment["response_mode"]
        if status in {"firsthand", "directly_told"} and not scene_ids:
            raise ValueError(
                f"{assessment['fact_id']} is {status} without scene evidence"
            )
        if status == "plausible_hearsay" and mode not in {
            "state_with_attribution",
            "admit_limited_knowledge",
            "do_not_volunteer",
        }:
            raise ValueError(
                f"{assessment['fact_id']} hearsay has incompatible mode {mode}"
            )
        if status == "inferred" and mode not in {
            "frame_as_inference",
            "admit_limited_knowledge",
            "do_not_volunteer",
        }:
            raise ValueError(
                f"{assessment['fact_id']} inference has incompatible mode {mode}"
            )
        if status == "unknown" and mode not in {
            "admit_limited_knowledge",
            "do_not_volunteer",
        }:
            raise ValueError(
                f"{assessment['fact_id']} unknown has incompatible mode {mode}"
            )

    runtime = card.get("runtime_injection", "")
    if not isinstance(runtime, str) or not runtime.strip():
        raise ValueError("runtime_injection is empty")
    forbidden_meta = ("fact_id", "Wiki", "schema", "资料卡", "审计")
    hits = [item for item in forbidden_meta if item in runtime]
    if hits:
        raise ValueError(f"runtime_injection contains meta terms: {hits}")
    if "她不知道「" in runtime or "她不知道“" in runtime:
        raise ValueError(
            "runtime_injection may be reverse-leaking an unknown named secret"
        )


def valid_existing(path: Path, evidence: dict[str, Any]) -> bool:
    try:
        validate_card(load_json(path), evidence)
        return True
    except Exception:
        return False


def organize_one(
    *,
    root: Path,
    lore_id: str,
    model: str,
    effort: str,
    retries: int,
    timeout_seconds: int,
    force: bool,
) -> dict[str, Any]:
    worldview_root = root / "mualani_worldview"
    evidence_path = worldview_root / "evidence" / f"{lore_id}.json"
    output_path = worldview_root / "cards" / f"{lore_id}.json"
    log_dir = worldview_root / "logs"
    capsule_dir = worldview_root / "capsules" / lore_id
    evidence = load_json(evidence_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    capsule_dir.mkdir(parents=True, exist_ok=True)
    (capsule_dir / "CAPSULE.txt").write_text(
        "This capsule intentionally contains no other lore cards.\n",
        encoding="utf-8",
    )

    if not force and valid_existing(output_path, evidence):
        return {"lore_id": lore_id, "status": "cached", "attempt": 0}

    template = (
        worldview_root
        / "prompts"
        / "organize_mualani_worldview_card_zh.txt"
    ).read_text(encoding="utf-8")
    prompt = template.format(
        evidence_bundle_json=json.dumps(
            evidence, ensure_ascii=False, indent=2
        )
    )
    schema_path = (
        worldview_root
        / "schema"
        / "mualani_worldview_card_v1.schema.json"
    ).resolve()
    env = os.environ.copy()
    last_error = ""
    for attempt in range(1, retries + 2):
        temp_output = output_path.with_suffix(f".attempt-{attempt}.tmp")
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
                    cwd=capsule_dir,
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
                    card = load_json(temp_output)
                    validate_card(card, evidence)
                except Exception as exc:
                    last_error = f"invalid structured result: {exc}"
                else:
                    temp_output.replace(output_path)
                    return {
                        "lore_id": lore_id,
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
                f"[retry] {lore_id}: attempt {attempt} failed: "
                f"{last_error}",
                flush=True,
            )
    return {
        "lore_id": lore_id,
        "status": "failed",
        "attempt": retries + 1,
        "error": last_error,
    }


def main() -> None:
    args = parse_args()
    if not 1 <= args.workers <= 32:
        raise SystemExit("--workers must be between 1 and 32")
    root = args.root.resolve()
    worldview_root = root / "mualani_worldview"
    manifest = load_json(worldview_root / "evidence" / "manifest.json")
    lore_ids = [
        item["lore_id"]
        for item in manifest["results"]
        if item["status"] == "ready"
    ]
    if args.only:
        requested = set(args.only)
        missing = sorted(requested - set(lore_ids))
        if missing:
            raise SystemExit(f"Unknown --only lore IDs: {missing}")
        lore_ids = [item for item in lore_ids if item in requested]

    print(
        f"Starting {len(lore_ids)} isolated Mualani-worldview organizers "
        f"with up to {args.workers} workers: {args.model}, "
        f"reasoning={args.reasoning_effort}",
        flush=True,
    )
    started = time.monotonic()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        pending = {
            executor.submit(
                organize_one,
                root=root,
                lore_id=lore_id,
                model=args.model,
                effort=args.reasoning_effort,
                retries=args.retries,
                timeout_seconds=args.timeout_seconds,
                force=args.force,
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
                        "error": f"worker exception: {exc}",
                    }
                results.append(result)
                print(
                    f"[{len(results)}/{len(lore_ids)}] {lore_id}: "
                    f"{result['status']} "
                    f"(attempt {result.get('attempt', '?')})",
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
        "schema_version": "mualani-worldview-run-report-v1",
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "workers": args.workers,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "results": sorted(results, key=lambda item: item["lore_id"]),
    }
    report_path = worldview_root / (
        "run_report.partial.json" if args.only else "run_report.json"
    )
    dump_json(report_path, report)
    failures = [item for item in results if item["status"] == "failed"]
    if failures:
        raise SystemExit(
            f"{len(failures)} organizers failed; see {report_path}"
        )


if __name__ == "__main__":
    main()
