#!/usr/bin/env python3
"""Keep only annotation_id, model, gold, and prediction in prediction JSONL files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


KEEP_FIELDS = ["annotation_id", "model", "gold", "prediction"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def compact_record(record: dict) -> dict:
    return {field: record.get(field) for field in KEEP_FIELDS}


def main() -> int:
    args = parse_args()
    output_path = args.output
    if args.in_place:
        output_path = args.path.with_suffix(args.path.suffix + ".tmp")
    if output_path is None:
        output_path = args.path.with_name(f"{args.path.stem}.compact{args.path.suffix}")

    with args.path.open(encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            record = compact_record(json.loads(line))
            dst.write(json.dumps(record, ensure_ascii=False) + "\n")

    if args.in_place:
        output_path.replace(args.path)
    print(f"Wrote compact JSONL to {args.path if args.in_place else output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
