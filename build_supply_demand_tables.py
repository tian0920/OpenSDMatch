#!/usr/bin/env python3
"""
Build analysis-friendly supply/demand matching tables from cleaned CSV exports.

Outputs several themed CSV files instead of one huge denormalized table:
- sd_objects.csv: one row per tagged object, with supply/demand/target tags.
- sd_tags_long.csv: one row per normalized tag.
- user_sd_profiles.csv: one row per uid, aggregating user tags and profile fields.
- opportunities_enriched.csv: opportunities joined with owner profile and AI tags.
- company_sd_profiles.csv: company-level supply/demand words and metadata.
- cooperation_edges.csv: normalized matching/cooperation edges.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


DEFAULT_INPUT_DIR = "/home/ecs-user/analysis_output_cleaned/cleaned_csv"
DEFAULT_USER_PROFILE = "/home/ecs-user/merged_output/user_profiles_pruned.csv"
DEFAULT_OUTPUT_DIR = "/home/ecs-user/supply_demand_output"


def clean(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"[ \t\r\f\v]+", " ", str(value).replace("\u3000", " ").strip())


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [{clean(k): clean(v) for k, v in row.items() if k is not None} for row in reader]


def write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
            count += 1
    return count


def parse_json(value: str) -> object:
    value = clean(value)
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def split_words(value: str) -> list[str]:
    value = clean(value)
    if not value:
        return []
    parts = re.split(r"[,，;；、\n]+", value)
    return [clean(part) for part in parts if clean(part)]


def tag_name(tag: dict[str, object]) -> str:
    for key in ("normalized_tag", "suggested_tag", "secondary_tag", "raw_text", "normalized"):
        value = clean(tag.get(key, ""))
        if value:
            return value
    return ""


def parse_tag_list(value: str) -> list[dict[str, str]]:
    parsed = parse_json(value)
    if not isinstance(parsed, list):
        return []
    tags: list[dict[str, str]] = []
    for item in parsed:
        if isinstance(item, dict):
            tags.append({clean(k): clean(v) for k, v in item.items()})
    return tags


def tag_text(tags: list[dict[str, str]]) -> str:
    names: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        name = tag_name(tag)
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    return "；".join(names)


def object_key(object_type: str, object_id: str) -> str:
    return f"{clean(object_type)}:{clean(object_id)}"


def load_user_profiles(path: Path) -> dict[str, dict[str, str]]:
    profiles = {}
    for row in read_csv(path):
        uid = row.get("uid", "")
        if uid:
            profiles[uid] = row
    return profiles


def build_tags_long(input_dir: Path) -> tuple[list[dict[str, object]], dict[str, dict[str, Counter[str]]]]:
    rows = read_csv(input_dir / "t_ai_tag_index.csv")
    output: list[dict[str, object]] = []
    user_side_tags: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    for row in rows:
        normalized = clean(row.get("normalized_tag") or row.get("suggested_tag") or row.get("secondary_tag"))
        uid = row.get("uid", "")
        side = row.get("tag_side", "")
        if uid and side and normalized:
            user_side_tags[uid][side][normalized] += 1
        output.append(
            {
                "tag_row_id": row.get("id", ""),
                "uid": uid,
                "object_key": object_key(row.get("object_type", ""), row.get("object_id", "")),
                "object_type": row.get("object_type", ""),
                "object_id": row.get("object_id", ""),
                "tag_scene": row.get("tag_scene", ""),
                "tag_side": side,
                "primary_tag": row.get("primary_tag", ""),
                "secondary_tag": row.get("secondary_tag", ""),
                "suggested_tag": row.get("suggested_tag", ""),
                "normalized_tag": normalized,
                "validity": row.get("validity", ""),
                "create_time": row.get("create_time", ""),
            }
        )
    return output, user_side_tags


def build_sd_objects(input_dir: Path) -> tuple[list[dict[str, object]], dict[str, dict[str, str]]]:
    rows = read_csv(input_dir / "t_ai_tag_result.csv")
    output: list[dict[str, object]] = []
    by_object: dict[str, dict[str, str]] = {}
    for row in rows:
        supply_tags = parse_tag_list(row.get("supply_tags", ""))
        demand_tags = parse_tag_list(row.get("demand_tags", ""))
        target_tags = parse_tag_list(row.get("cooperation_target_tags", ""))
        keywords = parse_tag_list(row.get("entity_keywords", ""))
        key = object_key(row.get("object_type", ""), row.get("object_id", ""))
        item = {
            "object_key": key,
            "uid": row.get("uid", ""),
            "object_type": row.get("object_type", ""),
            "object_id": row.get("object_id", ""),
            "tag_scene": row.get("tag_scene", ""),
            "validity": row.get("validity", ""),
            "direction": row.get("direction", ""),
            "primary_action_type": row.get("primary_action_type", ""),
            "secondary_action_types": row.get("secondary_action_types", ""),
            "cooperation_method": row.get("cooperation_method", ""),
            "supply_tag_count": len(supply_tags),
            "demand_tag_count": len(demand_tags),
            "target_tag_count": len(target_tags),
            "keyword_count": len(keywords),
            "supply_tags": tag_text(supply_tags),
            "demand_tags": tag_text(demand_tags),
            "cooperation_target_tags": tag_text(target_tags),
            "entity_keywords": tag_text(keywords),
            "has_suggested_tags": row.get("has_suggested_tags", ""),
            "hit_exclusion": row.get("hit_exclusion", ""),
            "create_time": row.get("create_time", ""),
            "update_time": row.get("update_time", ""),
        }
        output.append(item)
        by_object[key] = {k: clean(v) for k, v in item.items()}
    return output, by_object


def build_user_sd_profiles(
    input_dir: Path,
    user_profiles: dict[str, dict[str, str]],
    user_side_tags: dict[str, dict[str, Counter[str]]],
    sd_objects: list[dict[str, object]],
) -> list[dict[str, object]]:
    object_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in sd_objects:
        uid = clean(row.get("uid", ""))
        if uid:
            object_counts[uid][clean(row.get("object_type", ""))] += 1

    all_uids = set(user_profiles) | set(user_side_tags) | set(object_counts)
    output = []
    for uid in sorted(all_uids):
        profile = user_profiles.get(uid, {})
        supply_counter = user_side_tags.get(uid, {}).get("supply", Counter())
        demand_counter = user_side_tags.get(uid, {}).get("demand", Counter())
        output.append(
            {
                "uid": uid,
                "name": profile.get("name", ""),
                "display_name": profile.get("display_name", ""),
                "mobile": profile.get("mobile", ""),
                "province": profile.get("province", ""),
                "city": profile.get("city", ""),
                "company": profile.get("company", ""),
                "position": profile.get("position", ""),
                "business_desc": profile.get("business_desc", ""),
                "source_tables": profile.get("source_tables", ""),
                "supply_tag_count": sum(supply_counter.values()),
                "demand_tag_count": sum(demand_counter.values()),
                "top_supply_tags": "；".join(tag for tag, _ in supply_counter.most_common(20)),
                "top_demand_tags": "；".join(tag for tag, _ in demand_counter.most_common(20)),
                "supply_tag_stats_json": json_dumps(supply_counter.most_common(50)),
                "demand_tag_stats_json": json_dumps(demand_counter.most_common(50)),
                "tagged_unit_entity_count": object_counts.get(uid, Counter()).get("unit_entity", 0),
                "tagged_opportunity_count": object_counts.get(uid, Counter()).get("opportunity", 0),
                "opportunities_count": profile.get("opportunities_count", ""),
                "jobs_count": profile.get("jobs_count", ""),
                "friend_edge_count": profile.get("friend_edge_count", ""),
            }
        )
    return output


def build_opportunities(input_dir: Path, user_profiles: dict[str, dict[str, str]], object_index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    rows = read_csv(input_dir / "es_opportunities.csv")
    output = []
    for row in rows:
        uid = row.get("uid", "")
        profile = user_profiles.get(uid, {})
        obj = object_index.get(object_key("opportunity", row.get("id", "")), {})
        output.append(
            {
                "opportunity_id": row.get("id", ""),
                "uid": uid,
                "owner_name": profile.get("display_name") or profile.get("name", ""),
                "owner_company": profile.get("company", ""),
                "owner_position": profile.get("position", ""),
                "owner_province": profile.get("province", ""),
                "owner_city": profile.get("city", ""),
                "title": row.get("title", ""),
                "content": row.get("content", ""),
                "review_state": row.get("reviewState", ""),
                "collect_count": row.get("collectCount", ""),
                "create_time": row.get("createTime", ""),
                "update_time": row.get("updateTime", ""),
                "validity": obj.get("validity", ""),
                "direction": obj.get("direction", ""),
                "primary_action_type": obj.get("primary_action_type", ""),
                "cooperation_method": obj.get("cooperation_method", ""),
                "supply_tags": obj.get("supply_tags", ""),
                "demand_tags": obj.get("demand_tags", ""),
                "cooperation_target_tags": obj.get("cooperation_target_tags", ""),
                "entity_keywords": obj.get("entity_keywords", ""),
            }
        )
    return output


def build_company_profiles(input_dir: Path) -> list[dict[str, object]]:
    csd = read_csv(input_dir / "t_company_supply_demand.csv")
    enterprise_by_name = {row.get("company_name", ""): row for row in read_csv(input_dir / "t_enterprise.csv")}
    unit_by_name = {row.get("canonical_name", ""): row for row in read_csv(input_dir / "t_unit_entity.csv")}
    output = []
    for row in csd:
        name = row.get("company_name", "")
        enterprise = enterprise_by_name.get(name, {})
        unit = unit_by_name.get(name, {})
        output.append(
            {
                "company_name": name,
                "industry": row.get("industry") or enterprise.get("industry") or clean(parse_company_info_industry(unit.get("company_info", ""))),
                "main_business": row.get("main_business", ""),
                "products": row.get("products", ""),
                "supply_words": row.get("supply_words", ""),
                "demand_words": row.get("demand_words", ""),
                "supply_word_count": len(split_words(row.get("supply_words", ""))),
                "demand_word_count": len(split_words(row.get("demand_words", ""))),
                "company_type": enterprise.get("company_type") or unit.get("unit_nature", ""),
                "address": enterprise.get("address") or unit.get("office_address", ""),
                "website": enterprise.get("website") or unit.get("official_website", ""),
                "summary_text": unit.get("summary_text", ""),
                "capability_points": unit.get("capability_points", ""),
                "create_time": row.get("create_time", ""),
                "update_time": row.get("update_time", ""),
            }
        )
    return output


def parse_company_info_industry(value: str) -> str:
    parsed = parse_json(value)
    if isinstance(parsed, dict):
        return clean(parsed.get("行业", ""))
    return ""


def build_edges(input_dir: Path, user_profiles: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    edges: list[dict[str, object]] = []
    for row in read_csv(input_dir / "t_supply_chain_relation.csv"):
        edges.append(
            {
                "edge_type": "company_supply_chain_match",
                "source_id": row.get("party_a", ""),
                "source_type": "company",
                "target_id": row.get("party_b", ""),
                "target_type": "company",
                "score": row.get("score", ""),
                "status": "",
                "match_type": "supply_chain",
                "title": "",
                "reason": row.get("reason", ""),
                "action_plan": row.get("action_plan", ""),
                "event_time": row.get("create_time", ""),
                "raw_json": "",
            }
        )

    for row in read_csv(input_dir / "es_business_match_reports.csv"):
        report_data = parse_json(row.get("report_data", ""))
        overview = report_data.get("report_overview", {}) if isinstance(report_data, dict) else {}
        edges.append(
            {
                "edge_type": "user_match_report",
                "source_id": row.get("uid", ""),
                "source_type": "user",
                "target_id": row.get("passive_uid", ""),
                "target_type": "user",
                "score": "",
                "status": row.get("status", ""),
                "match_type": row.get("report_type", ""),
                "title": row.get("report_name", ""),
                "reason": f"total_matches={overview.get('total_matches', '')}; involved_friends={overview.get('involved_friends', '')}",
                "action_plan": f"suggested_actions={overview.get('suggested_actions', '')}",
                "event_time": row.get("updated_at") or row.get("finished_at") or row.get("created_at", ""),
                "raw_json": row.get("report_data", ""),
            }
        )

    for row in read_csv(input_dir / "t_biz_cooperation.csv"):
        edges.append(
            {
                "edge_type": "biz_cooperation_invite",
                "source_id": row.get("uid", ""),
                "source_type": "user",
                "target_id": row.get("invitee_uid", ""),
                "target_type": "user",
                "score": "",
                "status": row.get("status", ""),
                "match_type": f"invitation_type:{row.get('invitation_type', '')}",
                "title": "",
                "reason": "",
                "action_plan": "",
                "event_time": row.get("update_time") or row.get("create_time", ""),
                "raw_json": json_dumps(row),
            }
        )

    # Add names for user-user edges where possible.
    for edge in edges:
        if edge["source_type"] == "user":
            source_profile = user_profiles.get(clean(edge["source_id"]), {})
            edge["source_name"] = source_profile.get("display_name") or source_profile.get("name", "")
            edge["source_company"] = source_profile.get("company", "")
        else:
            edge["source_name"] = edge["source_id"]
            edge["source_company"] = edge["source_id"]
        if edge["target_type"] == "user":
            target_profile = user_profiles.get(clean(edge["target_id"]), {})
            edge["target_name"] = target_profile.get("display_name") or target_profile.get("name", "")
            edge["target_company"] = target_profile.get("company", "")
        else:
            edge["target_name"] = edge["target_id"]
            edge["target_company"] = edge["target_id"]
    return edges


def write_readme(output_dir: Path, counts: dict[str, int]) -> None:
    lines = [
        "# 供需合作匹配主题表",
        "",
        "这些表由清洗后的 CSV 二次合并生成，用于集中分析供给、需求、合作对象和匹配关系。",
        "",
        "## 输出文件",
    ]
    descriptions = {
        "sd_objects.csv": "一行一个被 AI 解析过的对象，含供给标签、需求标签、合作对象标签、关键词。",
        "sd_tags_long.csv": "一行一个标签，适合做标签频次、供需侧对比、透视表。",
        "user_sd_profiles.csv": "一行一个用户，聚合用户供给/需求标签，并补充基础画像字段。",
        "opportunities_enriched.csv": "一行一个商机，补充发布者画像和 AI 解析出的供需标签。",
        "company_sd_profiles.csv": "一行一个公司/机构，含主营业务、行业、供给词、需求词。",
        "cooperation_edges.csv": "统一的合作/匹配边表，整合公司供应链匹配、用户匹配报告、合作邀请。",
    }
    for filename, desc in descriptions.items():
        lines.append(f"- `{filename}`：{counts.get(filename, 0):,} 行。{desc}")
    lines.extend(
        [
            "",
            "## 建议用法",
            "- 看标签供需结构：从 `sd_tags_long.csv` 按 `tag_side/primary_tag/secondary_tag/normalized_tag` 透视。",
            "- 看单个用户供需画像：查 `user_sd_profiles.csv`。",
            "- 看商机质量和方向：查 `opportunities_enriched.csv` 的 `validity/direction/cooperation_method`。",
            "- 看公司间潜在合作：按 `cooperation_edges.csv` 中 `edge_type=company_supply_chain_match` 和 `score` 排序。",
            "- 看系统已有匹配结果：按 `edge_type=user_match_report` 查看 `raw_json` 和 `reason/action_plan`。",
        ]
    )
    (output_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build supply/demand matching analysis tables.")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--user-profile", default=DEFAULT_USER_PROFILE)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    user_profile_path = Path(args.user_profile).resolve()

    user_profiles = load_user_profiles(user_profile_path)
    tags_long, user_side_tags = build_tags_long(input_dir)
    sd_objects, object_index = build_sd_objects(input_dir)
    user_sd_profiles = build_user_sd_profiles(input_dir, user_profiles, user_side_tags, sd_objects)
    opportunities = build_opportunities(input_dir, user_profiles, object_index)
    company_profiles = build_company_profiles(input_dir)
    edges = build_edges(input_dir, user_profiles)

    counts = {}
    counts["sd_tags_long.csv"] = write_csv(
        output_dir / "sd_tags_long.csv",
        tags_long,
        [
            "tag_row_id",
            "uid",
            "object_key",
            "object_type",
            "object_id",
            "tag_scene",
            "tag_side",
            "primary_tag",
            "secondary_tag",
            "suggested_tag",
            "normalized_tag",
            "validity",
            "create_time",
        ],
    )
    counts["sd_objects.csv"] = write_csv(
        output_dir / "sd_objects.csv",
        sd_objects,
        [
            "object_key",
            "uid",
            "object_type",
            "object_id",
            "tag_scene",
            "validity",
            "direction",
            "primary_action_type",
            "secondary_action_types",
            "cooperation_method",
            "supply_tag_count",
            "demand_tag_count",
            "target_tag_count",
            "keyword_count",
            "supply_tags",
            "demand_tags",
            "cooperation_target_tags",
            "entity_keywords",
            "has_suggested_tags",
            "hit_exclusion",
            "create_time",
            "update_time",
        ],
    )
    counts["user_sd_profiles.csv"] = write_csv(
        output_dir / "user_sd_profiles.csv",
        user_sd_profiles,
        [
            "uid",
            "name",
            "display_name",
            "mobile",
            "province",
            "city",
            "company",
            "position",
            "business_desc",
            "source_tables",
            "supply_tag_count",
            "demand_tag_count",
            "top_supply_tags",
            "top_demand_tags",
            "supply_tag_stats_json",
            "demand_tag_stats_json",
            "tagged_unit_entity_count",
            "tagged_opportunity_count",
            "opportunities_count",
            "jobs_count",
            "friend_edge_count",
        ],
    )
    counts["opportunities_enriched.csv"] = write_csv(
        output_dir / "opportunities_enriched.csv",
        opportunities,
        [
            "opportunity_id",
            "uid",
            "owner_name",
            "owner_company",
            "owner_position",
            "owner_province",
            "owner_city",
            "title",
            "content",
            "review_state",
            "collect_count",
            "create_time",
            "update_time",
            "validity",
            "direction",
            "primary_action_type",
            "cooperation_method",
            "supply_tags",
            "demand_tags",
            "cooperation_target_tags",
            "entity_keywords",
        ],
    )
    counts["company_sd_profiles.csv"] = write_csv(
        output_dir / "company_sd_profiles.csv",
        company_profiles,
        [
            "company_name",
            "industry",
            "main_business",
            "products",
            "supply_words",
            "demand_words",
            "supply_word_count",
            "demand_word_count",
            "company_type",
            "address",
            "website",
            "summary_text",
            "capability_points",
            "create_time",
            "update_time",
        ],
    )
    counts["cooperation_edges.csv"] = write_csv(
        output_dir / "cooperation_edges.csv",
        edges,
        [
            "edge_type",
            "source_id",
            "source_type",
            "source_name",
            "source_company",
            "target_id",
            "target_type",
            "target_name",
            "target_company",
            "score",
            "status",
            "match_type",
            "title",
            "reason",
            "action_plan",
            "event_time",
            "raw_json",
        ],
    )
    write_readme(output_dir, counts)

    print(f"Done. Output dir: {output_dir}")
    for filename, count in counts.items():
        print(f"{filename}: {count:,} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
