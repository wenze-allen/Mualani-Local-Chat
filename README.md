# Mualani Local Chat

An unofficial local, text-only Mualani character-chat runtime for Linux and
Windows. It combines a fine-tuned Qwen3.5 GGUF model with a concise persona
prompt, character relationship boundaries, Mualani-viewpoint world cards,
saved conversations, automatic context compaction, and in-session model and
response-length switching.

[简体中文说明](README.zh-CN.md)

## Download

Open the [latest GitHub Release](../../releases/latest) and choose one archive:

- `Mualani-Local-Chat-linux-x86_64.tar.gz`
- `Mualani-Local-Chat-windows-x64.zip`

Model weights are separate assets in the same GitHub Release:

- 4B: download both assets whose names contain `4B-Chat-v2`.
- 9B: download all three assets whose names contain `9B-Chat-v2`.

Keep every shard of the selected model under its original filename and place
the files in:

```text
models/4b/Mualani-Qwen3.5-4B-Chat-v2-Q4_K_M-00001-of-00002.gguf
models/4b/Mualani-Qwen3.5-4B-Chat-v2-Q4_K_M-00002-of-00002.gguf

models/9b/Mualani-Qwen3.5-9B-Chat-v2-Q4_K_M-00001-of-00003.gguf
models/9b/Mualani-Qwen3.5-9B-Chat-v2-Q4_K_M-00002-of-00003.gguf
models/9b/Mualani-Qwen3.5-9B-Chat-v2-Q4_K_M-00003-of-00003.gguf
```

The launcher selects the first shard and llama.cpp loads the remaining shards
automatically. One model is enough. If both are installed, `/model` switches
between them without discarding the conversation. SHA-256 checksums are in
[`MODEL_SHA256SUMS.txt`](MODEL_SHA256SUMS.txt).

## Run

Linux:

```bash
./run.sh
```

Windows PowerShell:

```powershell
.\run-windows.ps1
```

The launcher selects Vulkan when a compatible device is visible and otherwise
uses CPU inference. Force a backend when needed:

```bash
MUALANI_BACKEND=cpu ./run.sh
MUALANI_BACKEND=vulkan ./run.sh
```

```powershell
.\run-windows.ps1 -Backend cpu
.\run-windows.ps1 -Backend vulkan
```

The selected model and short/long response mode are remembered under `data/`.
Conversation histories are stored in `data/sessions/`.

## Runtime requirements

The release archive includes the application binary and runtime cards. Python,
CUDA, ROCm, a compiler, and the full llama.cpp source tree are not required.

- Linux: x86-64, a reasonably recent glibc/libstdc++/libgomp,
  `libvulkan.so.1`, and a terminal with UTF-8/true-color support.
- Windows: Windows 10/11 x64, PowerShell 5.1 or later, and a current display
  driver with the Vulkan loader.
- Vulkan acceleration: a Vulkan 1.2-capable GPU and vendor driver.
- CPU mode: a 64-bit x86 CPU; the Vulkan loader is still needed by the combined
  binary, but no Vulkan-capable GPU is required.

Approximate storage:

| Installed models | GGUF size | Recommended free space |
| --- | ---: | ---: |
| 4B only | 2.6 GiB | 4 GiB |
| 9B only | 5.3 GiB | 7 GiB |
| 4B + 9B | 7.9 GiB | 10 GiB |

The launcher chooses conservative context sizes from detected VRAM or RAM. Set
`MUALANI_VRAM_GIB`, `MUALANI_CTX_4B`, or `MUALANI_CTX_9B` to override detection.
On Windows, VRAM reporting can be inaccurate for some drivers, so an explicit
`MUALANI_VRAM_GIB` is recommended when the selected context is too small.

## Commands

- `/mode`: switch between short and long answers.
- `/model`: switch between installed 4B and 9B models.
- `/resume`: resume a saved conversation.
- `/compact`: summarize older context while retaining recent turns.
- `/cards`, `/relations`, `/lore`: show active runtime cards.
- `/clear`: start a fresh conversation.
- `/exit`: quit.

## Build from source

The build scripts fetch the pinned llama.cpp commit and apply the tracked
downstream overlay. The text-only build keeps Qwen3.5, the CLI loopback runtime,
CPU kernels, and Vulkan; it removes other model architectures, multimodal
decoders, the web UI, tests, examples, and unrelated tools.

Linux build dependencies include Git, CMake, a C++ compiler, Vulkan headers and
loader development files, `glslc`, and SPIR-V headers:

```bash
./scripts/build-linux.sh
```

For Windows, install Visual Studio C++ build tools, Git, CMake, and the LunarG
Vulkan SDK, then run:

```powershell
.\scripts\build-windows.ps1
```

Staged archives are created below `dist/`. See the release workflow for the
exact clean Linux and Windows build environments.

## Scope and licensing

The source tree and platform archives do not contain training data, checkpoints,
adapters, game audio, or copied dialogue archives. GGUF weights are published
only as separate Release assets. Original software is MIT licensed. Upstream and reference notices are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
