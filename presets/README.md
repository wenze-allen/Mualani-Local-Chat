# Preset and Dynamic Context Design

[简体中文](README.zh-CN.md)

### Principle

The preset is deliberately layered. Stable identity belongs in the short base
persona; topic-specific facts belong in cards; conversation memory belongs in
the compaction summary. Repeating all facts in one permanent system prompt
wastes context and makes unrelated facts influence every answer.

`preset_spec.json` records the exact composition order. `build_prompt.py`
provides a readable reference implementation using the checked-in full cards.
The production runtime implements the same order dynamically in C++.

### Layers

1. **Base persona:** identity, home, occupation, ownership of the watersports
   shop "Leisurely Puffer," relationship to the male Traveler, language, and broad behavior. It
   avoids long lists of catchphrases and scenario-specific instructions.
2. **Global relationship index:** a compact always-on list of established
   acquaintances and region contacts. This stops the model from selecting a
   famous local character merely because the user names a region.
3. **Character impression cards:** activated by aliases in the current user
   message. They describe how Mualani sees someone, not that person's general
   biography.
4. **Relationship boundary cards:** activated for named characters. They
   determine acquaintance, familiarity, region, and contact policy separately
   from public lore.
5. **Worldview cards:** activated by the longest matching term in the current
   user message. A compound term shadows a broader substring. Up to six cards
   are retained in LRU order.
6. **Response mode:** short mode defaults to one or two sentences; long mode
   defaults to four to eight sentences except for trivial greetings. A direct
   request for detail overrides short mode.
7. **Compaction summary:** trusted older conversation memory is appended after
   the behavioral layers and is explicitly marked as history rather than the
   current user message.

### Hidden draft consistency

When cards are active, the runtime checks an undisplayed draft against the
current relationship and worldview boundaries. Names introduced by the draft
may activate additional character or relationship cards. A material conflict
causes hidden regeneration with a concise correction. After two failed
regenerations, the runtime uses a grounded fallback instead of exposing a
validator refusal to the user.

The checker must distinguish a contradiction from harmless creativity. “I do
not know Yoimiya, but you can introduce us” is consistent; claiming that
Mualani can contact Yoimiya or knows her schedule is not. Limited knowledge of
Inazuma does not prevent agreeing to travel there.

### Build an inspectable prompt

```bash
python presets/build_prompt.py \
  --mode short \
  --character kachina \
  --relationship yoimiya \
  --world inazuma_overview \
  --output /tmp/mualani-prompt.txt
```

This command is for inspection and experiments. The application activates
cards from user text automatically and does not need a prebuilt monolithic
prompt.

### Updating the preset

Keep new stable identity facts in `base/`, response-length behavior in
`modes/`, and injection framing in `injection/`. Put character- or topic-bound
facts in full cards. Before adding a new base rule, first check whether the
failure can be represented as a relationship boundary, an epistemic boundary,
or a card-specific behavior; this keeps the permanent prompt small.
