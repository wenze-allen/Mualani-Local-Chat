# 可复现性说明

[English](REPRODUCIBILITY.md)

### 公开链路

```text
用户自行提供的对白仓库
  -> 玛拉妮中英文语料提取
  -> 可选的固定版本角色语音导入
  -> 对白规范化与 chat-v2 构建
  -> 全量审计及按场景分组的训练/验证/测试切分
  -> BF16 Qwen3.5 LoRA（4B 或 9B）
  -> 合并后的 Transformers 模型
  -> F16 GGUF -> Q4_K_M GGUF

客观世界卡 + 玛拉妮在场场景
  -> 按词条隔离的证据包
  -> 玛拉妮认知特化
  -> 多轮语义复审
  -> 完整视角卡
  -> 精简运行时卡

完整角色名单 + 已审查角色印象 + 场景交集
  -> 证据约束的关系网
  -> 每个角色的联络边界

基础人格 + 关系索引 + 动态激活卡 + 回答模式 + 记忆
  -> 每一轮最终 system 上下文
```

所有需要维护的转换都由仓库中的源码、配置、Schema 或明确不变量表示。生成的
语料、checkpoints、模型权重、缓存和日志统一放在被忽略的工作目录中。

### 可复现级别

- **精确结构复现：**依靠公开代码、Schema、参数、提示词、随机种子和来源版本
  标识即可完成。
- **精确数据集字节：**需要完全相同的源仓库 revision 和外部语音页 revision；
  生成清单会提供各 split 哈希用于比较。
- **精确适配器字节：**即使随机种子相同，不同 GPU、CUDA kernel、PyTorch 版本
  或分布式设置也不保证逐字节一致，应同时比较指标与实际行为。
- **精确知识卡：**仓库内最终卡片和哈希清单是权威版本。重新调用语言模型整理
  时可能产生不同措辞，替换前必须重新通过 Schema 和语义复审。

### 验证

提交 PR 前运行两个验证器：

```bash
python scripts/validate-package.py
python scripts/validate-research.py
```

`validate-package.py` 保护可移植运行包；`validate-research.py` 检查 544 张完整
卡、哈希清单、客观卡与视角卡关联、运行时投影、虚构 SFT 格式、预设拼接和私人
路径边界。

### 版本记录

每次发布适配器或 GGUF 时应保留：

- 基座仓库与解析后的 commit；
- 语料 revision 与外部页面 revision；
- 数据集 manifest 与审计报告；
- train/validation/test SHA-256；
- 训练参数与依赖版本；
- GPU 名称、CUDA 版本、精度、有效 batch size 与耗时；
- adapter Run ID 与合并清单；
- llama.cpp commit、GGUF 转换参数、量化类型与输出哈希。
