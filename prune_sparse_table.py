#!/usr/bin/env python3
"""
Prune sparse rows and columns from a merged CSV table.

The script is conservative by default:
- Always keeps protected identifier columns such as uid and source_tables.
- Drops columns whose empty ratio is at or above --col-empty-threshold.
- Drops rows whose kept-column non-empty count is below --row-min-nonempty
  or whose kept-column fill ratio is below --row-min-fill-ratio.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_EMPTY_VALUES = {"", "[]", "{}", "null", "none", "nan", "undefined"}
DEFAULT_PROTECTED_COLUMNS = {
    "uid",
    "source_tables",
    "name",
    "display_name",
    "real_name",
    "mobile",
    "email",
    "company",
    "position",
}


def norm(value: object) -> str:
    return "" if value is None else str(value).strip()


def is_empty(value: object) -> bool:
    text = norm(value)
    return text.lower() in DEFAULT_EMPTY_VALUES


def read_header(input_path: Path) -> list[str]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        return next(reader, [])


def count_columns(input_path: Path, header: list[str]) -> tuple[int, dict[str, int]]:
    nonempty_counts = {col: 0 for col in header}
    total_rows = 0
    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            for col in header:
                if not is_empty(row.get(col, "")):
                    nonempty_counts[col] += 1
    return total_rows, nonempty_counts


def choose_columns(
    header: list[str],
    total_rows: int,
    nonempty_counts: dict[str, int],
    col_empty_threshold: float,
    protected_columns: set[str],
) -> tuple[list[str], list[dict[str, object]]]:
    kept: list[str] = []
    dropped: list[dict[str, object]] = []
    for col in header:
        nonempty = nonempty_counts.get(col, 0)
        empty_ratio = 1 - (nonempty / total_rows if total_rows else 0)
        protected = col in protected_columns
        if protected or empty_ratio < col_empty_threshold:
            kept.append(col)
        else:
            dropped.append(
                {
                    "column": col,
                    "nonempty_count": nonempty,
                    "empty_ratio": f"{empty_ratio:.2%}",
                    "reason": f"empty_ratio >= {col_empty_threshold:.0%}",
                }
            )
    return kept, dropped


def prune_rows(
    input_path: Path,
    output_path: Path,
    kept_columns: list[str],
    row_min_nonempty: int,
    row_min_fill_ratio: float,
) -> dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = kept = dropped = 0
    with input_path.open("r", encoding="utf-8-sig", newline="") as src, output_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=kept_columns, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            total += 1
            nonempty = sum(1 for col in kept_columns if not is_empty(row.get(col, "")))
            fill_ratio = nonempty / len(kept_columns) if kept_columns else 0
            if nonempty < row_min_nonempty or fill_ratio < row_min_fill_ratio:
                dropped += 1
                continue
            writer.writerow({col: row.get(col, "") for col in kept_columns})
            kept += 1
    return {"total_rows": total, "kept_rows": kept, "dropped_rows": dropped}


def write_dropped_columns(path: Path, dropped_columns: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["column", "nonempty_count", "empty_ratio", "reason"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dropped_columns)


def write_report(
    path: Path,
    input_path: Path,
    output_path: Path,
    original_cols: int,
    kept_cols: int,
    dropped_columns: list[dict[str, object]],
    row_stats: dict[str, int],
    args: argparse.Namespace,
) -> None:
    lines = [
        "# 稀疏行列清理报告",
        "",
        f"- 输入文件：{input_path}",
        f"- 输出文件：{output_path}",
        f"- 原始列数：{original_cols}",
        f"- 保留列数：{kept_cols}",
        f"- 删除列数：{len(dropped_columns)}",
        f"- 原始行数：{row_stats['total_rows']:,}",
        f"- 保留行数：{row_stats['kept_rows']:,}",
        f"- 删除行数：{row_stats['dropped_rows']:,}",
        "",
        "## 阈值",
        f"- 删除列：空值率 >= {args.col_empty_threshold:.0%}",
        f"- 删除行：非空字段数 < {args.row_min_nonempty} 或填充率 < {args.row_min_fill_ratio:.0%}",
        f"- 保护列：{', '.join(sorted(args.protect_column))}",
        "",
        "## 删除列示例",
    ]
    for item in dropped_columns[:50]:
        lines.append(f"- {item['column']}：非空 {item['nonempty_count']}，空值率 {item['empty_ratio']}")
    if len(dropped_columns) > 50:
        lines.append(f"- 其余 {len(dropped_columns) - 50} 列见 dropped_sparse_columns.csv")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Drop sparse rows and columns from a CSV file.")
    parser.add_argument(
        "--input",
        default="/home/ecs-user/merged_output/user_profiles_merged.csv",
        help="Input merged CSV.",
    )
    parser.add_argument(
        "--output",
        default="/home/ecs-user/merged_output/user_profiles_pruned.csv",
        help="Output pruned CSV.",
    )
    parser.add_argument(
        "--report-dir",
        default="/home/ecs-user/merged_output",
        help="Directory for pruning report files.",
    )
    parser.add_argument(
        "--col-empty-threshold",
        type=float,
        default=0.98,
        help="Drop columns with empty ratio >= this value.",
    )
    parser.add_argument(
        "--row-min-nonempty",
        type=int,
        default=8,
        help="Drop rows with fewer non-empty fields than this after column pruning.",
    )
    parser.add_argument(
        "--row-min-fill-ratio",
        type=float,
        default=0.05,
        help="Drop rows with fill ratio below this after column pruning.",
    )
    parser.add_argument(
        "--protect-column",
        action="append",
        default=sorted(DEFAULT_PROTECTED_COLUMNS),
        help="Column to always keep. Can be repeated.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    report_dir = Path(args.report_dir).resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    header = read_header(input_path)
    total_rows, nonempty_counts = count_columns(input_path, header)
    kept_columns, dropped_columns = choose_columns(
        header,
        total_rows,
        nonempty_counts,
        args.col_empty_threshold,
        set(args.protect_column),
    )
    row_stats = prune_rows(
        input_path,
        output_path,
        kept_columns,
        args.row_min_nonempty,
        args.row_min_fill_ratio,
    )
    write_dropped_columns(report_dir / "dropped_sparse_columns.csv", dropped_columns)
    write_report(
        report_dir / "prune_sparse_report.md",
        input_path,
        output_path,
        len(header),
        len(kept_columns),
        dropped_columns,
        row_stats,
        args,
    )
    print(f"Done. Output: {output_path}")
    print(f"Rows kept/dropped: {row_stats['kept_rows']:,}/{row_stats['dropped_rows']:,}")
    print(f"Columns kept/dropped: {len(kept_columns)}/{len(dropped_columns)}")
    print(f"Report: {report_dir / 'prune_sparse_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
