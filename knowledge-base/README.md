# Knowledge Base

[简体中文](README.zh-CN.md)

### Scope

This directory publishes the complete structured knowledge used to build the
runtime cards. It contains 21 Mualani character-impression cards, 119
relationship-boundary cards, 202 objective world-lore cards, and 202
Mualani-viewpoint world-lore cards. The smaller files under `app/cards` are a
projection of these full cards, not the canonical research records.

The checked-in corpus basis is `OSCBWin6.7.54`. A card records what was
supported at that revision; it is not a promise that later game releases are
already represented.

### Four card layers

1. `world_lore_cards/cards` stores reusable objective lore: facts, temporal
   scope, in-world visibility, source records, uncertainty, and excluded
   gameplay-only material.
2. `mualani_worldview/cards` specializes every objective fact to Mualani. Each
   fact is classified as firsthand, directly told, professionally known,
   culturally known, plausible hearsay, inferred, or unknown. The card also
   defines natural phrasing and omniscience boundaries.
3. `character_impressions/cards` stores only Mualani's evidenced impression of
   another character. It includes address terms, behavioral boundaries,
   evidence references, uncertainty, and the runtime injection.
4. `mualani_relationships/cards` separates public knowledge from private
   acquaintance. It states whether Mualani personally knows a character, how
   familiar they are, which region they belong to, and whether she may propose
   contacting them.

This separation prevents three common failures: treating public identity as a
personal relationship, giving a local guide encyclopedia-level knowledge, and
turning one quoted interaction into a permanent personality rule.

### Character specialization pipeline

Objective lore is never injected directly as Mualani's knowledge. The builder
creates one isolated evidence bundle per lore topic containing exactly one
objective card, the shared epistemic profile, and lexically retrieved scenes
in which Mualani is present. A fresh organizer process classifies every fact.
It may cite only scene IDs contained in that bundle. Independent review passes
then check overclaiming, reverse leakage of secrets, unnatural uncertainty,
and trigger collisions. The approved result becomes the full viewpoint card;
only its compact `runtime_injection` is exported to the application.

The isolation rule matters: organizers do not receive the other 201 lore
cards, so an unrelated topic cannot silently contaminate the current card.

### Character impressions and relationship network

Character candidates are discovered from Mualani-present scenes, explicit
mentions, character voice lines, playable characters, companion characters,
and selected announced characters. An impression card is accepted only when
the evidence contains an explicit evaluation, direct dialogue, or a shared
event that supports an actual impression. Mere co-occurrence is rejected.

The relationship builder starts from the derived complete roster in
`mualani_relationships/roster.json` for coverage, then
grants personal acquaintance only to characters with an approved impression
card. Every other roster member receives an explicit `no_evidence` boundary.
Familiarity and contact policy are separate: knowing someone does not imply
that they are always available, and not knowing someone does not require
refusing a Traveler-led introduction.

### Rebuilding

The scripts under `builders` preserve the research pipeline. They expect a
private work root containing `YuanShenResources`, the extracted Mualani corpus,
and generated evidence directories. Raw dialogue and model-generation logs are
inputs and audit artifacts; they are not bundled into this repository.

Typical order:

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

The three review rounds use Codex CLI by default. Model name, reasoning effort,
worker count, retries, and timeout are command-line parameters. Round two only
revisits round-one failures; round three verifies the remaining replacements
without silently accepting another rewrite.

After curating the private work root, maintainers import the allowlisted final
artifacts and regenerate the hash manifest:

```bash
python scripts/import-research-assets.py --source-root WORK_ROOT
python scripts/export-runtime-cards.py \
  --characters knowledge-base/character_impressions/cards \
  --relationships knowledge-base/mualani_relationships/cards \
  --world knowledge-base/mualani_worldview/cards \
  --output app/cards
python scripts/validate-research.py
```
