# 知识库

[English](README.md)

### 范围

本目录公开用于生成运行时卡片的完整结构化知识。目前包括 21 张玛拉妮角色
印象卡、119 张关系边界卡、202 张客观世界观卡，以及 202 张玛拉妮视角
世界观卡。`app/cards` 下较小的文件只是这些完整卡片的运行时投影，并不是
研究记录的主版本。

当前纳入版本所依据的语料为 `OSCBWin6.7.54`。卡片记录的是这一版本已有
证据支持的内容，并不表示后续游戏版本已经自动纳入。

### 四层卡片

1. `world_lore_cards/cards` 保存可复用的客观世界资料，包括事实、时间范围、
   世界内可见性、来源、不确定性，以及被排除的纯玩法内容。
2. `mualani_worldview/cards` 把每条客观事实特化为玛拉妮的认知。每条事实会被
   判定为亲历、直接获知、职业知识、文化常识、可能听闻、推断或未知，并规定
   自然表达方式和防止全知的边界。
3. `character_impressions/cards` 只保存有证据支持的“玛拉妮怎样看待对方”，
   包括称呼、行为边界、证据引用、不确定项和运行时注入文本。
4. `mualani_relationships/cards` 把公开身份和私人相识分开，记录玛拉妮是否
   亲自认识对方、熟悉程度、所属地区，以及能否主动提议联络对方。

这种分层主要避免三类错误：把公开身份当成私人关系、让本地向导拥有百科式
全知，以及把一次剧情互动机械固化成永久性格规则。

### 角色视角特化流程

客观世界卡不会直接当作玛拉妮的知识注入。构建器会为每个词条建立隔离证据
包，其中只包含一张客观卡、统一认知档案，以及通过词面检索找到的玛拉妮在场
场景。每个整理任务都在新的进程中逐事实判断，而且只能引用该证据包内的场景
ID。之后通过独立复审检查知识越界、秘密反向泄漏、不自然的不确定表达和触发词
碰撞。通过的结果成为完整视角卡，应用端只导出其中精简的
`runtime_injection`。

隔离非常重要：整理一张卡时不会同时提供其他 201 张世界卡，因此无关词条
不会在批处理中悄悄污染当前卡片。

### 角色印象与关系网

角色候选来自玛拉妮在场剧情、明确提名、角色语音、可玩角色名单、伙伴角色和
选定的已公开角色。只有证据中存在明确评价、直接对话，或能够支持真实印象的
共同经历时，才会建立印象卡；仅仅同场不会自动通过。

关系网以 `mualani_relationships/roster.json` 中派生的完整角色名单保证
覆盖率，但只有已经通过审查的印象卡才能授予私人
相识。其余角色都会得到明确的 `no_evidence` 边界。熟悉程度与联络政策分别
记录：认识不等于对方随时有空；不认识也不等于拒绝由旅行者带领的初次见面。

### 重新构建

`builders` 下保留完整研究流水线。它们需要一个私有工作目录，其中包含
`YuanShenResources`、已提取的玛拉妮语料和生成的证据目录。原始对白和模型
生成日志属于输入与审计产物，不随本仓库分发。

典型顺序：

```bash
python knowledge-base/builders/extract_mualani_full_scenes.py --root WORK_ROOT
python knowledge-base/builders/build_mualani_impression_evidence.py --root WORK_ROOT
python knowledge-base/builders/run_mualani_impression_cards.py --root WORK_ROOT --workers 32
python knowledge-base/builders/assemble_mualani_impression_cards.py --root WORK_ROOT
python knowledge-base/builders/build_mualani_relationship_network.py \
  --root WORK_ROOT \
  --roster knowledge-base/mualani_relationships/roster.json
python knowledge-base/builders/build_mualani_worldview_evidence.py --root WORK_ROOT
python knowledge-base/builders/run_mualani_worldview_cards.py --root WORK_ROOT --workers 32
python knowledge-base/builders/audit_mualani_worldview_cards.py --root WORK_ROOT
python knowledge-base/builders/build_mualani_worldview_runtime_cards.py --root WORK_ROOT
python knowledge-base/builders/run_mualani_worldview_runtime_reviews.py \
  --root WORK_ROOT --workers 32
python knowledge-base/builders/promote_mualani_worldview_runtime_reviews.py \
  --root WORK_ROOT
python knowledge-base/builders/run_mualani_worldview_runtime_reviews.py \
  --root WORK_ROOT --workers 32 \
  --cards-dir reviewed_runtime_cards \
  --only-from-review-dir runtime_reviews --only-verdict revise \
  --output-dir runtime_reviews_round2 \
  --log-dir runtime_review_logs_round2 \
  --capsule-dir runtime_review_capsules_round2 \
  --report-name runtime_review_round2_report.json
python knowledge-base/builders/apply_mualani_worldview_round2_reviews.py \
  --root WORK_ROOT
python knowledge-base/builders/run_mualani_worldview_runtime_reviews.py \
  --root WORK_ROOT --workers 32 \
  --cards-dir final_runtime_cards \
  --only-from-review-dir runtime_reviews_round2 --only-verdict revise \
  --output-dir runtime_reviews_round3 \
  --log-dir runtime_review_logs_round3 \
  --capsule-dir runtime_review_capsules_round3 \
  --report-name runtime_review_round3_report.json
python knowledge-base/builders/audit_mualani_worldview_final_runtime.py \
  --root WORK_ROOT
```

三轮复审默认通过 Codex CLI 运行，模型名、推理强度、并行数、重试次数和超时
都可以通过命令行参数调整。第二轮只处理第一轮未通过项；第三轮只验证仍需修订
的替换结果，不会无声接受又一次改写。

在私有工作目录完成整理后，维护者用以下命令导入白名单中的最终产物、重新生成
哈希清单并导出运行时卡：

```bash
python scripts/import-research-assets.py --source-root WORK_ROOT
python scripts/export-runtime-cards.py \
  --characters knowledge-base/character_impressions/cards \
  --relationships knowledge-base/mualani_relationships/cards \
  --world knowledge-base/mualani_worldview/cards \
  --output app/cards
python scripts/validate-research.py
```
