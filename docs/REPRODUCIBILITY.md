# Reproducibility Map

[简体中文](REPRODUCIBILITY.zh-CN.md)

### Published chain

```text
user-supplied dialogue repository
  -> bilingual Mualani corpus extraction
  -> optional pinned character-voice import
  -> dialogue normalization and chat-v2 construction
  -> exhaustive audit and grouped train/validation/test split
  -> BF16 Qwen3.5 LoRA (4B or 9B)
  -> merged Transformers model
  -> F16 GGUF -> Q4_K_M GGUF

objective world cards + Mualani-present scenes
  -> isolated per-topic evidence bundles
  -> Mualani epistemic specialization
  -> semantic review rounds
  -> complete viewpoint cards
  -> compact runtime cards

complete roster + reviewed character impressions + scene intersections
  -> evidence-bounded relationship network
  -> per-character contact boundaries

base persona + relationship index + dynamically active cards + mode + memory
  -> final per-turn system context
```

Every maintained transformation is represented by checked-in source, a
configuration file, a schema, or a written invariant. Generated corpora,
checkpoints, model weights, caches, and logs live under ignored work
directories.

### Reproducibility levels

- **Exact structural reproduction:** possible from the public code, schemas,
  parameters, prompts, random seeds, and source revision identifiers.
- **Exact dataset bytes:** requires the same source repository revision and the
  pinned external voice-page revision. The generated manifest provides split
  hashes for comparison.
- **Exact adapter bytes:** not guaranteed across GPU models, CUDA kernels,
  PyTorch releases, or distributed settings even with the same seed. Compare
  metrics and behavior as well as hashes.
- **Exact knowledge cards:** the checked-in final cards and manifest hashes are
  authoritative. Regenerating LLM-organized cards may produce different prose;
  schema checks and semantic review are required before replacing them.

### Verification

Run both validators before a pull request:

```bash
python scripts/validate-package.py
python scripts/validate-research.py
```

`validate-package.py` protects the portable runtime. `validate-research.py`
checks 544 complete cards, their hash manifest, objective-to-viewpoint links,
runtime projections, synthetic SFT format, preset composition, and private-path
boundaries.

### Version records

Preserve the following for every published adapter or GGUF:

- base repository and resolved commit;
- corpus revision and external-page revision;
- dataset manifest and audit report;
- train/validation/test SHA-256 values;
- training arguments and dependency versions;
- GPU name, CUDA version, precision, effective batch size, and elapsed time;
- adapter run ID and merge manifest;
- llama.cpp commit, GGUF conversion flags, quantization type, and output hash.
