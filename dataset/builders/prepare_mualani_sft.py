#!/usr/bin/env python3
"""Convert the extracted Mualani corpus into assistant-only SFT JSONL files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


DATASET_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_ROOT = DATASET_ROOT / "work" / "mualani_corpus"
DEFAULT_PERSONA_DIR = DATASET_ROOT / "config"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=DEFAULT_CORPUS_ROOT,
        help="Root of the extracted bilingual corpus.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DATASET_ROOT / "work" / "training_data",
        help="Parent directory for sft_zh/sft_en/sft_bilingual.",
    )
    parser.add_argument(
        "--language",
        choices=("zh", "en", "bilingual"),
        default="zh",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Use the strict source candidates instead of the default candidates.",
    )
    parser.add_argument("--seed", default="mualani-sft-v1")
    parser.add_argument("--validation-ratio", type=float, default=0.05)
    parser.add_argument("--test-ratio", type=float, default=0.05)
    parser.add_argument(
        "--traveler-gender",
        choices=("male", "female"),
        default="male",
        help="Resolve the game's gender-selection markup consistently.",
    )
    parser.add_argument(
        "--quality-profile",
        choices=("legacy", "chat-v2"),
        default="legacy",
        help=(
            "legacy reproduces the original row-per-subtitle dataset; chat-v2 "
            "merges split turns and removes samples that harm direct chat."
        ),
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
    return rows


def resolve_game_markup(text: str, language: str, gender: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"(?m)^#+", "", text).strip()
    # Keep the protagonist name as a stable noun. Replacing it with second
    # person creates broken compounds such as “你爷爷” for the game's
    # {NICKNAME}{M#爷爷}{F#奶奶} branch.
    text = text.replace(
        "{NICKNAME}", "旅行者" if language == "zh" else "Traveler"
    )

    pair_pattern = re.compile(r"\{M#([^{}]*)\}\{F#([^{}]*)\}")

    def choose_gender(match: re.Match[str]) -> str:
        return match.group(1 if gender == "male" else 2)

    text = pair_pattern.sub(choose_gender, text)
    text = re.sub(r"\{RUBY#\[[DS]\][^{}]*\}", "", text)
    text = re.sub(r"\{[MF]#([^{}]*)\}", r"\1", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compact_title(title: str) -> str:
    return title.rstrip("…。. ")


def voice_prompt(row: dict[str, Any], language: str) -> str:
    title = compact_title(str(row.get("voice_title") or row.get("title") or ""))
    category = str(row.get("voice_category") or "")

    if language == "zh":
        exact = {
            "初次见面": "你好！可以介绍一下自己吗？",
            "生日": "今天是我的生日。",
            "早上好": "早上好，玛拉妮。",
            "中午好": "中午好，玛拉妮。",
            "晚上好": "晚上好，玛拉妮。",
            "晚安": "晚安，玛拉妮。",
            "加入队伍": "玛拉妮，一起出发吧！",
        }
        if title in exact:
            return exact[title]
        if title.startswith("关于") and "·" in title:
            return f"你怎么看{title.split('·', 1)[1]}？"
        if category == "weather_environment":
            return f"现在{title}。"
        if category == "time_of_day":
            return f"{title}，玛拉妮。"
        if category == "birthday":
            return "今天是我的生日。"
        if category in {"favorite_food", "disliked_food", "hobby", "sharing"}:
            return f"想听你聊聊「{title}」。"
        if row.get("voice_group") == "combat":
            return f"【战斗情景：{title}】"
        return f"旅行者想听你聊聊「{title}」。"

    exact = {
        "Hello": "Hi! Could you introduce yourself?",
        "Birthday": "Today is my birthday.",
        "Good Morning": "Good morning, Mualani.",
        "Good Afternoon": "Good afternoon, Mualani.",
        "Good Evening": "Good evening, Mualani.",
        "Good Night": "Good night, Mualani.",
        "Joining the Party": "Mualani, let's head out together!",
    }
    if title in exact:
        return exact[title]
    if title.startswith("About ") and ":" in title:
        return f"What do you think about {title.split(':', 1)[1].strip()}?"
    if category == "weather_environment":
        return f"The situation right now is: {title}."
    if category == "time_of_day":
        return f"{title}, Mualani."
    if category == "birthday":
        return "Today is my birthday."
    if category in {"favorite_food", "disliked_food", "hobby", "sharing"}:
        return f"Tell me what you think about “{title}.”"
    if row.get("voice_group") == "combat":
        return f"[Combat situation: {title}]"
    return f"The Traveler asks Mualani about “{title}.”"


def scene_prompt(
    row: dict[str, Any], language: str, gender: str
) -> str:
    context = row.get("context_before") or []
    cleaned_context: list[tuple[str, str, str]] = []
    for item in context:
        text = resolve_game_markup(str(item.get("text") or ""), language, gender)
        if not text:
            continue
        speaker = str(item.get("speaker") or ("某人" if language == "zh" else "Someone"))
        if language == "zh":
            speaker = {
                "Player": "旅行者",
                "Traveler": "旅行者",
                "Black Screen": "旁白",
            }.get(speaker, speaker)
        else:
            speaker = {
                "Player": "Traveler",
                "旅行者": "Traveler",
                "Black Screen": "Narration",
            }.get(speaker, speaker)
        cleaned_context.append((speaker, text, str(item.get("kind") or "dialogue")))

    title = resolve_game_markup(str(row.get("title") or ""), language, gender)
    objective = resolve_game_markup(
        str(row.get("scene_objective") or ""), language, gender
    )
    if objective.casefold() in {"additional", "none", "null"}:
        objective = ""

    if language == "zh":
        lines: list[str] = []
        if title:
            lines.append(f"【场景】{title}")
        if objective and objective != title:
            lines.append(f"【当前情景】{objective}")
        if cleaned_context:
            lines.append("【此前对话】")
            for speaker, text, kind in cleaned_context:
                marker = "选项" if kind == "choice" else speaker
                lines.append(f"{marker}：{text}")
        else:
            lines.append("旅行者：玛拉妮？")
        lines.append("请自然接着说。")
        return "\n".join(lines)

    lines = []
    if title:
        lines.append(f"[Scene] {title}")
    if objective and objective != title:
        lines.append(f"[Current situation] {objective}")
    if cleaned_context:
        lines.append("[Previous dialogue]")
        for speaker, text, kind in cleaned_context:
            marker = "Choice" if kind == "choice" else speaker
            lines.append(f"{marker}: {text}")
    else:
        lines.append("Traveler: Mualani?")
    lines.append("Continue naturally.")
    return "\n".join(lines)


def scene_prompt_chat_v2(
    row: dict[str, Any], language: str, gender: str
) -> str:
    context = row.get("context_before") or []
    cleaned_context: list[tuple[str, str, str]] = []
    for item in context:
        text = resolve_game_markup(str(item.get("text") or ""), language, gender)
        if not text:
            continue
        speaker = str(item.get("speaker") or ("某人" if language == "zh" else "Someone"))
        if language == "zh":
            speaker = {
                "Player": "旅行者",
                "Traveler": "旅行者",
                "Black Screen": "旁白",
            }.get(speaker, speaker)
        else:
            speaker = {
                "Player": "Traveler",
                "旅行者": "Traveler",
                "Black Screen": "Narration",
            }.get(speaker, speaker)
        cleaned_context.append((speaker, text, str(item.get("kind") or "dialogue")))

    if not cleaned_context:
        raise ValueError(
            f"chat-v2 scene has no usable context: {row.get('dialogue_id')}"
        )

    title = resolve_game_markup(str(row.get("title") or ""), language, gender)
    objective = resolve_game_markup(
        str(row.get("scene_objective") or ""), language, gender
    )
    if objective.casefold() in {"additional", "none", "null"}:
        objective = ""

    if language == "zh":
        lines: list[str] = []
        if title:
            lines.append(f"【场景】{title}")
        if objective and objective != title:
            lines.append(f"【当前情景】{objective}")
        if len(cleaned_context) > 1:
            lines.append("【此前对话】")
            for speaker, text, kind in cleaned_context[:-1]:
                marker = "旅行者" if kind == "choice" else speaker
                lines.append(f"{marker}：{text}")
        speaker, text, kind = cleaned_context[-1]
        marker = "旅行者" if kind == "choice" else speaker
        lines.append("【必须回应的最后一句】")
        lines.append(f"{marker}：{text}")
        lines.append(
            "只说玛拉妮对此刻最后一句的完整回应；不要替别人说话，"
            "不要回应对方没有说过的提议。"
        )
        return "\n".join(lines)

    lines = []
    if title:
        lines.append(f"[Scene] {title}")
    if objective and objective != title:
        lines.append(f"[Current situation] {objective}")
    if len(cleaned_context) > 1:
        lines.append("[Previous dialogue]")
        for speaker, text, kind in cleaned_context[:-1]:
            marker = "Traveler" if kind == "choice" else speaker
            lines.append(f"{marker}: {text}")
    speaker, text, kind = cleaned_context[-1]
    marker = "Traveler" if kind == "choice" else speaker
    lines.append("[Last line that must be answered]")
    lines.append(f"{marker}: {text}")
    lines.append(
        "Give only Mualani's complete response to that last line. Do not speak "
        "for anyone else or agree with an idea that was never proposed."
    )
    return "\n".join(lines)


def group_id(row: dict[str, Any]) -> str:
    if row.get("source_type") == "CharacterVoice":
        return f"voice:{row.get('scene_id') or row.get('dialogue_id')}"
    source = row.get("source_file") or row.get("document_id") or "unknown"
    scene = row.get("scene_id") or row.get("document_id") or "unknown"
    return f"scene:{source}:{scene}"


def source_path(corpus_root: Path, language: str, strict: bool) -> Path:
    suffix = "_strict" if strict else ""
    return (
        corpus_root
        / "combined"
        / language
        / f"mualani_training_candidates{suffix}.jsonl"
    )


def make_example(
    row: dict[str, Any],
    language: str,
    gender: str,
    persona: str,
    quality_profile: str = "legacy",
) -> dict[str, Any]:
    target = resolve_game_markup(str(row.get("text") or ""), language, gender)
    if not target:
        raise ValueError(f"empty target after cleaning: {row.get('dialogue_id')}")

    if row.get("source_type") == "CharacterVoice":
        user = voice_prompt(row, language)
    elif quality_profile == "chat-v2":
        user = scene_prompt_chat_v2(row, language, gender)
    else:
        user = scene_prompt(row, language, gender)

    gid = group_id(row)
    return {
        "id": f"{language}:{row.get('dialogue_id')}",
        "language": language,
        "group_id": gid,
        "prompt": [
            {"role": "system", "content": persona},
            {"role": "user", "content": user},
        ],
        "completion": {"role": "assistant", "content": target},
        "metadata": {
            "dialogue_id": row.get("dialogue_id"),
            "source_type": row.get("source_type"),
            "source_file": row.get("source_file"),
            "document_id": row.get("document_id"),
            "scene_id": row.get("scene_id"),
            "title": row.get("title"),
            "voice_category": row.get("voice_category"),
            "merged_dialogue_ids": row.get(
                "_merged_dialogue_ids", [row.get("dialogue_id")]
            ),
        },
    }


def semantic_length(text: str) -> int:
    return len(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", text))


def chat_v2_filler_only(text: str) -> bool:
    return bool(
        re.fullmatch(
            r"[「『“\"']?(?:嗯+|唔+|呃+|诶+|欸+|啊+|哦+|哎+|哎呀|"
            r"哈哈+|嘿嘿+|好吧|好啊|行吧|是吗|这样啊|原来如此)"
            r"[」』”\"'，,。.!！?？…—~～\s]*",
            text.strip(),
        )
    )


def chat_v2_filler_start(text: str) -> bool:
    return bool(
        re.match(
            r"^[「『“\"']?(?:嗯+|唔+|呃+|诶+|欸+|啊+|哦+|噢+|"
            r"哇+|咦+|呀+|哟(?:呼|吼|哈)?|呜呼|呼呀|啊哈|(?:哎呀)+|"
            r"哈哈+|嘿嘿+|好吧|好啊)[，,。.!！?？…—~～\s]",
            text.strip(),
        )
    )


def merge_chat_v2_turns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge subtitle fragments that are consecutive Mualani lines."""

    by_id = {str(row.get("dialogue_id")): row for row in rows}
    successor_candidates: dict[str, list[str]] = {}
    predecessor: dict[str, str] = {}
    for row in rows:
        if row.get("source_type") == "CharacterVoice":
            continue
        context = row.get("context_before") or []
        if not context:
            continue
        previous_id = str(context[-1].get("id") or "")
        previous = by_id.get(previous_id)
        if (
            previous is None
            or previous.get("source_type") == "CharacterVoice"
            or group_id(previous) != group_id(row)
        ):
            continue
        current_id = str(row.get("dialogue_id"))
        successor_candidates.setdefault(previous_id, []).append(current_id)
        predecessor[current_id] = previous_id

    successor = {
        parent: children[0]
        for parent, children in successor_candidates.items()
        if len(children) == 1
    }
    eligible_predecessor = {
        child: parent
        for child, parent in predecessor.items()
        if successor.get(parent) == child
    }

    merged: list[dict[str, Any]] = []
    consumed: set[str] = set()
    for row in rows:
        row_id = str(row.get("dialogue_id"))
        if row_id in consumed or row_id in eligible_predecessor:
            continue
        chain = [row]
        current_id = row_id
        while current_id in successor:
            next_id = successor[current_id]
            if next_id in consumed:
                break
            chain.append(by_id[next_id])
            current_id = next_id
        for item in chain:
            consumed.add(str(item.get("dialogue_id")))

        combined = dict(chain[0])
        combined["text"] = "\n".join(
            str(item.get("text") or "").strip()
            for item in chain
            if str(item.get("text") or "").strip()
        )
        combined["_merged_dialogue_ids"] = [
            item.get("dialogue_id") for item in chain
        ]
        merged.append(combined)

    # Rows whose unique predecessor belonged to an earlier chain were consumed.
    # A defensive pass catches any branch-shaped rows not reached above.
    for row in rows:
        row_id = str(row.get("dialogue_id"))
        if row_id not in consumed:
            copied = dict(row)
            copied["_merged_dialogue_ids"] = [row.get("dialogue_id")]
            merged.append(copied)
    return merged


def chat_v2_exclusion_reason(
    row: dict[str, Any], language: str, gender: str
) -> str | None:
    if row.get("source_type") == "CharacterVoice":
        if row.get("voice_group") == "combat":
            return "combat_voice"
    else:
        context = row.get("context_before") or []
        if not context:
            return "scene_without_context"
        last_context = context[-1]
        last_speaker = str(last_context.get("speaker") or "")
        last_text = resolve_game_markup(
            str(last_context.get("text") or ""), language, gender
        )
        if last_speaker == "玛拉妮":
            return "unmerged_own_turn"
        if last_speaker == "Black Screen":
            return "narration_transition"
        if semantic_length(last_text) < 2:
            return "nonsemantic_last_utterance"
        if (
            str(last_context.get("kind") or "") == "choice"
            and re.fullmatch(r"（.*）|\(.*\)", last_text, flags=re.DOTALL)
        ):
            return "traveler_internal_monologue"
        if str(row.get("dialogue_id")) in {"150392017", "150420123"}:
            return "known_semantic_mismatch"

    text = resolve_game_markup(str(row.get("text") or ""), language, gender)
    if chat_v2_filler_only(text):
        return "filler_only"
    if semantic_length(text) < 10:
        return "too_short"
    if text.rstrip().endswith(("…", "——", "—")):
        return "fragment_ending"
    if text.lstrip().startswith(("…", "...")):
        return "leading_ellipsis"
    if chat_v2_filler_start(text):
        return "filler_start"
    return None


def split_for_group(
    gid: str, seed: str, validation_ratio: float, test_ratio: float
) -> str:
    digest = hashlib.sha256(f"{seed}\0{gid}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64
    if value < test_ratio:
        return "test"
    if value < test_ratio + validation_ratio:
        return "validation"
    return "train"


class DisjointSet:
    def __init__(self, values: Iterable[str]):
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            self.parent[right_root] = left_root
        else:
            self.parent[left_root] = right_root


def substantive_completion(text: str) -> bool:
    semantic_characters = re.findall(r"[\u3400-\u9fffA-Za-z0-9]", text)
    return len(semantic_characters) >= 8


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    args = parse_args()
    if args.quality_profile == "chat-v2" and args.language != "zh":
        raise ValueError(
            "chat-v2 currently has Chinese-specific speaker and filler rules; "
            "use --language zh or --quality-profile legacy"
        )
    if args.validation_ratio < 0 or args.test_ratio < 0:
        raise ValueError("split ratios must be non-negative")
    if args.validation_ratio + args.test_ratio >= 1:
        raise ValueError("validation_ratio + test_ratio must be below 1")

    languages = ("zh", "en") if args.language == "bilingual" else (args.language,)
    output_suffix = (
        f"sft_{args.language}"
        if args.quality_profile == "legacy"
        else f"sft_{args.language}_chat_v2"
    )
    output_dir = args.output_root / output_suffix
    output_dir.mkdir(parents=True, exist_ok=True)

    all_examples: list[dict[str, Any]] = []
    inputs: dict[str, str] = {}
    exclusion_counts: Counter[str] = Counter()
    source_rows_before_quality = 0
    source_rows_after_turn_merging = 0
    for language in languages:
        path = source_path(args.corpus_root, language, args.strict)
        if not path.is_file():
            raise FileNotFoundError(path)
        persona_path = DEFAULT_PERSONA_DIR / f"persona_{language}.txt"
        persona = persona_path.read_text(encoding="utf-8").strip()
        inputs[language] = str(path.resolve())
        language_rows = load_jsonl(path)
        source_rows_before_quality += len(language_rows)
        if args.quality_profile == "chat-v2":
            language_rows = merge_chat_v2_turns(language_rows)
        source_rows_after_turn_merging += len(language_rows)
        for row in language_rows:
            if args.quality_profile == "chat-v2":
                exclusion_reason = chat_v2_exclusion_reason(
                    row, language, args.traveler_gender
                )
                if exclusion_reason:
                    exclusion_counts[exclusion_reason] += 1
                    continue
            all_examples.append(
                make_example(
                    row,
                    language,
                    args.traveler_gender,
                    persona,
                    quality_profile=args.quality_profile,
                )
            )

    splits: dict[str, list[dict[str, Any]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    # Exact repeated targets must not leak across evaluation splits. Build
    # connected components of source scenes linked by a repeated target, while
    # preserving every context-specific training row.
    all_groups = {example["group_id"] for example in all_examples}
    components = DisjointSet(all_groups)
    completion_owner: dict[tuple[str, str], str] = {}
    for example in all_examples:
        completion_text = re.sub(
            r"\s+", " ", example["completion"]["content"]
        ).strip()
        if not substantive_completion(completion_text):
            continue
        completion_key = (
            example["language"],
            completion_text,
        )
        owner = completion_owner.setdefault(completion_key, example["group_id"])
        components.union(owner, example["group_id"])

    group_splits: dict[str, str] = {}
    for example in all_examples:
        gid = example["group_id"]
        component = components.find(gid)
        split = group_splits.setdefault(
            gid,
            split_for_group(
                component, args.seed, args.validation_ratio, args.test_ratio
            ),
        )
        splits[split].append(example)

    if not all(splits.values()):
        raise RuntimeError(
            "one or more splits are empty; change --seed or split ratios"
        )

    files: dict[str, dict[str, Any]] = {}
    for split, examples in splits.items():
        path = output_dir / f"{split}.jsonl"
        count = write_jsonl(path, examples)
        files[split] = {
            "path": path.name,
            "rows": count,
            "sha256": sha256_file(path),
        }

    source_types = Counter(
        example["metadata"]["source_type"] for example in all_examples
    )
    language_counts = Counter(example["language"] for example in all_examples)
    manifest = {
        "format": (
            "mualani-assistant-only-sft-v1"
            if args.quality_profile == "legacy"
            else "mualani-direct-chat-sft-v2"
        ),
        "language": args.language,
        "quality_profile": args.quality_profile,
        "strict_source": args.strict,
        "traveler_gender_resolution": args.traveler_gender,
        "seed": args.seed,
        "validation_ratio": args.validation_ratio,
        "test_ratio": args.test_ratio,
        "inputs": inputs,
        "total_rows": len(all_examples),
        "unique_groups": len(group_splits),
        "split_components_after_duplicate_linking": len(
            {components.find(group) for group in all_groups}
        ),
        "language_counts": dict(language_counts),
        "source_type_counts": dict(source_types),
        "quality_filter": {
            "source_rows_before_quality": source_rows_before_quality,
            "rows_after_turn_merging": source_rows_after_turn_merging,
            "excluded_after_merging": sum(exclusion_counts.values()),
            "exclusion_counts": dict(exclusion_counts),
        },
        "files": files,
        "notes": [
            "All rows sharing a source scene are assigned to the same split.",
            "Loss must be computed only on completion.content.",
            "Game gender/RUBY markup is resolved before training.",
            (
                "chat-v2 merges consecutive Mualani subtitle fragments, "
                "removes non-chat barks and incomplete replies, and makes the "
                "last utterance to answer explicit."
                if args.quality_profile == "chat-v2"
                else "legacy preserves the original row-per-subtitle behavior."
            ),
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
