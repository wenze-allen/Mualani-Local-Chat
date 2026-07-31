#!/usr/bin/env python3
"""Estimate wall time from the measured A800 chat-v2 baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("device", nargs="?", help="Device key, or omit to list keys.")
    parser.add_argument("--model", choices=("4b", "9b"), default="9b")
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--train-rows", type=int, default=503)
    args = parser.parse_args()

    baseline = json.loads(
        (ROOT / "benchmarks/a800_80gb_chat_v2.json").read_text(encoding="utf-8")
    )
    estimates = json.loads(
        (ROOT / "config/cuda_device_estimates.json").read_text(encoding="utf-8")
    )
    devices = estimates["devices"]
    if not args.device:
        for key, value in devices.items():
            print(f"{key:24} {value['label']}")
        return
    if args.device not in devices:
        raise SystemExit(f"Unknown device {args.device!r}; run without a device to list keys.")
    if args.epochs <= 0 or args.train_rows <= 0:
        raise SystemExit("--epochs and --train-rows must be positive")

    device = devices[args.device]
    observed = baseline["runs"][args.model]["train_runtime_seconds"]
    workload_scale = (args.epochs / 2.0) * (args.train_rows / 503.0)
    lower = observed * workload_scale / device["throughput_factor_high"]
    upper = observed * workload_scale / device["throughput_factor_low"]
    fit = device[f"{args.model}_fit"]
    print(f"Device: {device['label']}")
    print(f"Model: {args.model}; rows: {args.train_rows}; epochs: {args.epochs:g}")
    print(f"Estimated training time: {lower / 60:.1f}-{upper / 60:.1f} minutes")
    print(f"Configuration fit: {fit}")
    print("Estimate only; run 5-10 optimizer steps and extrapolate for the host.")


if __name__ == "__main__":
    main()
