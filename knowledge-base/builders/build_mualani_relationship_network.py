#!/usr/bin/env python3
"""Build Mualani's complete, evidence-bounded relationship network.

The playable roster is used only as a coverage list. Personal familiarity is
granted exclusively by the already audited Mualani impression cards. Everyone
else receives an explicit "no evidence of personal acquaintance" boundary.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

FAMILIARITY_OVERRIDES = {
    "traveler": "close_trusted",
    "paimon": "close_trusted",
    "kachina": "close_trusted",
    "chasca": "established_familiar",
    "citlali": "established_familiar",
    "kinich": "established_familiar",
    "mavuika": "established_familiar",
    "xilonen": "established_familiar",
    "bennett": "established_familiar",
    "iansan": "familiar",
    "ifa": "familiar",
    "ororon": "familiar",
    "varesa": "familiar",
    "ajaw": "familiar",
    "arataki_itto": "recent_shared_experience",
    "barbara": "recent_shared_experience",
    "linnea": "recent_shared_experience",
    "nilou": "recent_shared_experience",
    "venti": "recent_shared_experience",
    "yumemizuki_mizuki": "recent_shared_experience",
    "kuki_shinobu": "limited_indirect_acquaintance",
}

FAMILIARITY_LABELS = {
    "close_trusted": "亲近且互相信任",
    "established_familiar": "已有较充分共同经历的熟人",
    "familiar": "熟悉的同伴或熟人",
    "recent_shared_experience": "近期因共同经历而认识",
    "limited_indirect_acquaintance": "知道并记得对方，但交集有限",
    "no_evidence": "没有私人相识证据",
}

CONTACT_POLICIES = {
    "close_trusted": "may_freely_propose_contact",
    "established_familiar": "may_propose_when_contextually_relevant",
    "familiar": "may_propose_when_contextually_relevant",
    "recent_shared_experience": "may_suggest_reconnecting_if_context_fits",
    "limited_indirect_acquaintance": "do_not_propose_without_user_naming",
    "no_evidence": "do_not_propose_or_claim_contact",
}

REGION_ZH_TO_EN = {
    "蒙德": "Mondstadt",
    "璃月": "Liyue",
    "稻妻": "Inazuma",
    "须弥": "Sumeru",
    "枫丹": "Fontaine",
    "纳塔": "Natlan",
    "挪德卡莱": "Nod-Krai",
    "至冬": "Snezhnaya",
    "其他": "Other",
}
REGION_EN_TO_ZH = {value: key for key, value in REGION_ZH_TO_EN.items()}

REGION_ORDER = [
    "Natlan",
    "Mondstadt",
    "Liyue",
    "Inazuma",
    "Sumeru",
    "Fontaine",
    "Nod-Krai",
    "Snezhnaya",
    "Other",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--roster",
        type=Path,
        default=ROOT / "mualani_relationships" / "roster.json",
        help=(
            "Derived playable/satellite coverage roster. Refresh this file "
            "from the source URLs recorded in network.json when the game adds "
            "characters; raw API or wiki snapshots are not committed."
        ),
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def build_roster(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if payload.get("schema_version") != "mualani-relationship-roster-v1":
        raise RuntimeError(f"unsupported relationship roster: {path}")
    roster = payload["characters"]
    roster.sort(key=lambda item: item["character_id"])
    ids = [item["character_id"] for item in roster]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate relationship roster IDs")
    return roster


def scan_mualani_scenes(
    root: Path, roster: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    scene_path = (
        root
        / "character_impressions"
        / "scope_audit"
        / "mualani_full_scenes.jsonl"
    )
    scenes = [
        json.loads(line)
        for line in scene_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    output: dict[str, dict[str, Any]] = {}
    for character in roster:
        name = character["name_zh"]
        speaker_scenes: set[str] = set()
        mualani_mentions: list[str] = []
        for scene in scenes:
            scene_ref = f"{scene['source_file']}#{scene['scene_id']}"
            for turn in scene["turns"]:
                speaker = turn["speaker_zh"]
                text = turn["text_zh"]
                if (
                    speaker == name
                    or speaker.startswith(name + "（")
                    or speaker.startswith(name + "(")
                ):
                    speaker_scenes.add(scene_ref)
                if (
                    len(name) >= 2
                    and "玛拉妮" in speaker
                    and name in text
                ):
                    mualani_mentions.append(scene_ref)
        output[character["character_id"]] = {
            "speaker_scene_count": len(speaker_scenes),
            "mualani_mention_count": len(mualani_mentions),
            "scene_refs": sorted(speaker_scenes | set(mualani_mentions)),
        }
    return output


def contact_policy_zh(policy: str) -> str:
    return {
        "may_freely_propose_contact": "可以自然主动提议去找、邀请或联络，但仍不能擅自断言对方有空。",
        "may_propose_when_contextually_relevant": "话题和地点合适时可以提议联系；不得把熟悉夸大为随叫随到。",
        "may_suggest_reconnecting_if_context_fits": "只有目的和地点确实合适时才可提议再次见面；不得写成经常来往。",
        "do_not_propose_without_user_naming": "不应主动把对方列为拜访对象；用户点名时也要保留交集有限的尺度。",
        "do_not_propose_or_claim_contact": "不得主动提议去找对方，也不得声称能联络、知道其日程或知道其是否难约。",
    }[policy]


def unknown_runtime_line(name_zh: str) -> str:
    return (
        f"现有玛拉妮语音与共同剧情没有证明她和{name_zh}有私人交情。"
        "世界资料若只提供对方的公开身份，只能当作公开知识，不能据此写成"
        "玛拉妮亲自认识、联系过、知道对方日程或知道对方是否难约。"
        "回答涉及两人关系、拜访或邀约时，玛拉妮必须先明确说自己没有"
        "见过或并不认识此人；没有另行提供的玛拉妮视角证据时，也不得"
        "臆测此人的性格、习惯、心情或会怎样看待玛拉妮。"
        "玛拉妮不能主动把此人当作当地联系人；若旅行者点名想拜访，"
        "可以同意同行，但应由旅行者带路或介绍，或先打听公开渠道。"
    )


def make_runtime_summary(cards: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    region_contacts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        if card["familiarity"] != "no_evidence":
            grouped[card["familiarity"]].append(card)
            if card["contact_policy"] in {
                "may_freely_propose_contact",
                "may_propose_when_contextually_relevant",
                "may_suggest_reconnecting_if_context_fits",
            }:
                region_contacts[card["region"]].append(card)

    lines = [
        "【玛拉妮的人际关系边界】",
        "“知道一个人的名字或公开身份”不等于“和这个人认识”。"
        "判断私交、称呼、联络能力和拜访建议时，以本关系网为准，"
        "不得用一般世界知识补造关系。",
    ]
    for tier in (
        "close_trusted",
        "established_familiar",
        "familiar",
        "recent_shared_experience",
        "limited_indirect_acquaintance",
    ):
        people = sorted(grouped[tier], key=lambda item: item["name_zh"])
        if not people:
            continue
        names = "、".join(item["name_zh"] for item in people)
        lines.append(f"- {FAMILIARITY_LABELS[tier]}：{names}。")
    lines.extend(
        [
            "- 上述名单之外的其他角色：一律视为没有私人相识证据。"
            "即使玛拉妮知道其公开身份，也不得说自己见过、认识、能联系、"
            "知道其行程或知道其是否难约。",
            "- 当旅行者没有点名，只问“去当地找谁”“叫谁来玩”时，"
            "只能从下方对应地区的已认识联系人中提议；"
            "不能随手挑选当地名人或其他可玩角色。",
        ]
    )
    for region in REGION_ORDER:
        people = sorted(
            region_contacts.get(region, []), key=lambda item: item["name_zh"]
        )
        names = "、".join(item["name_zh"] for item in people) if people else "无"
        lines.append(f"- {region} 可考虑联系的人：{names}。")
    lines.extend(
        [
            "- 若目的地没有已认识联系人，玛拉妮应直说自己在那里没有熟人，"
            "再问旅行者是否有认识的人，或提议先游玩、再通过公开渠道打听；"
            "不能为了让回答显得具体而捏造一个联系人。",
            "- 用户主动点名关系网外的人时，可以接受“去拜访”的计划，"
            "但第一句话必须明确说明自己没见过、没认识或不熟；"
            "把旅行者当作带路或介绍的一方。没有人物印象或世界资料支持时，"
            "简短说不认识即可，不要为了圆场捏造“听说过”、职业、性格或评价。"
            "不认识不等于拒绝同行。不得倒过来表现成玛拉妮"
            "本来就与对方熟识，也不得凭一般印象臆测对方的性格、心情、"
            "日程或会如何看待玛拉妮。",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    output_root = root / "mualani_relationships"
    cards_dir = output_root / "cards"
    if cards_dir.exists():
        shutil.rmtree(cards_dir)
    cards_dir.mkdir(parents=True)

    roster = build_roster(args.roster.resolve(strict=True))
    scene_scan = scan_mualani_scenes(root, roster)
    impression_dir = root / "character_impressions" / "cards"
    impression_cards = {
        path.stem: load_json(path) for path in impression_dir.glob("*.json")
    }
    excluded = {
        row["character_id"]: row
        for row in (
            json.loads(line)
            for line in (
                root / "character_impressions" / "excluded_characters.jsonl"
            )
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
    }

    roster_ids = {item["character_id"] for item in roster}
    missing_impression_ids = sorted(set(impression_cards) - roster_ids)
    if missing_impression_ids:
        raise RuntimeError(
            f"impression cards missing from relationship roster: {missing_impression_ids}"
        )
    unreviewed_intersections = []
    cards = []
    for item in roster:
        character_id = item["character_id"]
        impression = impression_cards.get(character_id)
        scan = scene_scan[character_id]
        if (
            impression is None
            and character_id not in excluded
            and (scan["speaker_scene_count"] or scan["mualani_mention_count"])
        ):
            unreviewed_intersections.append(
                {
                    "character_id": character_id,
                    "name_zh": item["name_zh"],
                    "scan": scan,
                }
            )

        aliases = list(dict.fromkeys(item["aliases"]))
        if impression:
            aliases = list(
                dict.fromkeys(impression.get("activation_keys", []) + aliases)
            )
            familiarity = FAMILIARITY_OVERRIDES[character_id]
            personal_acquaintance = True
            basis = {
                "status": "supported_by_impression_card",
                "impression_card": (
                    f"character_impressions/cards/{character_id}.json"
                ),
                "evidence_types": impression.get("evidence_types", []),
                "scene_scan": scan,
            }
        else:
            familiarity = "no_evidence"
            personal_acquaintance = False
            basis = {
                "status": (
                    "reviewed_and_excluded"
                    if character_id in excluded
                    else "no_intersection_found"
                ),
                "exclusion_reason": excluded.get(character_id, {}).get(
                    "reason", ""
                ),
                "scene_scan": scan,
            }
        policy = CONTACT_POLICIES[familiarity]
        runtime_injection = (
            (
                f"所属地区：{REGION_EN_TO_ZH.get(item['region'], item['region'])}。"
                f"关系级别：{FAMILIARITY_LABELS[familiarity]}。"
                f"{contact_policy_zh(policy)}"
            )
            if personal_acquaintance
            else unknown_runtime_line(item["name_zh"])
        )
        card = {
            "schema_version": "mualani-relationship-card-v1",
            "character_id": character_id,
            "name_zh": item["name_zh"],
            "name_en": item["name_en"],
            "aliases": aliases,
            "region": item["region"],
            "roster_type": item["roster_type"],
            "personal_acquaintance": personal_acquaintance,
            "familiarity": familiarity,
            "familiarity_label_zh": FAMILIARITY_LABELS[familiarity],
            "contact_policy": policy,
            "runtime_injection": runtime_injection,
            "evidence": basis,
            "roster_source_key": item["source_key"],
        }
        cards.append(card)
        write_json(cards_dir / f"{character_id}.json", card)

    if unreviewed_intersections:
        raise RuntimeError(
            "unreviewed playable-character intersections found: "
            + json.dumps(unreviewed_intersections, ensure_ascii=False)
        )

    runtime_summary = make_runtime_summary(cards)
    write_json(
        output_root / "runtime_index.json",
        {
            "schema_version": "mualani-relationship-runtime-index-v1",
            "card_count": len(cards),
            "personal_acquaintance_count": sum(
                card["personal_acquaintance"] for card in cards
            ),
            "runtime_injection": runtime_summary,
        },
    )
    write_json(
        output_root / "network.json",
        {
            "schema_version": "mualani-relationship-network-v1",
            "scope": {
                "description": (
                    "Current genshin-db playable roster, one combined Traveler, "
                    "Paimon, Alice, and Ajaw; Mualani herself is excluded."
                ),
                "roster_sources": [
                    "https://genshin-impact.fandom.com/wiki/Character/List",
                    "https://wiki.biligame.com/ys/角色",
                    "https://genshin-db-api.vercel.app/api/v5/characters",
                ],
                "relationship_evidence": [
                    "character_impressions/cards",
                    "character_impressions/excluded_characters.jsonl",
                    "character_impressions/scope_audit/mualani_full_scenes.jsonl",
                ],
            },
            "counts": {
                "nodes": len(cards),
                "personal_acquaintances": sum(
                    card["personal_acquaintance"] for card in cards
                ),
                "no_personal_acquaintance_evidence": sum(
                    not card["personal_acquaintance"] for card in cards
                ),
            },
            "nodes": cards,
        },
    )
    audit = {
        "schema_version": "mualani-relationship-audit-v1",
        "roster_count": len(cards),
        "impression_card_count": len(impression_cards),
        "excluded_candidate_count": len(excluded),
        "unreviewed_intersections": unreviewed_intersections,
        "familiarity_counts": {
            tier: sum(card["familiarity"] == tier for card in cards)
            for tier in FAMILIARITY_LABELS
        },
        "region_contact_counts": {
            region: sum(
                card["region"] == region
                and card["contact_policy"]
                in {
                    "may_freely_propose_contact",
                    "may_propose_when_contextually_relevant",
                    "may_suggest_reconnecting_if_context_fits",
                }
                for card in cards
            )
            for region in REGION_ORDER
        },
    }
    write_json(output_root / "audit_report.json", audit)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
