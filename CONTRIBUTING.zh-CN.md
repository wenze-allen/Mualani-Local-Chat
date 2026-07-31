# 贡献指南

[English](CONTRIBUTING.md)

欢迎提交范围小、便于审查的修改。请在自己的 fork 中建立分支，再向 `main` 提交
Pull Request，由维护者审查后合并。

修改运行代码时，应构建文档中的 Linux 或 Windows 程序包，并完成简短 CPU 冒烟
测试。修改卡片时，应先编辑 `knowledge-base/` 下的完整卡，再重新生成对应的
`app/cards` 投影，并在 PR 中说明事实依据和来源版本。修改数据或训练代码时，应
保留 assistant-only loss、按场景分组切分、确定性 manifest 和与站点无关的通用
配置。

运行：

```bash
python scripts/validate-package.py
python scripts/validate-research.py
```

不要提交原始对白库、游戏音频、模型权重、checkpoints、生成后的训练 split、对话
历史、认证 token、私有研究日志，或特定账户和集群路径。
