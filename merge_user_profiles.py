#!/usr/bin/env python3
"""
Merge cleaned app-export CSV files into one user-centered profile table.

Input defaults to analysis_output_cleaned/cleaned_csv. The script keeps one row
per uid. One-to-one fields are flattened into columns; one-to-many records are
stored as compact JSON columns with companion count fields.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


DEFAULT_INPUT_DIR = "analysis_output_cleaned/cleaned_csv"
DEFAULT_OUTPUT_DIR = "merged_output"

UID_COLUMNS = ("uid", "_uid", "user_id", "member_uid", "invitee_uid", "inviter_uid", "passive_uid", "targe_uid")
TIME_COLUMNS = ("update_time", "updated_at", "create_time", "created_at", "_update_time", "_createTime", "_dt", "dt")

BASE_COLUMNS = [
    "uid",
    "name",
    "display_name",
    "real_name",
    "gender",
    "mobile",
    "email",
    "country",
    "province",
    "city",
    "address",
    "company",
    "position",
    "department",
    "business_desc",
    "user_desc",
    "resume",
    "portrait",
    "source_tables",
]


def clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\ufeff", "").replace("\u3000", " ").strip()
    return re.sub(r"[ \t\r\f\v]+", " ", text)


def json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {clean(k): clean(v) for k, v in row.items() if k is not None}


def load_rows(input_dir: Path, table_name: str) -> list[dict[str, str]]:
    path = input_dir / f"{table_name}.csv"
    if not path.exists():
        return []
    return list(read_csv(path))


def first_nonempty(*values: str) -> str:
    for value in values:
        if clean(value):
            return clean(value)
    return ""


def row_time(row: dict[str, str]) -> str:
    return first_nonempty(*(row.get(col, "") for col in TIME_COLUMNS))


def choose_latest(rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows:
        return {}
    return max(rows, key=lambda row: row_time(row))


def compact_record(row: dict[str, str], fields: list[str]) -> dict[str, str]:
    return {field: row.get(field, "") for field in fields if row.get(field, "")}


def limited_records(rows: list[dict[str, str]], fields: list[str], limit: int) -> list[dict[str, str]]:
    sorted_rows = sorted(rows, key=row_time, reverse=True)
    return [compact_record(row, fields) for row in sorted_rows[:limit]]


def add_source(profile: dict[str, object], table_name: str) -> None:
    sources = profile.setdefault("_source_tables_set", set())
    if isinstance(sources, set):
        sources.add(table_name)


def ensure_profile(profiles: dict[str, dict[str, object]], uid: str) -> dict[str, object]:
    uid = clean(uid)
    profile = profiles.setdefault(uid, {"uid": uid, "_source_tables_set": set()})
    return profile


def set_if_empty(profile: dict[str, object], field: str, value: str) -> None:
    value = clean(value)
    if value and not profile.get(field):
        profile[field] = value


def collect_all_uids(input_dir: Path) -> set[str]:
    uids: set[str] = set()
    for path in input_dir.glob("*.csv"):
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            candidates = [col for col in UID_COLUMNS if col in header]
            if not candidates:
                continue
            for row in reader:
                for col in candidates:
                    value = clean(row.get(col, ""))
                    if value and value.lower() != "undefined":
                        uids.add(value)
    return uids


def merge_base_user(input_dir: Path, profiles: dict[str, dict[str, object]]) -> None:
    for row in load_rows(input_dir, "t_user"):
        uid = first_nonempty(row.get("_uid", ""), row.get("uid", ""))
        if not uid:
            continue
        profile = ensure_profile(profiles, uid)
        add_source(profile, "t_user")
        set_if_empty(profile, "name", row.get("_name", ""))
        set_if_empty(profile, "display_name", row.get("_display_name", ""))
        set_if_empty(profile, "gender", row.get("_gender", ""))
        set_if_empty(profile, "mobile", row.get("_mobile", ""))
        set_if_empty(profile, "email", row.get("_email", ""))
        set_if_empty(profile, "address", row.get("_address", ""))
        set_if_empty(profile, "company", row.get("_company", ""))
        set_if_empty(profile, "portrait", row.get("_portrait", ""))
        set_if_empty(profile, "user_create_time", row.get("_createTime", ""))
        set_if_empty(profile, "user_type", row.get("_type", ""))
        set_if_empty(profile, "user_deleted", row.get("_deleted", ""))


def merge_external(input_dir: Path, profiles: dict[str, dict[str, object]]) -> None:
    by_uid: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in load_rows(input_dir, "t_user_external"):
        if row.get("uid"):
            by_uid[row["uid"]].append(row)
    for uid, rows in by_uid.items():
        row = choose_latest(rows)
        profile = ensure_profile(profiles, uid)
        add_source(profile, "t_user_external")
        set_if_empty(profile, "name", row.get("name", ""))
        set_if_empty(profile, "real_name", row.get("real_name", ""))
        set_if_empty(profile, "mobile", row.get("user_mobile", ""))
        set_if_empty(profile, "email", row.get("email", ""))
        set_if_empty(profile, "country", row.get("country", ""))
        set_if_empty(profile, "province", row.get("province", ""))
        set_if_empty(profile, "city", row.get("city", ""))
        set_if_empty(profile, "business_desc", row.get("business_desc", ""))
        set_if_empty(profile, "user_desc", row.get("user_desc", ""))
        set_if_empty(profile, "resume", row.get("resume", ""))
        set_if_empty(profile, "portrait", row.get("portrait", ""))
        set_if_empty(profile, "background_pic", row.get("background_pic", ""))
        set_if_empty(profile, "personal_link", row.get("personal_link", ""))
        set_if_empty(profile, "invite_code", row.get("invite_code", ""))
        set_if_empty(profile, "external_update_time", row.get("update_time", ""))
        profile["external_profile_json"] = json_dumps(compact_record(row, list(row.keys())))


def merge_jobs(input_dir: Path, profiles: dict[str, dict[str, object]], limit: int) -> None:
    by_uid: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in load_rows(input_dir, "t_user_jobs"):
        if row.get("uid"):
            by_uid[row["uid"]].append(row)
    fields = [
        "id",
        "employer",
        "position",
        "is_main",
        "business",
        "division_business",
        "department",
        "job_status",
        "join_date",
        "leave_date",
        "create_time",
        "update_time",
        "company_info",
    ]
    for uid, rows in by_uid.items():
        profile = ensure_profile(profiles, uid)
        add_source(profile, "t_user_jobs")
        main_rows = [row for row in rows if row.get("is_main") in {"1", "true", "True"}]
        main = choose_latest(main_rows) if main_rows else choose_latest(rows)
        set_if_empty(profile, "company", main.get("employer", ""))
        set_if_empty(profile, "position", main.get("position", ""))
        set_if_empty(profile, "department", main.get("department", ""))
        profile["jobs_count"] = len(rows)
        profile["jobs_json"] = json_dumps(limited_records(rows, fields, limit))


def merge_key_value_table(
    input_dir: Path,
    profiles: dict[str, dict[str, object]],
    table_name: str,
    key_col: str,
    value_col: str,
    prefix: str,
    limit: int,
) -> None:
    rows_by_uid: dict[str, list[dict[str, str]]] = defaultdict(list)
    kv_by_uid: dict[str, dict[str, str]] = defaultdict(dict)
    for row in load_rows(input_dir, table_name):
        uid = row.get("uid") or row.get("_uid") or row.get("user_id")
        key = row.get(key_col, "")
        value = row.get(value_col, "")
        if not uid:
            continue
        rows_by_uid[uid].append(row)
        if key and value and key not in kv_by_uid[uid]:
            kv_by_uid[uid][key] = value

    for uid, rows in rows_by_uid.items():
        profile = ensure_profile(profiles, uid)
        add_source(profile, table_name)
        profile[f"{prefix}_count"] = len(rows)
        profile[f"{prefix}_json"] = json_dumps(kv_by_uid.get(uid, {}))
        for key, value in sorted(kv_by_uid.get(uid, {}).items())[:limit]:
            safe_key = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", key).strip("_")
            if safe_key:
                profile[f"{prefix}_{safe_key}"] = value


def merge_simple_latest(
    input_dir: Path,
    profiles: dict[str, dict[str, object]],
    table_name: str,
    uid_col: str,
    field_map: dict[str, str],
) -> None:
    rows_by_uid: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in load_rows(input_dir, table_name):
        uid = row.get(uid_col, "")
        if uid:
            rows_by_uid[uid].append(row)
    for uid, rows in rows_by_uid.items():
        row = choose_latest(rows)
        profile = ensure_profile(profiles, uid)
        add_source(profile, table_name)
        for source, target in field_map.items():
            set_if_empty(profile, target, row.get(source, ""))
        profile[f"{table_name}_count"] = len(rows)


def merge_json_collection(
    input_dir: Path,
    profiles: dict[str, dict[str, object]],
    table_name: str,
    uid_col: str,
    output_name: str,
    fields: list[str],
    limit: int,
) -> None:
    rows_by_uid: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in load_rows(input_dir, table_name):
        uid = row.get(uid_col, "")
        if uid:
            rows_by_uid[uid].append(row)
    for uid, rows in rows_by_uid.items():
        profile = ensure_profile(profiles, uid)
        add_source(profile, table_name)
        profile[f"{output_name}_count"] = len(rows)
        profile[f"{output_name}_json"] = json_dumps(limited_records(rows, fields, limit))


def merge_ai_tags(input_dir: Path, profiles: dict[str, dict[str, object]], limit: int) -> None:
    tags_by_uid: dict[str, Counter[str]] = defaultdict(Counter)
    sides_by_uid: dict[str, Counter[str]] = defaultdict(Counter)
    for row in load_rows(input_dir, "t_ai_tag_index"):
        uid = row.get("uid", "")
        tag = first_nonempty(row.get("normalized_tag", ""), row.get("suggested_tag", ""), row.get("secondary_tag", ""))
        if not uid or not tag:
            continue
        tags_by_uid[uid][tag] += 1
        side = row.get("tag_side", "")
        if side:
            sides_by_uid[uid][side] += 1
    for uid, counter in tags_by_uid.items():
        profile = ensure_profile(profiles, uid)
        add_source(profile, "t_ai_tag_index")
        profile["ai_tag_count"] = sum(counter.values())
        profile["ai_top_tags"] = "；".join(tag for tag, _count in counter.most_common(limit))
        profile["ai_tag_stats_json"] = json_dumps(counter.most_common(limit))
        profile["ai_tag_side_stats_json"] = json_dumps(dict(sides_by_uid.get(uid, {})))


def merge_friend_stats(input_dir: Path, profiles: dict[str, dict[str, object]]) -> None:
    friend_counts: Counter[str] = Counter()
    for row in load_rows(input_dir, "t_friend"):
        uid = row.get("uid", "")
        friend_uid = row.get("friend_uid", "")
        if uid:
            friend_counts[uid] += 1
        if friend_uid:
            friend_counts[friend_uid] += 1
    for uid, count in friend_counts.items():
        profile = ensure_profile(profiles, uid)
        add_source(profile, "t_friend")
        profile["friend_edge_count"] = count


def merge_all(input_dir: Path, limit: int) -> dict[str, dict[str, object]]:
    profiles: dict[str, dict[str, object]] = {}
    merge_base_user(input_dir, profiles)
    merge_external(input_dir, profiles)
    merge_jobs(input_dir, profiles, limit)
    merge_key_value_table(input_dir, profiles, "t_user_accessory", "info_key", "info_value", "accessory", limit)
    merge_key_value_table(input_dir, profiles, "t_user_info_setting", "setting_key", "setting_value", "setting", limit)
    merge_key_value_table(input_dir, profiles, "t_user_stat", "stat_key", "stat_value", "stat", limit)
    merge_simple_latest(
        input_dir,
        profiles,
        "t_user_city",
        "user_id",
        {"country": "country", "province": "province", "city": "city"},
    )
    merge_simple_latest(
        input_dir,
        profiles,
        "t_user_city_wx",
        "user_id",
        {"country": "country", "province": "province", "city": "city"},
    )
    merge_json_collection(
        input_dir,
        profiles,
        "t_user_education",
        "uid",
        "education",
        ["school", "qualification", "enrollment_time", "graduation_time", "remark"],
        limit,
    )
    merge_json_collection(
        input_dir,
        profiles,
        "es_contacts",
        "uid",
        "es_contacts",
        ["id", "name", "company", "position", "job", "city", "business", "tagList", "updateTime"],
        limit,
    )
    merge_json_collection(
        input_dir,
        profiles,
        "es_opportunities",
        "uid",
        "opportunities",
        ["id", "title", "content", "createTime", "updateTime", "reviewState"],
        limit,
    )
    merge_json_collection(
        input_dir,
        profiles,
        "es_business_match_reports",
        "uid",
        "match_reports",
        ["id", "passive_uid", "report_type", "status", "report_month", "report_name", "updated_at"],
        limit,
    )
    merge_ai_tags(input_dir, profiles, limit)
    merge_friend_stats(input_dir, profiles)
    return profiles


def output_columns(profiles: dict[str, dict[str, object]]) -> list[str]:
    dynamic: set[str] = set()
    for profile in profiles.values():
        dynamic.update(str(key) for key in profile.keys() if not str(key).startswith("_"))
    rest = sorted(dynamic - set(BASE_COLUMNS))
    return [col for col in BASE_COLUMNS if col in dynamic or col == "source_tables"] + rest


def write_profiles(output_path: Path, profiles: dict[str, dict[str, object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = output_columns(profiles)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for uid in sorted(profiles):
            profile = dict(profiles[uid])
            sources = profile.pop("_source_tables_set", set())
            if isinstance(sources, set):
                profile["source_tables"] = "；".join(sorted(sources))
            writer.writerow({col: profile.get(col, "") for col in columns})


def write_summary(output_dir: Path, profiles: dict[str, dict[str, object]]) -> None:
    source_counter: Counter[str] = Counter()
    for profile in profiles.values():
        sources = profile.get("_source_tables_set", set())
        if isinstance(sources, set):
            source_counter.update(sources)
    lines = [
        "# 用户合并结果说明",
        "",
        f"- 合并用户数：{len(profiles):,}",
        f"- 涉及来源表数量：{len(source_counter)}",
        "",
        "## 来源表覆盖",
    ]
    for table, count in source_counter.most_common():
        lines.append(f"- {table}：{count:,} 个用户")
    lines.extend(
        [
            "",
            "## 合并策略",
            "- `t_user`、`t_user_external`、城市表取同一用户最新/非空信息作为主列。",
            "- `t_user_jobs`、教育、ES 联系人、商机、匹配报告等一对多信息写入 JSON 列，并保留 count。",
            "- `t_user_accessory`、`t_user_info_setting`、`t_user_stat` 按 key-value 透视成若干列，同时保留完整 JSON。",
            "- AI 标签从 `t_ai_tag_index` 聚合为热门标签、标签计数和供需侧统计。",
        ]
    )
    (output_dir / "merge_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge cleaned CSV exports into user profiles.")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help="Directory containing cleaned CSV files.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for merged outputs.")
    parser.add_argument("--output-file", default="user_profiles_merged.csv", help="Merged CSV file name.")
    parser.add_argument("--limit", type=int, default=20, help="Max records/items kept in JSON collection fields.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")

    profiles = merge_all(input_dir, args.limit)
    output_path = output_dir / args.output_file
    write_profiles(output_path, profiles)
    write_summary(output_dir, profiles)
    print(f"Done. Merged users: {len(profiles):,}")
    print(f"Output CSV: {output_path}")
    print(f"Summary: {output_dir / 'merge_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
