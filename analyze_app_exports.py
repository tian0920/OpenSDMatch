#!/usr/bin/env python3
"""
Analyze and lightly clean app-export zip files that contain xlsx tables.

The script uses only Python's standard library. It does not modify source zip
files. By default it writes inventory and recommendation reports. Use
--export-cleaned to also export cleaned CSV files for tables that are not marked
as irrelevant or duplicate exports.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable
from zipfile import ZipFile


XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
OFFICE_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

DATE_SUFFIX_RE = re.compile(r"_(20\d{6}_\d{6})(?:\(\d+\))?$")
SENSITIVE_RE = re.compile(
    r"(password|salt|token|captcha|session|mobile|phone|tel|email|wechat|qr|身份证|id_card)",
    re.I,
)
TIME_RE = re.compile(r"(time|date|created|updated|timestamp|expire|start|end)", re.I)
TEXT_RE = re.compile(r"(content|desc|summary|remark|scope|business|info|text|tags|attach)", re.I)

# Conservative first-pass filtering. Edit these lists if your project needs a
# different scope.
IRRELEVANT_TABLE_PATTERNS = [
    r"^flyway_schema_history$",
    r"^sys_(captcha|config|dept|dept_external|dept_navigator|log|menu|oss|role|role_menu|user|user_role|user_token)$",
    r"^(pc|shiro)_session$",
    r"^phone_code_record$",
    r"^dynamic_synonym_rule_",
    r"^t_app_version$",
    r"^t_comfy_",
    r"^t_device$",
    r"^t_file$",
]

CORE_TABLE_HINTS = [
    "t_ai_tag",
    "t_unit_entity",
    "t_company",
    "t_enterprise",
    "t_user_external",
    "t_user_jobs",
    "t_user_accessory",
    "t_business",
    "t_demand",
    "t_friend",
    "es_contacts",
    "es_opportunities",
    "es_business_match_reports",
]

TABLE_DIMENSION_RULES = [
    ("AI标签", re.compile(r"ai_tag|tag_", re.I)),
    ("企业/机构", re.compile(r"company|enterprise|unit_entity|corporation|dept|employer|corp", re.I)),
    ("用户/联系人", re.compile(r"user|contact|friend|book|accessory|jobs", re.I)),
    ("商机/供需/业务", re.compile(r"business|demand|opportunit|supply|match|report", re.I)),
    ("系统/权限/配置", re.compile(r"^sys_|session|captcha|token|flyway|config|log", re.I)),
    ("内容/互动", re.compile(r"article|comment|favorites|feedback|chat|group|message", re.I)),
]


@dataclass
class TableStats:
    zip_name: str
    member_name: str
    table_name: str
    normalized_table: str
    rows: int = 0
    cols: int = 0
    header: list[str] = field(default_factory=list)
    sample_rows: list[list[str]] = field(default_factory=list)
    empty_rows: int = 0
    exact_duplicate_rows: int = 0
    key_duplicate_rows: int = 0
    key_columns: list[str] = field(default_factory=list)
    blank_field_ratio: float = 0.0
    mostly_blank_columns: list[str] = field(default_factory=list)
    sensitive_columns: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    data_hash: str = ""
    action: str = "keep"
    reason: str = ""


def normalize_table_name(member_name: str) -> str:
    stem = Path(member_name).stem
    stem = re.sub(r"^\d+_", "", stem)
    stem = DATE_SUFFIX_RE.sub("", stem)
    return stem


def resolve_xlsx_path(base: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return str(PurePosixPath(base).parent / target)


def column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref or "")
    if not match:
        return 0
    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - 64
    return value - 1


def load_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values = []
    for item in root.findall(f"{XLSX_NS}si"):
        values.append("".join(text.text or "" for text in item.iter(f"{XLSX_NS}t")))
    return values


def first_sheet_path(zf: ZipFile) -> str:
    workbook_path = "xl/workbook.xml"
    workbook = ET.fromstring(zf.read(workbook_path))
    sheet = workbook.find(f"{XLSX_NS}sheets/{XLSX_NS}sheet")
    if sheet is None:
        raise ValueError("xlsx has no worksheet")
    rel_id = sheet.attrib.get(f"{OFFICE_REL_NS}id")
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels.findall(f"{PKG_REL_NS}Relationship"):
        if rel.attrib.get("Id") == rel_id:
            return resolve_xlsx_path(workbook_path, rel.attrib["Target"])
    raise ValueError("worksheet relationship not found")


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return clean_value("".join(text.text or "" for text in cell.iter(f"{XLSX_NS}t")))
    value = cell.find(f"{XLSX_NS}v")
    if value is None or value.text is None:
        return ""
    raw = value.text
    if cell_type == "s":
        try:
            return clean_value(shared_strings[int(raw)])
        except (ValueError, IndexError):
            return clean_value(raw)
    return clean_value(raw)


def clean_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u3000", " ").strip()
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return text


def iter_xlsx_rows(xlsx_bytes: bytes) -> Iterable[list[str]]:
    import io

    with ZipFile(io.BytesIO(xlsx_bytes)) as zf:
        shared_strings = load_shared_strings(zf)
        sheet_path = first_sheet_path(zf)
        with zf.open(sheet_path) as sheet_file:
            for _event, elem in ET.iterparse(sheet_file, events=("end",)):
                if elem.tag != f"{XLSX_NS}row":
                    continue
                row: list[str] = []
                for cell in elem.findall(f"{XLSX_NS}c"):
                    idx = column_index(cell.attrib.get("r", ""))
                    while len(row) <= idx:
                        row.append("")
                    row[idx] = cell_value(cell, shared_strings)
                while row and row[-1] == "":
                    row.pop()
                yield row
                elem.clear()


def choose_key_columns(header: list[str], normalized_table: str) -> list[int]:
    lower = [h.lower() for h in header]
    candidates: list[list[str]] = []
    if {"uid", "object_type", "object_id", "tag_side", "primary_tag", "secondary_tag"} <= set(lower):
        candidates.append(["uid", "object_type", "object_id", "tag_side", "primary_tag", "secondary_tag"])
    if {"uid", "object_type", "object_id", "tag_scene"} <= set(lower):
        candidates.append(["uid", "object_type", "object_id", "tag_scene"])
    if {"company_name", "legal_person_name"} <= set(lower):
        candidates.append(["company_name", "legal_person_name"])
    if {"name", "company_type"} <= set(lower) and "company" in normalized_table:
        candidates.append(["name", "company_type"])
    if "uscc" in lower:
        candidates.append(["uscc"])
    if "_id" in lower:
        candidates.append(["_id"])
    if "id" in lower:
        candidates.append(["id"])
    for cols in candidates:
        positions = [lower.index(col) for col in cols if col in lower]
        if positions:
            return positions
    return []


def row_digest(values: list[str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_dimensions(table: str, header: list[str]) -> list[str]:
    text = " ".join([table, *header])
    dimensions = [name for name, pattern in TABLE_DIMENSION_RULES if pattern.search(text)]
    return dimensions or ["其他"]


def is_irrelevant_table(table: str) -> bool:
    return any(re.search(pattern, table, re.I) for pattern in IRRELEVANT_TABLE_PATTERNS)


def is_core_table(table: str) -> bool:
    return any(hint in table for hint in CORE_TABLE_HINTS)


def analyze_member(zip_name: str, member_name: str, xlsx_bytes: bytes, max_rows: int | None) -> TableStats:
    table = normalize_table_name(member_name)
    stats = TableStats(
        zip_name=zip_name,
        member_name=member_name,
        table_name=Path(member_name).stem,
        normalized_table=table,
    )
    seen_rows: set[str] = set()
    seen_keys: set[tuple[str, ...]] = set()
    blank_cells = 0
    total_cells = 0
    blank_by_col: Counter[int] = Counter()
    data_hash = hashlib.sha256()
    key_positions: list[int] = []

    for physical_row_no, row in enumerate(iter_xlsx_rows(xlsx_bytes), start=1):
        if max_rows is not None and physical_row_no > max_rows + 1:
            break
        if not any(row):
            stats.empty_rows += 1
            continue
        if not stats.header:
            stats.header = [clean_value(v) for v in row]
            stats.cols = len(stats.header)
            key_positions = choose_key_columns(stats.header, table)
            stats.key_columns = [stats.header[i] for i in key_positions]
            stats.sensitive_columns = [h for h in stats.header if SENSITIVE_RE.search(h)]
            continue

        values = [clean_value(v) for v in row]
        if len(values) < stats.cols:
            values.extend([""] * (stats.cols - len(values)))
        values = values[: stats.cols]
        stats.rows += 1
        if len(stats.sample_rows) < 3:
            stats.sample_rows.append(values)
        data_hash.update(row_digest(values).encode("ascii"))

        digest = row_digest(values)
        if digest in seen_rows:
            stats.exact_duplicate_rows += 1
        else:
            seen_rows.add(digest)

        if key_positions:
            key = tuple(values[i] if i < len(values) else "" for i in key_positions)
            if any(key):
                if key in seen_keys:
                    stats.key_duplicate_rows += 1
                else:
                    seen_keys.add(key)

        for idx in range(stats.cols):
            total_cells += 1
            if idx >= len(values) or values[idx] == "":
                blank_cells += 1
                blank_by_col[idx] += 1

    stats.data_hash = data_hash.hexdigest()
    stats.blank_field_ratio = blank_cells / total_cells if total_cells else 0.0
    if stats.rows:
        stats.mostly_blank_columns = [
            stats.header[idx]
            for idx, count in blank_by_col.items()
            if idx < len(stats.header) and count / stats.rows >= 0.95
        ]
    stats.dimensions = classify_dimensions(table, stats.header)
    return stats


def collect_zip_members(input_dir: Path, zip_names: list[str]) -> list[tuple[Path, str]]:
    zip_paths = [input_dir / name for name in zip_names] if zip_names else sorted(input_dir.glob("*.zip"))
    members: list[tuple[Path, str]] = []
    for zip_path in zip_paths:
        if not zip_path.exists():
            raise FileNotFoundError(zip_path)
        with ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if not info.filename.endswith(".xlsx") or info.is_dir():
                    continue
                members.append((zip_path, info.filename))
    return members


def mark_actions(stats: list[TableStats]) -> None:
    by_table: dict[str, list[TableStats]] = defaultdict(list)
    by_hash: dict[str, list[TableStats]] = defaultdict(list)
    for item in stats:
        by_table[item.normalized_table].append(item)
        if item.data_hash:
            by_hash[item.data_hash].append(item)

    for item in stats:
        if item.rows == 0:
            item.action = "drop_empty"
            item.reason = "空表，没有业务记录"
        elif is_irrelevant_table(item.normalized_table):
            item.action = "drop_irrelevant"
            item.reason = "系统/配置/会话/日志类数据，通常不进入项目业务分析"
        elif not is_core_table(item.normalized_table) and "系统/权限/配置" in item.dimensions:
            item.action = "review_irrelevant"
            item.reason = "疑似系统侧数据，建议人工确认后删除"
        else:
            item.action = "keep"
            item.reason = "保留用于后续项目分析"

    for _digest, group in by_hash.items():
        if len(group) <= 1:
            continue
        keeper = sorted(group, key=lambda x: (x.action.startswith("drop"), x.zip_name, x.member_name))[0]
        for item in group:
            if item is keeper or item.action.startswith("drop"):
                continue
            item.action = "drop_duplicate_export"
            item.reason = f"与 {keeper.zip_name}/{keeper.member_name} 数据内容完全一致"

    for table, group in by_table.items():
        if len(group) <= 1:
            continue
        non_dropped = [x for x in group if not x.action.startswith("drop")]
        if len(non_dropped) <= 1:
            continue
        largest = max(non_dropped, key=lambda x: (x.rows, x.cols))
        for item in non_dropped:
            if item is largest:
                item.reason += "；同名表多次导出，暂保留记录数最多版本"
            else:
                item.action = "review_duplicate_export"
                item.reason = f"同名表 {table} 存在多份导出，建议与 {largest.zip_name}/{largest.member_name} 比对后删除"


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_reports(output_dir: Path, stats: list[TableStats], max_rows: int | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory_fields = [
        "zip_name",
        "member_name",
        "normalized_table",
        "rows",
        "cols",
        "dimensions",
        "action",
        "reason",
        "key_columns",
        "exact_duplicate_rows",
        "key_duplicate_rows",
        "blank_field_ratio",
        "mostly_blank_columns",
        "sensitive_columns",
        "header",
    ]
    inventory_rows = [
        {
            "zip_name": s.zip_name,
            "member_name": s.member_name,
            "normalized_table": s.normalized_table,
            "rows": s.rows,
            "cols": s.cols,
            "dimensions": "、".join(s.dimensions),
            "action": s.action,
            "reason": s.reason,
            "key_columns": ",".join(s.key_columns),
            "exact_duplicate_rows": s.exact_duplicate_rows,
            "key_duplicate_rows": s.key_duplicate_rows,
            "blank_field_ratio": f"{s.blank_field_ratio:.2%}",
            "mostly_blank_columns": ",".join(s.mostly_blank_columns[:30]),
            "sensitive_columns": ",".join(s.sensitive_columns),
            "header": ",".join(s.header),
        }
        for s in sorted(stats, key=lambda x: (x.action, x.normalized_table, x.zip_name))
    ]
    write_csv(output_dir / "table_inventory.csv", inventory_rows, inventory_fields)

    recommendation_rows = [
        row
        for row in inventory_rows
        if str(row["action"]).startswith("drop") or str(row["action"]).startswith("review")
    ]
    write_csv(output_dir / "cleanup_recommendations.csv", recommendation_rows, inventory_fields)

    dimension_counts = Counter()
    for s in stats:
        for dim in s.dimensions:
            dimension_counts[dim] += s.rows

    action_counts = Counter(s.action for s in stats)
    duplicate_tables = [s for s in stats if "duplicate" in s.action or s.exact_duplicate_rows or s.key_duplicate_rows]
    sensitive_tables = [s for s in stats if s.sensitive_columns]
    top_tables = sorted(stats, key=lambda s: s.rows, reverse=True)[:20]

    row_scope = "全量" if max_rows is None else f"抽样（每表最多 {max_rows:,} 行数据）"
    row_label = "总业务行数" if max_rows is None else "样本业务行数"
    top_title = "## 最大的 20 张表" if max_rows is None else "## 最大的 20 张表（样本内）"

    lines = [
        "# APP 导出数据初步清洗与分析报告",
        "",
        "## 总览",
        f"- 文件表数量：{len(stats)}",
        f"- 分析范围：{row_scope}",
        f"- {row_label}（按各导出表累加）：{sum(s.rows for s in stats):,}",
        "- 处理建议：" + "；".join(f"{k}={v}" for k, v in sorted(action_counts.items())),
        "",
        "## 主要信息和维度",
    ]
    for dim, count in dimension_counts.most_common():
        lines.append(f"- {dim}：约 {count:,} 行")
    lines.extend(["", top_title])
    for s in top_tables:
        lines.append(f"- {s.normalized_table}：{s.rows:,} 行，{s.cols} 列，来源 {s.zip_name}")
    lines.extend(["", "## 建议删除或复核的数据"])
    for action, count in action_counts.most_common():
        lines.append(f"- {action}：{count} 张表")
    lines.append("")
    lines.append("详见 `cleanup_recommendations.csv`。")
    lines.extend(["", "## 重复数据提示"])
    if duplicate_tables:
        for s in duplicate_tables[:50]:
            lines.append(
                f"- {s.normalized_table} / {s.zip_name}：表内完全重复 {s.exact_duplicate_rows} 行，"
                f"业务键重复 {s.key_duplicate_rows} 行，建议={s.action}"
            )
    else:
        lines.append("- 未发现明显重复行或重复导出。")
    lines.extend(["", "## 敏感字段提示"])
    if sensitive_tables:
        for s in sensitive_tables[:50]:
            lines.append(f"- {s.normalized_table}：{', '.join(s.sensitive_columns)}")
    else:
        lines.append("- 未识别到明显敏感字段。")
    lines.extend(
        [
            "",
            "## 使用建议",
            "- 原始 zip 不会被修改。",
            "- 先查看 `table_inventory.csv` 和 `cleanup_recommendations.csv`，确认 drop/review 规则是否符合你的业务目标。",
            "- 如需导出清洗后的 CSV，重新运行脚本并加上 `--export-cleaned`。",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_cleaned_csv(input_dir: Path, output_dir: Path, stats: list[TableStats], max_rows: int | None) -> None:
    cleaned_dir = output_dir / "cleaned_csv"
    if cleaned_dir.exists():
        shutil.rmtree(cleaned_dir)
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    keep = [s for s in stats if s.action == "keep"]
    for item in keep:
        zip_path = input_dir / item.zip_name
        with ZipFile(zip_path) as zf:
            rows = iter_xlsx_rows(zf.read(item.member_name))
            header = next(rows, [])
            key_positions = choose_key_columns([clean_value(v) for v in header], item.normalized_table)
            seen_rows: set[str] = set()
            seen_keys: set[tuple[str, ...]] = set()
            out_path = cleaned_dir / f"{item.normalized_table}.csv"
            with out_path.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([clean_value(v) for v in header])
                for row_no, row in enumerate(rows, start=1):
                    if max_rows is not None and row_no > max_rows:
                        break
                    values = [clean_value(v) for v in row]
                    if not any(values):
                        continue
                    if len(values) < len(header):
                        values.extend([""] * (len(header) - len(values)))
                    values = values[: len(header)]
                    digest = row_digest(values)
                    if digest in seen_rows:
                        continue
                    seen_rows.add(digest)
                    if key_positions:
                        key = tuple(values[i] if i < len(values) else "" for i in key_positions)
                        if any(key):
                            if key in seen_keys:
                                continue
                            seen_keys.add(key)
                    writer.writerow(values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze app export zip/xlsx files.")
    parser.add_argument("--input-dir", default=".", help="Directory containing export zip files.")
    parser.add_argument("--output-dir", default="analysis_output", help="Directory for reports.")
    parser.add_argument("--zip", dest="zip_names", action="append", default=[], help="Specific zip file to analyze. Can repeat.")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional per-table row limit for faster sampling.")
    parser.add_argument("--export-cleaned", action="store_true", help="Export cleaned CSV files for kept tables.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    members = collect_zip_members(input_dir, args.zip_names)
    if not members:
        print(f"No .xlsx files found in zip files under {input_dir}", file=sys.stderr)
        return 1

    stats: list[TableStats] = []
    for idx, (zip_path, member_name) in enumerate(members, start=1):
        print(f"[{idx}/{len(members)}] {zip_path.name} :: {member_name}", flush=True)
        with ZipFile(zip_path) as zf:
            item = analyze_member(zip_path.name, member_name, zf.read(member_name), args.max_rows)
            stats.append(item)

    mark_actions(stats)
    write_reports(output_dir, stats, args.max_rows)
    if args.export_cleaned:
        export_cleaned_csv(input_dir, output_dir, stats, args.max_rows)

    print(f"\nDone. Report: {output_dir / 'report.md'}")
    print(f"Inventory: {output_dir / 'table_inventory.csv'}")
    print(f"Recommendations: {output_dir / 'cleanup_recommendations.csv'}")
    if args.export_cleaned:
        print(f"Cleaned CSV: {output_dir / 'cleaned_csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
