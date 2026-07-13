#!/usr/bin/env python3
"""Resolve annotation replicates by voting and prepare third-pass tie breaks."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CSV = ROOT / "sampling" / "annotation_pairs_blind.csv"
DEFAULT_PRIMARY_ANNOTATIONS = ROOT / "sampling" / "annotation_pairs_blind.csv.annotations.csv"
DEFAULT_TIEBREAK_CSV = ROOT / "sampling" / "annotation_pairs_tiebreak.csv"
DEFAULT_TIEBREAK_ANNOTATIONS = ROOT / "sampling" / "annotation_pairs_tiebreak.csv.annotations.csv"
DEFAULT_GOLD_CSV = ROOT / "model_test" / "gold" / "annotation_pairs_test.csv"
DEFAULT_MODEL_TEST_COPY = ROOT / "model_test" / "annotation_pairs_test.csv"

VOTE_COLUMNS = ["has_opportunity", "opportunity_score", "cooperation_type", "role_direction", "confidence"]
GOLD_COLUMNS = [
    "annotation_id",
    "source_annotation_id",
    "object_a_profile",
    "object_b_profile",
    *VOTE_COLUMNS,
    "decision_source",
    "vote_count",
    "decided_at",
]
TIEBREAK_COLUMNS = [
    "annotation_id",
    "source_annotation_id",
    "object_a_profile",
    "object_b_profile",
    *VOTE_COLUMNS,
    "tiebreak_fields",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-csv", type=Path, default=DEFAULT_BASE_CSV)
    parser.add_argument("--primary-annotations", type=Path, default=DEFAULT_PRIMARY_ANNOTATIONS)
    parser.add_argument("--tiebreak-annotations", type=Path, default=DEFAULT_TIEBREAK_ANNOTATIONS)
    parser.add_argument("--gold-csv", type=Path, default=DEFAULT_GOLD_CSV)
    parser.add_argument("--model-test-copy", type=Path, default=DEFAULT_MODEL_TEST_COPY)
    parser.add_argument("--tiebreak-csv", type=Path, default=DEFAULT_TIEBREAK_CSV)
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Recompute gold from all available annotation rows instead of preserving existing gold rows.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def read_csv(path: Path, encoding: str) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding=encoding) as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str], encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding=encoding) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def source_id(row: dict[str, str]) -> str:
    return (row.get("source_annotation_id") or row.get("annotation_id") or "").strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def existing_gold_source_ids(rows: list[dict[str, str]]) -> set[str]:
    ids = set()
    for row in rows:
        sid = source_id(row)
        if sid:
            ids.add(sid)
    return ids


def vote_value(rows: list[dict[str, str]], column: str) -> tuple[str, bool]:
    values = [str(row.get(column, "")).strip() for row in rows if str(row.get(column, "")).strip()]
    if not values:
        return "", True
    counts = Counter(values)
    most_common = counts.most_common()
    if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
        return "", True
    return most_common[0][0], False


def group_annotations(*annotation_sets: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for rows in annotation_sets:
        for row in rows:
            sid = source_id(row)
            if sid:
                grouped[sid].append(row)
    return grouped


def resolve_one(
    sid: str,
    annotations: list[dict[str, str]],
    base_by_id: dict[str, dict[str, str]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    base = base_by_id.get(sid)
    if not base:
        return None, None

    decided: dict[str, str] = {}
    tied_fields: list[str] = []
    for column in VOTE_COLUMNS:
        value, tied = vote_value(annotations, column)
        if tied:
            tied_fields.append(column)
        else:
            decided[column] = value

    if not tied_fields:
        gold_row = {
            "annotation_id": sid,
            "source_annotation_id": sid,
            "object_a_profile": base.get("object_a_profile", ""),
            "object_b_profile": base.get("object_b_profile", ""),
            **decided,
            "decision_source": "vote",
            "vote_count": len(annotations),
            "decided_at": now_iso(),
        }
        return gold_row, None

    tiebreak_row = {
        "annotation_id": sid,
        "source_annotation_id": sid,
        "object_a_profile": base.get("object_a_profile", ""),
        "object_b_profile": base.get("object_b_profile", ""),
        **{column: decided.get(column, "") for column in VOTE_COLUMNS},
        "tiebreak_fields": "|".join(tied_fields),
    }
    return None, tiebreak_row


def main() -> int:
    args = parse_args()

    base_rows = read_csv(args.base_csv, args.encoding)
    primary_rows = read_csv(args.primary_annotations, args.encoding)
    tiebreak_rows = read_csv(args.tiebreak_annotations, args.encoding)
    existing_gold_rows = [] if args.rebuild else read_csv(args.gold_csv, args.encoding)

    base_by_id = {row["annotation_id"]: row for row in base_rows if row.get("annotation_id")}
    grouped = group_annotations(primary_rows, tiebreak_rows)
    gold_ids = existing_gold_source_ids(existing_gold_rows)

    new_gold_rows: list[dict[str, Any]] = []
    pending_tiebreak_rows: list[dict[str, Any]] = []

    for sid in sorted(grouped):
        if sid in gold_ids:
            continue
        gold_row, tiebreak_row = resolve_one(sid, grouped[sid], base_by_id)
        if gold_row:
            new_gold_rows.append(gold_row)
        elif tiebreak_row:
            pending_tiebreak_rows.append(tiebreak_row)

    final_gold_rows = [*existing_gold_rows, *new_gold_rows]

    print(f"base rows: {len(base_rows)}")
    print(f"primary annotation rows: {len(primary_rows)}")
    print(f"tiebreak annotation rows: {len(tiebreak_rows)}")
    print(f"existing gold source ids: {len(gold_ids)}")
    print(f"new gold rows: {len(new_gold_rows)}")
    print(f"pending tiebreak rows: {len(pending_tiebreak_rows)}")

    if args.dry_run:
        return 0

    write_csv(args.gold_csv, final_gold_rows, GOLD_COLUMNS, args.encoding)
    if args.model_test_copy:
        write_csv(args.model_test_copy, final_gold_rows, GOLD_COLUMNS, args.encoding)
    write_csv(args.tiebreak_csv, pending_tiebreak_rows, TIEBREAK_COLUMNS, args.encoding)

    print(f"wrote gold: {args.gold_csv}")
    if args.model_test_copy:
        print(f"wrote model_test copy: {args.model_test_copy}")
    print(f"wrote tiebreak csv: {args.tiebreak_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
