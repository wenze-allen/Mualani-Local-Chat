# CUDA 训练时间估算

[English](ESTIMATED_TRAINING_TIME.md)

## 实测基线

已完成的 chat-v2 日志可以提供可靠的单卡基线。使用一张
NVIDIA A800-SXM4-80GB，在 503 条训练数据、26 条验证数据、两轮训练、最大长度
2048、BF16 LoRA 和 64 个 optimizer step 的条件下：

| 模型 | Micro batch / 梯度累积 | 实测训练时间 | 吞吐量 |
| --- | --- | ---: | ---: |
| Qwen3.5 4B | 2 / 8 | 888.1 秒（14.8 分钟） | 1.133 samples/s |
| Qwen3.5 9B | 1 / 16 | 1673.9 秒（27.9 分钟） | 0.601 samples/s |

包含软件版本和原始 Trainer 指标的基线保存在
`benchmarks/a800_80gb_chat_v2.json`。其中还记录了原始 metrics、运行清单和日志
的 SHA-256；这些原始文件包含站点路径和主机元数据，因此不直接公开。

## 工程估算

下表是假设数据、轮数、精度和单卡实现均不改变时的宽区间 wall-clock 估计。只有
A800 行来自实测；其他行根据架构、BF16 能力、显存带宽、小 batch 利用率，以及
小显存设备需要降低 micro batch 等因素推算，并不是厂商 benchmark。

| CUDA 设备 | 显存 | 4B 估计 | 9B 估计 | 直接运行预期 |
| --- | ---: | ---: | ---: | --- |
| H200 SXM | 141 GB | 6–9 分钟 | 12–17 分钟 | 两者预计均可 |
| H100 SXM | 80 GB | 7–10 分钟 | 13–19 分钟 | 两者预计均可 |
| A100 | 80 GB | 14–17 分钟 | 27–31 分钟 | 两者预计均可 |
| L40S | 48 GB | 11–18 分钟 | 22–33 分钟 | 9B 使用 batch 1 |
| RTX 6000 Ada | 48 GB | 13–20 分钟 | 24–38 分钟 | 9B 使用 batch 1 |
| RTX A6000 | 48 GB | 19–30 分钟 | 35–56 分钟 | 9B 使用 batch 1 |
| RTX 5090 | 32 GB | 9–15 分钟 | 能装下时约 18–28 分钟 | 先测量 9B 峰值显存 |
| RTX 4090 | 24 GB | 14–22 分钟 | 当前方案预计装不下 | 4B 使用 batch 1 |
| A10 | 24 GB | 30–50 分钟 | 当前方案预计装不下 | 4B 使用 batch 1 |

NVIDIA 公布的规格包括：A100 为 80 GB、约 2 TB/s；H100 SXM 超过 3 TB/s；
H200 为 141 GB、4.8 TB/s；L40S 为 48 GB、864 GB/s；RTX 6000 Ada 为
48 GB；RTX 5090 为 32 GB。这些规格可以确定容量和性能上限趋势，但不能直接
决定本 Transformer 训练实际达到的速度。

来源：[A100 数据表](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/a100/pdf/nvidia-a100-datasheet-nvidia-us-2188504-web.pdf)、
[Hopper 架构](https://developer.nvidia.com/blog/nvidia-hopper-architecture-in-depth/)、
[H200](https://www.nvidia.com/en-us/data-center/h200/)、
[L40S](https://www.nvidia.com/en-us/data-center/l40s/)、
[RTX 6000 Ada](https://www.nvidia.com/en-us/products/workstations/rtx-6000/)、
[RTX 5090](https://marketplace.nvidia.com/en-us/consumer/graphics-cards/nvidia-geforce-rtx-5090/)。

## 使用估算器

```bash
python training/estimate_training_time.py
python training/estimate_training_time.py h100_sxm_80gb --model 9b
python training/estimate_training_time.py l40s_48gb --model 4b \
  --train-rows 1000 --epochs 3
```

只有长度分布、micro batch、梯度累积、验证频率和 kernel 都相近时，耗时才会近似
按数据条数与轮数线性变化。面对新设备，可靠做法是先跑 5–10 个 optimizer step，
覆盖一次验证间隔，再按实测每步秒数外推。表中的“可以运行”也不是显存保证，
因为 allocator、序列长度、驱动和显示占用都会改变峰值显存。

24 GB 显卡没有提供 9B 耗时，是因为当前公开流程把完整基座保持为 BF16。要让
9B 装入这类显卡，通常需要 QLoRA、CPU offload、更短序列或不同 optimizer，已经
属于实质不同的实验，无法直接与本次实测耗时比较。
