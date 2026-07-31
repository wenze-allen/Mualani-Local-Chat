#!/usr/bin/env python3
"""Add Mualani's categorized character voice lines from Genshin BWIKI.

The script fetches a pinned MediaWiki revision, extracts the 角色/语音1
templates, creates Chinese/English/parallel corpora, and appends them to the
existing YuanShenResources dialogue corpora after normalized-text deduplication.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


API_URL = "https://wiki.biligame.com/ys/api.php"
PAGE_NAME = "玛拉妮语音"
PAGE_URL = "https://wiki.biligame.com/ys/玛拉妮语音"
LICENSE_NAME = "CC BY-NC-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
TEMPLATE_NAME = "角色/语音1"
USER_AGENT = "Mualani-LoRA-corpus-builder/1.0 (research dataset extraction)"

LANGUAGE_CONFIG = {
    "zh": {"character": "玛拉妮", "field": "语音内容"},
    "en": {"character": "Mualani", "field": "语音内容英语"},
}

DATASET_ROOT = Path(__file__).resolve().parents[1]

WEATHER_AND_ENVIRONMENT = {
    "下雨的时候…",
    "打雷的时候…",
    "下雪的时候…",
    "阳光很好…",
    "刮大风了…",
    "在沙漠的时候…",
}
TIME_OF_DAY = {"早上好…", "中午好…", "晚上好…", "晚安…"}
COMBAT_PREFIX_CATEGORIES = {
    "元素战技": "elemental_skill",
    "元素爆发": "elemental_burst",
    "冲刺开始": "sprint",
    "打开宝箱": "open_chest",
    "生命值低": "low_hp",
    "同伴生命值低": "ally_low_hp",
    "倒下": "fallen",
    "普通受击": "light_hit",
    "重受击": "heavy_hit",
    "加入队伍": "join_party",
}

BR_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=DATASET_ROOT / "work" / "mualani_corpus",
        help="Existing corpus directory produced by extract_mualani_corpus.py.",
    )
    parser.add_argument(
        "--revision",
        type=int,
        default=611723,
        help="Pinned BWIKI revision id. Use 0 to fetch the latest revision.",
    )
    return parser.parse_args()


def api_request(params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{API_URL}?{query}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_revision_metadata(revision: int) -> dict[str, Any]:
    params: dict[str, Any] = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "ids|timestamp",
        "format": "json",
        "formatversion": "2",
    }
    if revision:
        params["revids"] = revision
    else:
        params["titles"] = PAGE_NAME
    payload = api_request(params)
    pages = payload.get("query", {}).get("pages", [])
    if not pages:
        raise RuntimeError("BWIKI revision query returned no pages")
    page = pages[0]
    revisions = page.get("revisions", [])
    if not revisions:
        raise RuntimeError("BWIKI revision query returned no revisions")
    revision_data = revisions[0]
    return {
        "pageid": page["pageid"],
        "title": page["title"],
        "revid": revision_data["revid"],
        "parentid": revision_data.get("parentid"),
        "timestamp": revision_data["timestamp"],
    }


def fetch_wikitext(revision: int) -> str:
    params: dict[str, Any] = {
        "action": "parse",
        "prop": "wikitext",
        "format": "json",
        "formatversion": "2",
    }
    if revision:
        params["oldid"] = revision
    else:
        params["page"] = PAGE_NAME
    payload = api_request(params)
    wikitext = payload.get("parse", {}).get("wikitext")
    if isinstance(wikitext, dict):
        wikitext = wikitext.get("*")
    if not isinstance(wikitext, str):
        raise RuntimeError("BWIKI parse query returned no wikitext")
    return wikitext


def extract_balanced_templates(wikitext: str, template_name: str) -> list[str]:
    marker = "{{" + template_name
    blocks: list[str] = []
    search_from = 0
    while True:
        start = wikitext.find(marker, search_from)
        if start < 0:
            break
        depth = 0
        cursor = start
        end = -1
        while cursor < len(wikitext) - 1:
            token = wikitext[cursor : cursor + 2]
            if token == "{{":
                depth += 1
                cursor += 2
                continue
            if token == "}}":
                depth -= 1
                cursor += 2
                if depth == 0:
                    end = cursor
                    break
                continue
            cursor += 1
        if end < 0:
            raise RuntimeError(f"Unclosed template starting at character {start}")
        blocks.append(wikitext[start:end])
        search_from = end
    return blocks


def parse_template_parameters(block: str) -> dict[str, str]:
    parameter_re = re.compile(r"(?m)^\|([^=\n]+)=")
    matches = list(parameter_re.finditer(block))
    parameters: dict[str, str] = {}
    for index, match in enumerate(matches):
        value_start = match.end()
        value_end = matches[index + 1].start() if index + 1 < len(matches) else -2
        parameters[match.group(1).strip()] = block[value_start:value_end].strip()
    return parameters


def clean_voice_text(value: str) -> str:
    value = BR_RE.sub("\n", value)
    value = TAG_RE.sub("", value)
    value = html.unescape(value)
    lines = [line.strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def normalized_text(value: str) -> str:
    return " ".join(value.split())


def classify_voice(title: str) -> tuple[str, str, bool]:
    for prefix, category in COMBAT_PREFIX_CATEGORIES.items():
        if title.startswith(prefix):
            return "combat", category, False

    if title.startswith("初次见面"):
        category = "introduction"
    elif title.startswith("闲聊·"):
        category = "casual_chat"
    elif title in WEATHER_AND_ENVIRONMENT:
        category = "weather_environment"
    elif title in TIME_OF_DAY:
        category = "time_of_day"
    elif title.startswith("关于玛拉妮自己·"):
        category = "about_self"
    elif title.startswith("关于我们·"):
        category = "relationship_with_traveler"
    elif title.startswith("关于「神之眼」"):
        category = "vision"
    elif title.startswith("有什么想要分享"):
        category = "sharing"
    elif title.startswith("感兴趣的见闻"):
        category = "interesting_knowledge"
    elif title.startswith("关于"):
        category = "about_other_character"
    elif title.startswith("想要了解玛拉妮·"):
        category = "friendship_profile"
    elif title.startswith("玛拉妮的爱好"):
        category = "hobby"
    elif title.startswith("玛拉妮的烦恼"):
        category = "worry"
    elif title.startswith("喜欢的食物"):
        category = "favorite_food"
    elif title.startswith("讨厌的食物"):
        category = "disliked_food"
    elif title.startswith("收到赠礼·"):
        category = "gift_response"
    elif title.startswith("生日"):
        category = "birthday"
    elif title.startswith("突破的感受·"):
        category = "ascension"
    else:
        category = "other_profile"

    affinity_related = category not in {
        "introduction",
        "casual_chat",
        "weather_environment",
        "time_of_day",
    }
    return "profile", category, affinity_related


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_voice_records(
    templates: list[dict[str, str]],
    metadata: dict[str, Any],
    language: str,
) -> list[dict[str, Any]]:
    config = LANGUAGE_CONFIG[language]
    records: list[dict[str, Any]] = []
    for index, template in enumerate(templates, start=1):
        voice_title = template["语音类型"].strip()
        raw_text = template[config["field"]].strip()
        text = clean_voice_text(raw_text)
        voice_group, voice_category, affinity_related = classify_voice(voice_title)
        record_id = f"bwiki_voice_{index:03d}"
        records.append(
            {
                "language": language,
                "character": config["character"],
                "dialogue_id": record_id,
                "speaker": config["character"],
                "text": text,
                "raw_text": raw_text,
                "source_type": "CharacterVoice",
                "source_file": (
                    f"BWIKI/{PAGE_NAME}?oldid={metadata['revid']}"
                ),
                "source_url": (
                    f"{PAGE_URL}?oldid={metadata['revid']}"
                ),
                "source_license": LICENSE_NAME,
                "source_license_url": LICENSE_URL,
                "source_revision": metadata["revid"],
                "source_revision_timestamp": metadata["timestamp"],
                "document_id": str(metadata["pageid"]),
                "title": voice_title,
                "description": "玛拉妮角色资料页语音",
                "chapter": None,
                "scene_id": record_id,
                "scene_objective": voice_category,
                "scene_path": ["character_voice", str(index)],
                "branch_path": [],
                "context_before": [],
                "flags": {
                    "joint_speaker": False,
                    "contains_markup": raw_text != text,
                    "contains_hidden_marker": False,
                    "text_test_marker": False,
                    "metadata_test_marker": False,
                    "discarded_marker": False,
                    "empty_text": not bool(text),
                },
                "duplicate_sources": [],
                "source_occurrence_count": 1,
                "voice_index": index,
                "voice_title": voice_title,
                "voice_file": template["语音文件"].strip(),
                "voice_group": voice_group,
                "voice_category": voice_category,
                "profile_personality_or_affinity": affinity_related,
            }
        )
    return records


def compact_parallel_side(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "speaker": row["speaker"],
        "text": row["text"],
        "raw_text": row["raw_text"],
        "source_type": row["source_type"],
        "source_file": row["source_file"],
        "source_url": row["source_url"],
        "source_revision": row["source_revision"],
        "title": row["title"],
        "scene_id": row["scene_id"],
        "scene_objective": row["scene_objective"],
        "context_before": [],
        "flags": row["flags"],
        "voice_group": row["voice_group"],
        "voice_category": row["voice_category"],
        "profile_personality_or_affinity": row[
            "profile_personality_or_affinity"
        ],
    }


def merge_without_text_duplicates(
    base_rows: list[dict[str, Any]],
    additional_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen = {normalized_text(row["text"]) for row in base_rows}
    merged = list(base_rows)
    skipped: list[dict[str, Any]] = []
    for row in additional_rows:
        key = normalized_text(row["text"])
        if key in seen:
            skipped.append(row)
            continue
        seen.add(key)
        merged.append(row)
    return merged, skipped


def main() -> None:
    args = parse_args()
    corpus_root = args.corpus_root.resolve()
    if not (corpus_root / "zh" / "mualani_all.jsonl").exists():
        raise SystemExit(
            "Existing YuanShenResources corpus not found under "
            f"{corpus_root}"
        )

    requested_revision = args.revision
    revision_metadata = fetch_revision_metadata(requested_revision)
    revision = revision_metadata["revid"]
    wikitext = fetch_wikitext(revision)
    template_blocks = extract_balanced_templates(wikitext, TEMPLATE_NAME)
    templates = [parse_template_parameters(block) for block in template_blocks]

    required_fields = {
        "语音类型",
        "语音文件",
        "语音内容",
        "语音内容英语",
    }
    invalid_templates = [
        index
        for index, template in enumerate(templates, start=1)
        if not required_fields.issubset(template)
        or not all(template[field].strip() for field in required_fields)
    ]
    if invalid_templates:
        raise RuntimeError(
            f"Missing required fields in voice templates: {invalid_templates}"
        )
    if len(templates) != 76:
        raise RuntimeError(
            f"Expected 76 character voice templates, found {len(templates)}"
        )

    voice_records = {
        language: build_voice_records(
            templates, revision_metadata, language
        )
        for language in LANGUAGE_CONFIG
    }
    for language, rows in voice_records.items():
        if len({row["dialogue_id"] for row in rows}) != len(rows):
            raise RuntimeError(f"Duplicate generated ids in {language}")
        if len({normalized_text(row["text"]) for row in rows}) != len(rows):
            raise RuntimeError(f"Duplicate character voice texts in {language}")

    parallel_rows = [
        {
            "dialogue_id": zh_row["dialogue_id"],
            "zh": compact_parallel_side(zh_row),
            "en": compact_parallel_side(en_row),
        }
        for zh_row, en_row in zip(
            voice_records["zh"], voice_records["en"], strict=True
        )
    ]

    source_dir = corpus_root / "character_voice" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = source_dir / f"{PAGE_NAME}.oldid-{revision}.wikitext"
    snapshot_path.write_text(wikitext, encoding="utf-8")
    write_json(
        source_dir / "source_metadata.json",
        {
            **revision_metadata,
            "page_url": PAGE_URL,
            "revision_url": f"{PAGE_URL}?oldid={revision}",
            "api_url": API_URL,
            "license": LICENSE_NAME,
            "license_url": LICENSE_URL,
            "template_count": len(templates),
        },
    )

    write_jsonl(
        corpus_root
        / "character_voice"
        / "zh"
        / "mualani_character_voice.jsonl",
        voice_records["zh"],
    )
    write_jsonl(
        corpus_root
        / "character_voice"
        / "en"
        / "mualani_character_voice.jsonl",
        voice_records["en"],
    )
    write_jsonl(
        corpus_root
        / "character_voice"
        / "parallel"
        / "mualani_zh_en_character_voice.jsonl",
        parallel_rows,
    )

    combined_counts: dict[str, Any] = {}
    overlap_report: dict[str, Any] = {}
    base_variants = {
        "all": "mualani_all.jsonl",
        "training_candidates": "mualani_training_candidates.jsonl",
        "training_candidates_strict": (
            "mualani_training_candidates_strict.jsonl"
        ),
    }
    for variant, filename in base_variants.items():
        overlap_report[variant] = {}
        for language in LANGUAGE_CONFIG:
            base_rows = read_jsonl(corpus_root / language / filename)
            merged, skipped = merge_without_text_duplicates(
                base_rows, voice_records[language]
            )
            write_jsonl(
                corpus_root / "combined" / language / filename,
                merged,
            )
            combined_counts[f"{language}_{variant}"] = len(merged)
            overlap_report[variant][language] = {
                "base_rows": len(base_rows),
                "character_voice_rows": len(voice_records[language]),
                "skipped_normalized_text_duplicates": len(skipped),
                "combined_rows": len(merged),
            }

        base_parallel_filename = (
            "mualani_zh_en.jsonl"
            if variant == "all"
            else f"mualani_zh_en_{variant}.jsonl"
        )
        base_parallel = read_jsonl(
            corpus_root / "parallel" / base_parallel_filename
        )
        combined_parallel = base_parallel + parallel_rows
        write_jsonl(
            corpus_root
            / "combined"
            / "parallel"
            / base_parallel_filename,
            combined_parallel,
        )
        combined_counts[f"parallel_{variant}"] = len(combined_parallel)

    category_counts = dict(
        sorted(
            Counter(
                row["voice_category"] for row in voice_records["zh"]
            ).items()
        )
    )
    group_counts = dict(
        sorted(
            Counter(
                row["voice_group"] for row in voice_records["zh"]
            ).items()
        )
    )
    voice_stats = {
        "source": {
            **revision_metadata,
            "page_url": PAGE_URL,
            "revision_url": f"{PAGE_URL}?oldid={revision}",
            "license": LICENSE_NAME,
            "license_url": LICENSE_URL,
        },
        "voice_lines_per_language": len(voice_records["zh"]),
        "paired_voice_lines": len(parallel_rows),
        "missing_required_templates": invalid_templates,
        "voice_group_counts": group_counts,
        "voice_category_counts": category_counts,
        "profile_personality_or_affinity_lines": sum(
            row["profile_personality_or_affinity"]
            for row in voice_records["zh"]
        ),
        "weather_environment_lines": sum(
            row["voice_category"] == "weather_environment"
            for row in voice_records["zh"]
        ),
        "combat_lines": sum(
            row["voice_group"] == "combat" for row in voice_records["zh"]
        ),
        "overlap_and_combination": overlap_report,
        "combined_counts": combined_counts,
    }
    write_json(corpus_root / "character_voice" / "stats.json", voice_stats)

    root_stats_path = corpus_root / "stats.json"
    root_stats = read_json(root_stats_path)
    root_stats["character_voice_wiki"] = voice_stats
    write_json(root_stats_path, root_stats)
    print(json.dumps(voice_stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
