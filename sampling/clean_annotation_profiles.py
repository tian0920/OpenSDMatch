import argparse
import csv
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = BASE_DIR / "annotation_pairs_blind.csv"
DEFAULT_OUTPUT = BASE_DIR / "annotation_pairs_blind_cleaned.csv"

PROFILE_COLUMNS = ("object_a_profile", "object_b_profile")
REMOVED_PREFIXES = (
    "供给词",
    "需求词",
    "供给关键词",
    "需求关键词",
    "supply words",
    "demand words",
    "supply keywords",
    "demand keywords",
)


def should_remove_profile_line(line: str) -> bool:
    normalized = line.strip().lower()
    if not normalized:
        return False

    return any(
        normalized.startswith(f"{prefix}:")
        or normalized.startswith(f"{prefix}：")
        for prefix in REMOVED_PREFIXES
    )


def clean_profile_text(value: str) -> str:
    if value is None:
        return ""

    kept_lines = [
        line.rstrip()
        for line in str(value).splitlines()
        if not should_remove_profile_line(line)
    ]

    return "\n".join(line for line in kept_lines if line.strip())


def clean_csv(input_path: Path, output_path: Path) -> tuple[int, int]:
    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{input_path} is empty or missing a header row")

        missing_cols = [col for col in PROFILE_COLUMNS if col not in reader.fieldnames]
        if missing_cols:
            raise ValueError(f"{input_path} missing columns: {missing_cols}")

        rows = list(reader)
        fieldnames = reader.fieldnames

    changed_cells = 0
    for row in rows:
        for col in PROFILE_COLUMNS:
            original = row.get(col, "")
            cleaned = clean_profile_text(original)
            if cleaned != original:
                changed_cells += 1
            row[col] = cleaned

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows), changed_cells


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove supply/demand keyword lines from annotation profile columns.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input CSV path. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite the input file after writing a .bak backup.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()

    if args.in_place:
        backup_path = input_path.with_suffix(input_path.suffix + ".bak")
        backup_path.write_bytes(input_path.read_bytes())
        output_path = input_path
    else:
        output_path = args.output.resolve()

    row_count, changed_cells = clean_csv(input_path, output_path)

    print(f"Cleaned rows: {row_count}")
    print(f"Changed profile cells: {changed_cells}")
    print(f"Output: {output_path}")
    if args.in_place:
        print(f"Backup: {backup_path}")


if __name__ == "__main__":
    main()
