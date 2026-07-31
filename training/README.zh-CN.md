# LoRA 训练流水线

[English](README.md)

### 范围

这里公开的是 4B 与 9B 玛拉妮适配器训练路径的通用版本，包括固定版本的模型
下载、数据集验证、BF16 LoRA、checkpoint 恢复、安全合并、GGUF 转换、
Q4_K_M 量化，以及最小 llama.cpp 加载测试。训练需要 NVIDIA CUDA 显卡，
Slurm 只是可选调度层。

A800 实测用时及其他 CUDA 设备的保守估算见
[CUDA 训练时间估算](ESTIMATED_TRAINING_TIME.zh-CN.md)。

脚本不再固定集群账户、主机名、Conda 路径、输出仓库或 token。本地设置写入被
Git 忽略的 `config/local.env`，可从 `config/default.env.example` 开始填写。

### 环境

推荐 Python 3.11 或 3.12。先按照显卡驱动安装匹配 CUDA 的 PyTorch，再安装
其余依赖：

```bash
python -m venv .venv
source .venv/bin/activate
# 按当前主机 CUDA 版本安装合适的 PyTorch。
pip install -r training/requirements.txt
cp training/config/default.env.example training/config/local.env
```

Transformers 必须提供 `Qwen3_5ForConditionalGeneration`。申请长时间 GPU
任务前先检查：

```bash
python -c 'import torch; from transformers import Qwen3_5ForConditionalGeneration; print(torch.cuda.is_available())'
```

### 完整命令

先构建和审计数据：

```bash
YUANSHEN_RESOURCES_DIR=/path/to/YuanShenResources dataset/build.sh
```

下载一个或两个基座：

```bash
training/scripts/download.sh 4b
training/scripts/download.sh 9b
training/scripts/download.sh all
```

在当前 CUDA 主机直接训练：

```bash
training/scripts/train_local_cuda.sh 4b
training/scripts/train_local_cuda.sh 9b
```

传入明确的 Run ID 和 checkpoint 即可恢复完整 Trainer 状态：

```bash
training/scripts/train_local_cuda.sh 9b RUN_ID \
  training/work/models/adapters/9b/RUN_ID/checkpoints/checkpoint-125
```

在通用 Slurm 集群中，把 `config/slurm.env.example` 复制为
`config/slurm.env`，填写该站点的分区和资源后运行：

```bash
training/scripts/train_slurm.sh 9b
```

合并和量化：

```bash
training/scripts/merge.sh 9b latest my-9b-merged
training/scripts/quantize_q4km.sh 9b \
  training/work/models/merged/9b/my-9b-merged
```

### 已采用的训练设计

- 原始 80 GB A100 级别实验使用 BF16 LoRA，而不是 4-bit QLoRA，以避免新架构
  对 bitsandbytes 的额外依赖。
- LoRA rank 为 16、alpha 为 32、dropout 为 0.05、学习率为 `3e-5`、训练两轮、
  最大序列长度 2048、随机种子 3407。
- 有效 batch size 为 16：4B 使用 batch 2 和 8 次梯度累积；9B 使用 batch 1 和
  16 次梯度累积。
- 适配器只作用于文本语言模型的注意力、线性注意力和 MLP 投影层，不训练视觉塔
  或 MTP 层。
- 训练过程中持续执行验证和 checkpoint 保存；每个 Run 会保留最终适配器、指标、
  参数、依赖版本、硬件信息、截断计数和数据集清单。
- 昂贵训练开始前会检查行数、SHA-256、格式、唯一 ID、场景分组，以及已经通过
  审计的 chat-v2 profile。

### 产物

生成文件默认都位于 `training/work/`：

```text
models/base/        下载的 Hugging Face 基座快照
models/adapters/    checkpoints 与最终 PEFT 适配器
models/merged/      合并后的 BF16 Transformers 模型
models/quantized/   F16、Q4_K_M GGUF 与校验和
logs/               每次运行的日志
tools/llama.cpp/    转换器与量化器源码
```

这些路径都不会进入 Git。适配器和 GGUF 应作为独立 Release 或 Hugging Face
产物发布，并同时记录基础模型 commit 和 SHA-256 清单。

### 可移植性说明

`train_local_cuda.sh` 直接检查 CUDA，不依赖 Slurm；`train_slurm.sh` 只是对
同一个本地训练入口增加提交参数。不同机构可以在调用前自行加载 module、激活
Conda、进入容器或套一层启动脚本，这些站点专用信息不进入共享流水线。

量化脚本默认构建 CPU 版 llama.cpp 转换器，因此量化本身不要求 CUDA，不过更多
CPU 核心和足够内存会加快合并与转换。正式归档发布时应固定
`LLAMA_CPP_REVISION`。
