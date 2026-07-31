# Estimated CUDA Training Time

[简体中文](ESTIMATED_TRAINING_TIME.zh-CN.md)

## Measured baseline

The completed chat-v2 logs provide a usable single-GPU baseline. On one
NVIDIA A800-SXM4-80GB, with 503 training rows, 26 validation rows, two epochs,
maximum length 2048, BF16 LoRA, and 64 optimizer steps:

| Model | Micro batch / accumulation | Measured training time | Throughput |
| --- | --- | ---: | ---: |
| Qwen3.5 4B | 2 / 8 | 888.1 s (14.8 min) | 1.133 samples/s |
| Qwen3.5 9B | 1 / 16 | 1673.9 s (27.9 min) | 0.601 samples/s |

The baseline, including software versions and raw Trainer metrics, is stored in
`benchmarks/a800_80gb_chat_v2.json`. It also records SHA-256 values for the
original metrics, run manifests, and logs; those raw files remain unpublished
because they include site-specific paths and host metadata.

## Engineering estimates

The following are broad wall-clock ranges for the same data, epochs, precision,
and one-GPU implementation. Only the A800 row was measured. Other rows are
estimates based on architecture, BF16 capability, memory bandwidth, expected
small-batch utilization, and the need to reduce micro batch on smaller cards.
They are not vendor benchmarks.

| CUDA device | VRAM | 4B estimate | 9B estimate | Direct-fit expectation |
| --- | ---: | ---: | ---: | --- |
| H200 SXM | 141 GB | 6–9 min | 12–17 min | both expected |
| H100 SXM | 80 GB | 7–10 min | 13–19 min | both expected |
| A100 | 80 GB | 14–17 min | 27–31 min | both expected |
| L40S | 48 GB | 11–18 min | 22–33 min | 9B use batch 1 |
| RTX 6000 Ada | 48 GB | 13–20 min | 24–38 min | 9B use batch 1 |
| RTX A6000 | 48 GB | 19–30 min | 35–56 min | 9B use batch 1 |
| RTX 5090 | 32 GB | 9–15 min | 18–28 min if it fits | measure 9B peak memory first |
| RTX 4090 | 24 GB | 14–22 min | not expected as published | 4B use batch 1 |
| A10 | 24 GB | 30–50 min | not expected as published | 4B use batch 1 |

NVIDIA documents 80 GB and roughly 2 TB/s for A100, over 3 TB/s for H100 SXM,
141 GB and 4.8 TB/s for H200, 48 GB and 864 GB/s for L40S, 48 GB for RTX 6000
Ada, and 32 GB for RTX 5090. Those specifications establish capacity and an
upper-bound trend; they do not determine this transformer's achieved speed.

Sources: [A100 datasheet](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/a100/pdf/nvidia-a100-datasheet-nvidia-us-2188504-web.pdf),
[Hopper architecture](https://developer.nvidia.com/blog/nvidia-hopper-architecture-in-depth/),
[H200](https://www.nvidia.com/en-us/data-center/h200/),
[L40S](https://www.nvidia.com/en-us/data-center/l40s/),
[RTX 6000 Ada](https://www.nvidia.com/en-us/products/workstations/rtx-6000/),
[RTX 5090](https://marketplace.nvidia.com/en-us/consumer/graphics-cards/nvidia-geforce-rtx-5090/).

## How to use the estimator

```bash
python training/estimate_training_time.py
python training/estimate_training_time.py h100_sxm_80gb --model 9b
python training/estimate_training_time.py l40s_48gb --model 4b \
  --train-rows 1000 --epochs 3
```

Runtime scales approximately with rows and epochs only when length distribution,
micro batch, gradient accumulation, evaluation frequency, and kernels remain
similar. For a new host, the reliable procedure is to run 5–10 optimizer steps,
include one evaluation interval, and extrapolate from measured seconds per
step. A fit label is not a memory guarantee because allocator behavior,
sequence lengths, drivers, and background display use can change peak VRAM.

The 24 GB cards are not listed for 9B because this published pipeline keeps the
full base in BF16. Making 9B fit there would normally require a materially
different experiment such as QLoRA, CPU offload, shorter sequences, or a
different optimizer, so its time would not be comparable to the measured run.
