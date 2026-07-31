# Contributing

[简体中文](CONTRIBUTING.zh-CN.md)

Small, reviewable fixes are welcome. Create a branch in your fork and open a
pull request against `main`; maintainers review changes before merge.

For runtime code changes, build the documented Linux or Windows package and
run a short CPU smoke test. For card changes, edit the complete card under
`knowledge-base/` first, regenerate the corresponding `app/cards` projection,
and state the factual basis and source revision in the pull request. For
dataset or training changes, preserve assistant-only loss, scene-grouped
splits, deterministic manifests, and generic site-independent configuration.

Run:

```bash
python scripts/validate-package.py
python scripts/validate-research.py
```

Do not commit raw dialogue archives, game audio, model weights, checkpoints,
generated training splits, conversation histories, authentication tokens,
private research logs, or site-specific account and cluster paths.
