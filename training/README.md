# LoRA Training Pipeline

[简体中文](README.zh-CN.md)

### Scope

This is the public, site-independent form of the training path used for the 4B
and 9B Mualani adapters. It covers pinned model download, dataset verification,
BF16 LoRA, checkpoint resume, safe merge, GGUF conversion, Q4_K_M
quantization, and a minimal llama.cpp load test. Training requires an NVIDIA
CUDA GPU; Slurm is optional.

Measured A800 timing and cautious estimates for other CUDA devices are kept in
[Estimated CUDA Training Time](ESTIMATED_TRAINING_TIME.md).

No cluster account, host name, Conda installation, output repository, or token
is hard-coded. Local settings belong in `config/local.env`, which is ignored by
Git. Start from `config/default.env.example`.

### Environment

Python 3.11 or 3.12 is recommended. Install a CUDA-compatible PyTorch build for
your driver first, then install the remaining packages:

```bash
python -m venv .venv
source .venv/bin/activate
# Install PyTorch using the command appropriate for the host CUDA version.
pip install -r training/requirements.txt
cp training/config/default.env.example training/config/local.env
```

The Qwen3.5 implementation must expose
`Qwen3_5ForConditionalGeneration`. Run this check before allocating a long GPU
job:

```bash
python -c 'import torch; from transformers import Qwen3_5ForConditionalGeneration; print(torch.cuda.is_available())'
```

### End-to-end commands

Build and audit the data first:

```bash
YUANSHEN_RESOURCES_DIR=/path/to/YuanShenResources dataset/build.sh
```

Download one or both bases:

```bash
training/scripts/download.sh 4b
training/scripts/download.sh 9b
training/scripts/download.sh all
```

Train directly on the current CUDA host:

```bash
training/scripts/train_local_cuda.sh 4b
training/scripts/train_local_cuda.sh 9b
```

Resume the full Trainer state by passing an explicit run ID and checkpoint:

```bash
training/scripts/train_local_cuda.sh 9b RUN_ID \
  training/work/models/adapters/9b/RUN_ID/checkpoints/checkpoint-125
```

For a generic Slurm cluster, copy `config/slurm.env.example` to
`config/slurm.env`, fill in the site's partition and resource values, then run:

```bash
training/scripts/train_slurm.sh 9b
```

Merge and quantize:

```bash
training/scripts/merge.sh 9b latest my-9b-merged
training/scripts/quantize_q4km.sh 9b \
  training/work/models/merged/9b/my-9b-merged
```

### Reviewed training design

- BF16 LoRA rather than 4-bit QLoRA was used on the original 80 GB A100-class
  run, avoiding a bitsandbytes dependency for the new architecture.
- LoRA rank is 16, alpha 32, dropout 0.05, learning rate `3e-5`, two epochs,
  maximum sequence length 2048, and seed 3407.
- Effective batch size is 16: 4B uses batch 2 with eight accumulation steps;
  9B uses batch 1 with sixteen accumulation steps.
- The adapter targets text-language-model attention, linear-attention, and MLP
  projection modules only. It does not train the visual tower or MTP layers.
- Evaluation and checkpoint saves occur throughout training. The final adapter,
  metrics, arguments, dependency versions, hardware information, truncation
  counts, and dataset manifest are retained per run.
- Dataset verification checks row counts, SHA-256, schema, unique IDs, scene
  grouping, and the audited chat-v2 profile before expensive training begins.

### Artifacts

All generated files stay under `training/work/` by default:

```text
models/base/        downloaded Hugging Face snapshots
models/adapters/    checkpoints and final PEFT adapters
models/merged/      merged BF16 Transformers models
models/quantized/   F16 and Q4_K_M GGUF plus checksums
logs/               per-run logs
tools/llama.cpp/    converter and quantizer checkout
```

These paths are excluded from Git. Publish adapters or GGUF weights as separate
release/Hugging Face artifacts and keep their base commit and SHA-256 manifest.

### Portability notes

`train_local_cuda.sh` checks CUDA directly and does not require Slurm.
`train_slurm.sh` is only a submission adapter around the same local script.
Institutions may provide a module loader, Conda activation, container command,
or launcher wrapper before invoking it; those site details do not belong in the
shared pipeline.

The quantization script deliberately builds a CPU llama.cpp converter. CUDA is
not required for quantization, although a many-core CPU and sufficient RAM make
merge and conversion faster. Pin `LLAMA_CPP_REVISION` for archival releases.
