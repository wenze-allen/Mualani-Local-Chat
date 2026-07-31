# Dataset Construction

[简体中文](README.zh-CN.md)

### Purpose and boundary

This directory publishes the complete dataset design and the builders used for
the Mualani chat-v2 LoRA run. It does not contain the extracted game corpus or
the released train/validation/test files. A user supplies a locally obtained
`YuanShenResources` checkout; the scripts deterministically produce the same
schema and splitting policy.

The public synthetic row demonstrates the final format without reproducing a
game dialogue. Generated data is written below `dataset/work/`, which is
ignored by Git.

### Build

Place or point to the source repository, then run:

```bash
YUANSHEN_RESOURCES_DIR=/path/to/YuanShenResources \
  dataset/build.sh
```

Important overrides:

```bash
INCLUDE_BWIKI_VOICE=0                 # skip the pinned character-voice import
BWIKI_VOICE_REVISION=611723           # select the reviewed voice-page revision
CONTEXT_TURNS=8                       # maximum preceding structural turns
DATASET_LANGUAGE=zh                   # zh, en, or bilingual where supported
DATASET_PROFILE=chat-v2               # chat-v2 or legacy
TRAVELER_GENDER=male                  # resolve every gender branch consistently
VALIDATION_RATIO=0.05 TEST_RATIO=0.05
SPLIT_SEED=mualani-sft-v1
```

The final row schema is `schemas/sft_row_v1.schema.json`; the reviewed build
configuration is `config/mualani_chat_v2.json`.

### Construction stages

1. Scan Chinese and English dialogue JSON recursively and identify Mualani by
   speaker, retaining up to eight structurally valid preceding turns.
2. Keep an occurrence audit before deduplicating stable dialogue IDs. Prefer
   atomic quest/activity files over aggregate duplicates.
3. Optionally fetch the pinned Mualani character-voice page, classify profile,
   weather, time, affinity, food, birthday, and combat categories, then merge
   without normalized-text duplicates.
4. Resolve game markup. `{NICKNAME}` becomes `旅行者`/`Traveler`; every male or
   female branch is resolved with one selected protagonist gender. RUBY and
   formatting markers are removed.
5. Merge consecutive Mualani subtitle fragments into one complete assistant
   answer. This prevents the model from learning to stop after a filler or
   half-sentence.
6. For story dialogue, retain the scene and preceding speakers and explicitly
   identify the last utterance that must be answered. Other characters' lines
   remain conditioning context; only Mualani's answer is the completion.
7. Remove context-free story fragments, combat barks, filler-only answers,
   nonsemantic last utterances, internal-monologue choices, fragment endings,
   and known semantic mismatches.
8. Assign complete scenes to one split. Scenes connected by an exact,
   substantive repeated completion are unioned before hashing, preventing the
   same answer from leaking across train, validation, and test.
9. Generate SHA-256 manifests and run exhaustive schema, text-cleanliness,
   gender-resolution, split-leakage, and quality-triage audits.

### Why full dialogue context is used

Training only isolated Mualani lines teaches wording but discards what each
line answers. Chat-v2 therefore includes other speakers' preceding dialogue as
user-side context while computing loss only on Mualani's completion. The
context is capped and the final utterance is marked explicitly so the model is
less likely to answer an earlier proposal or speak for another character.

Character voice lines have no natural preceding turn, so the builder creates a
short intent-specific Traveler prompt from the voice category. Combat barks
are not converted into normal chat examples.

### Loss and truncation

The training loader renders explicit ChatML. System and user tokens receive
label `-100`; loss is computed only on assistant content. If a row exceeds the
maximum length, the persona and assistant target are preserved first and the
oldest user-side context is truncated. Overlong completions are truncated only
after reserving the minimum prompt structure, and counts are recorded in the
run manifest.
