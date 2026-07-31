# Mualani Local Chat

这是一个面向 Linux 与 Windows 的非官方、本地、纯文字玛拉妮角色聊天程序。它把
微调后的 Qwen3.5 GGUF、精简人物预设、玛拉妮视角的世界资料卡和关系边界接入同一
个终端程序，并支持保存会话、`/resume`、自动上下文压缩、`/model` 与长短回答切换。

## 下载

进入 [最新 GitHub Release](../../releases/latest)，按系统下载：

- Linux：`Mualani-Local-Chat-linux-x86_64.tar.gz`
- Windows：`Mualani-Local-Chat-windows-x64.zip`

程序包不包含模型。模型已经作为同一个 Release 中的独立 GGUF 分片提供：

- 4B：下载文件名包含 `4B-Chat-v2` 的 2 个分片。
- 9B：下载文件名包含 `9B-Chat-v2` 的 3 个分片。

同一模型的分片必须全部下载，并保持原文件名，分别放到：

```text
models/4b/Mualani-Qwen3.5-4B-Chat-v2-Q4_K_M-00001-of-00002.gguf
models/4b/Mualani-Qwen3.5-4B-Chat-v2-Q4_K_M-00002-of-00002.gguf

models/9b/Mualani-Qwen3.5-9B-Chat-v2-Q4_K_M-00001-of-00003.gguf
models/9b/Mualani-Qwen3.5-9B-Chat-v2-Q4_K_M-00002-of-00003.gguf
models/9b/Mualani-Qwen3.5-9B-Chat-v2-Q4_K_M-00003-of-00003.gguf
```

启动器会选择第一个分片，llama.cpp 会自动加载其余分片。只安装一个模型也能运行；
两个都安装后可在对话中用 `/model` 切换。下载校验值见
[`MODEL_SHA256SUMS.txt`](MODEL_SHA256SUMS.txt)。

## 启动

Linux：

```bash
./run.sh
```

Windows PowerShell：

```powershell
.\run-windows.ps1
```

启动器默认自动选择：检测到可用 Vulkan 设备时用显卡，否则使用 CPU。也可以强制：

```bash
MUALANI_BACKEND=cpu ./run.sh
MUALANI_BACKEND=vulkan ./run.sh
```

```powershell
.\run-windows.ps1 -Backend cpu
.\run-windows.ps1 -Backend vulkan
```

上次使用的模型和长/短回答模式保存在 `data/preferences.conf`，历史对话保存在
`data/sessions/`。

## 最小环境

发行包已包含程序和资料卡，不需要 Python、CUDA、ROCm、编译器或完整 llama.cpp。

- Linux：x86-64、较新的 glibc/libstdc++/libgomp、`libvulkan.so.1`、支持
  UTF-8/真彩色的终端。
- Windows：Windows 10/11 x64、PowerShell 5.1 或更新版本、含 Vulkan loader 的显卡驱动。
- Vulkan 加速：支持 Vulkan 1.2 的显卡与厂商驱动。
- 纯 CPU：64 位 x86 CPU；组合版程序仍需要 Vulkan loader，但不要求存在可用显卡。

磁盘占用估计：

| 模型 | GGUF 大小 | 建议预留空间 |
| --- | ---: | ---: |
| 仅 4B | 约 2.6 GiB | 4 GiB |
| 仅 9B | 约 5.3 GiB | 7 GiB |
| 4B + 9B | 约 7.9 GiB | 10 GiB |

启动器会按照检测到的显存或内存选择保守上下文。可通过 `MUALANI_VRAM_GIB`、
`MUALANI_CTX_4B`、`MUALANI_CTX_9B` 手动覆盖。Windows 的部分驱动无法准确上报
大显存容量，遇到上下文偏小时建议显式设置 `MUALANI_VRAM_GIB`。

## 对话命令

- `/mode`：切换短回答/长回答。
- `/model`：在已安装的 4B、9B 之间切换。
- `/resume`：恢复历史会话。
- `/compact`：把较早上下文压缩成摘要。
- `/cards`、`/relations`、`/lore`：查看当前激活的资料卡。
- `/clear`：清空当前对话。
- `/exit`：退出。

## 自行编译

构建脚本会拉取固定版本的 llama.cpp，再覆盖本仓库 `overlay/` 中的下游修改。精简
版本只保留 Qwen3.5、文字 CLI、本地回环服务、CPU 与 Vulkan；移除了其他模型架构、
多模态解码、Web UI、测试、示例和无关工具。

Linux 需要 Git、CMake、C++ 编译器、Vulkan 开发文件、`glslc` 与 SPIR-V headers：

```bash
./scripts/build-linux.sh
```

Windows 需要 Visual Studio C++ Build Tools、Git、CMake 和 LunarG Vulkan SDK：

```powershell
.\scripts\build-windows.ps1
```

输出位于 `dist/`。GitHub Actions 发布流程会分别构建 Linux 与 Windows 下载包。

## 范围与许可

源码树和平台程序包不包含训练集、检查点、LoRA adapter、游戏音频或整段对话库；
GGUF 权重仅作为独立 Release 资产发布。原创程序代码使用 MIT License；上游组件与资料来源见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。这是非官方、非商业同人研究项目，
与 HoYoverse、米哈游或 Cognosphere 无隶属或背书关系。
