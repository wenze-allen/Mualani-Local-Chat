# 第三方声明

[English](THIRD_PARTY_NOTICES.md)

## llama.cpp

运行程序是在 [llama.cpp](https://github.com/ggml-org/llama.cpp) 基础上修改的
纯文字下游构建，固定于 commit `e9fa0781f1c25fc4fe8c86be1edc6970661ad6f0`，
修改内容保存在 `overlay/`。

llama.cpp 使用 MIT License，其许可证文本收录在
[`licenses/llama.cpp-MIT.txt`](licenses/llama.cpp-MIT.txt)。

## 模型权重

模型权重不属于源码树，也不放入 Linux/Windows 程序包。兼容的玛拉妮 GGUF
分片作为独立 GitHub Release 资产发布，来源为 Huihui Qwen3.5 4B 与 9B 模型。
模型仓库把基座许可证标为 Apache-2.0。重新分发前应检查模型卡和全部上游条款：

- <https://huggingface.co/Allen0204/Mualani-Qwen3.5-LoRA-GGUF>
- <https://huggingface.co/huihui-ai/Huihui-Qwen3.5-4B-abliterated>
- <https://huggingface.co/huihui-ai/Huihui-Qwen3.5-9B-abliterated>

## 参考资料

运行时卡只包含精简事实摘要和行为边界；完整研究卡还保留短证据记录与页面版本。
研究过程以 Fandom 原神 Wiki 为主要公开参考，并用 BWiki 进行跨语言核验。
Fandom 社区文本通常采用 CC BY-SA 3.0。署名和来源链接见
[`SOURCES.zh-CN.md`](SOURCES.zh-CN.md)。仓库不包含游戏音频、完整对白库、生成
后的训练 split、checkpoint 或 Wiki 页面镜像。

## 同人项目声明

这是非官方、非商业同人研究项目，与 HoYoverse、米哈游或 Cognosphere 无隶属
或背书关系。《原神》、相关角色、名称与游戏内容属于各自权利人。
