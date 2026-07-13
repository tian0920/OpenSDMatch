#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI-assisted candidate screening for OpenSDMatch annotation-pair construction.

This script can run one candidate-pair screening job or all four jobs:

1. high_score_ai_candidates.csv + high_score_prompt.txt
2. mid_low_score_ai_candidates.csv + mid_low_score_prompt.txt
3. hard_negative_candidates.csv + hard_negative_prompt.txt
4. random_negative_candidates.csv + random_negative_prompt.txt

It uses Aliyun Bailian / DashScope OpenAI-compatible API.

Usage:

  export DASHSCOPE_API_KEY="your_api_key"

  # Run all four candidate screening jobs
  python3 sampling/run_ai_sampling_all.py --all

  # Run only one job
  python3 sampling/run_ai_sampling_all.py --job high_score
  python3 sampling/run_ai_sampling_all.py --job mid_low
  python3 sampling/run_ai_sampling_all.py --job hard_negative
  python3 sampling/run_ai_sampling_all.py --job random_negative

  # Small test: run first 10 rows of every job
  python3 sampling/run_ai_sampling_all.py --all --limit 10 --batch-size 5

Default directory layout:

  sampling/
    run_ai_sampling_all.py
    data/
      high_score_ai_candidates.csv
      mid_low_score_ai_candidates.csv
      hard_negative_candidates.csv
      random_negative_candidates.csv
    prompts/
      high_score_prompt.txt
      mid_low_score_prompt.txt
      hard_negative_prompt.txt
      random_negative_prompt.txt
    outputs/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from openai import OpenAI


DEFAULT_MODEL = "qwen3.7-max"
DEFAULT_BASE_URL = "https://llm-jhxtd03gjg0gd2o2.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"

DEFAULT_BATCH_SIZE = 30
DEFAULT_SLEEP_SECONDS = 1.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_EXISTING_ANNOTATION_CSV = "sampling/annotation_pairs_blind.csv"

# These columns should not be sent to the model for candidate screening.
# AI screening is not final gold labeling, but we still avoid obvious leakage/noisy fields.
LEAKAGE_COLUMNS = {
    "reason",
    "action_plan",
    "raw_json",
    "match_type",
    "status",
    "edge_type",
}

# Keep these columns first if they exist.
PREFERRED_COLUMNS = [
    "pair_id",
    "sampling_group",
    "ai_score",
    "source",
    "existing_edge",
    "same_industry",
    "industry_a",
    "industry_b",
    "tag_similarity_score",
    "complementarity_score",
    "shared_tags",
    "source_id",
    "target_id",
    "object_a_name",
    "object_b_name",
    "object_a_profile",
    "object_b_profile",
]


@dataclass(frozen=True)
class ScreeningJob:
    name: str
    input_csv: str
    prompt_file: str
    output_jsonl: str


JOBS: dict[str, ScreeningJob] = {
    "high_score": ScreeningJob(
        name="high_score",
        input_csv="high_score_ai_candidates.csv",
        prompt_file="high_score_prompt.txt",
        output_jsonl="high_score_ai_results.jsonl",
    ),
    "mid_low": ScreeningJob(
        name="mid_low",
        input_csv="mid_low_score_ai_candidates.csv",
        prompt_file="mid_low_score_prompt.txt",
        output_jsonl="mid_low_score_ai_results.jsonl",
    ),
    "hard_negative": ScreeningJob(
        name="hard_negative",
        input_csv="hard_negative_candidates.csv",
        prompt_file="hard_negative_prompt.txt",
        output_jsonl="hard_negative_results.jsonl",
    ),
    "random_negative": ScreeningJob(
        name="random_negative",
        input_csv="random_negative_candidates.csv",
        prompt_file="random_negative_prompt.txt",
        output_jsonl="random_negative_results.jsonl",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AI-assisted screening for OpenSDMatch candidate pairs."
    )

    run_group = parser.add_mutually_exclusive_group()
    run_group.add_argument(
        "--all",
        action="store_true",
        help="Run all four built-in screening jobs.",
    )
    run_group.add_argument(
        "--job",
        choices=sorted(JOBS.keys()),
        help="Run one built-in job.",
    )

    parser.add_argument(
        "--data-dir",
        default="sampling/data",
        help="Directory containing candidate CSV files. Default: sampling/data",
    )
    parser.add_argument(
        "--prompt-dir",
        default="sampling/prompts",
        help="Directory containing prompt txt files. Default: sampling/prompts",
    )
    parser.add_argument(
        "--output-dir",
        default="sampling/outputs",
        help="Directory for output JSONL files. Default: sampling/outputs",
    )

    # Single-file mode remains available for custom input/prompt/output.
    parser.add_argument(
        "--input",
        default=None,
        help="Custom input candidate CSV path. Used only when --all and --job are not set.",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Custom prompt txt path. Used only when --all and --job are not set.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Custom output JSONL path. Used only when --all and --job are not set.",
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model name. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI-compatible base URL.",
    )
    parser.add_argument(
        "--api-key-env",
        default="DASHSCOPE_API_KEY",
        help="Environment variable name for API key. Default: DASHSCOPE_API_KEY",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Batch size. Default: {DEFAULT_BATCH_SIZE}",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Start row index, useful for resuming or testing. In --all mode, applies to every job.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of rows to process. In --all mode, applies to every job.",
    )
    parser.add_argument(
        "--existing-annotation-csv",
        default=DEFAULT_EXISTING_ANNOTATION_CSV,
        help=(
            "Existing annotation CSV used to skip company pairs already in the "
            "human annotation pool. "
            f"Default: {DEFAULT_EXISTING_ANNOTATION_CSV}"
        ),
    )
    parser.add_argument(
        "--no-skip-existing-annotation-pairs",
        action="store_true",
        help="Do not skip company pairs that already appear in --existing-annotation-csv.",
    )
    parser.add_argument(
        "--no-skip-existing-output-pairs",
        action="store_true",
        help=(
            "Do not skip rows already represented in output JSONL files. Without "
            "this flag, existing pair_id values in the current output and company "
            "pairs found across all four built-in output files are skipped before "
            "API calls."
        ),
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help=f"Sleep seconds between requests. Default: {DEFAULT_SLEEP_SECONDS}",
    )
    parser.add_argument(
        "--job-sleep",
        type=float,
        default=2.0,
        help="Sleep seconds between jobs in --all mode. Default: 2.0",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=f"Max retries for each batch. Default: {DEFAULT_MAX_RETRIES}",
    )
    parser.add_argument(
        "--enable-thinking",
        action="store_true",
        help="Enable model thinking mode via extra_body. Final output only saves delta.content, not reasoning_content.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Deprecated compatibility flag. Output files are appended by default unless --overwrite-output is set.",
    )
    parser.add_argument(
        "--overwrite-output",
        action="store_true",
        help=(
            "Overwrite the output JSONL instead of appending/resuming. This also "
            "disables skipping existing pair_id values from that output file."
        ),
    )

    return parser.parse_args()


def get_client(api_key_env: str, base_url: str) -> OpenAI:
    api_key = os.getenv(api_key_env)

    if not api_key:
        raise RuntimeError(
            f"Missing API key. Please set it first:\n\n"
            f"  export {api_key_env}=\"your_api_key\"\n\n"
            f"Current api_key_env = {api_key_env}"
        )

    return OpenAI(api_key=api_key, base_url=base_url)


def clean_cell(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    # Avoid extremely long cells exploding prompt length.
    if len(text) > 1200:
        text = text[:1200] + "…"
    return text


def normalize_company_name(value: Any) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", "", str(value).strip())


def extract_company_name_from_profile(value: Any) -> str:
    text = clean_cell(value)
    if not text:
        return ""

    for line in text.splitlines():
        match = re.match(r"^\s*公司名称\s*[:：]\s*(.+?)\s*$", line)
        if match:
            return normalize_company_name(match.group(1))

    return ""


def pair_key(name_a: Any, name_b: Any) -> tuple[str, str] | None:
    a = normalize_company_name(name_a)
    b = normalize_company_name(name_b)
    if not a or not b:
        return None
    return tuple(sorted((a, b)))


def load_existing_annotation_pair_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        print(f"[Skip existing] Annotation CSV not found, skip filter disabled: {path}")
        return set()

    df = pd.read_csv(path, low_memory=False)
    keys: set[tuple[str, str]] = set()

    for _, row in df.iterrows():
        name_a = row.get("object_a_name", "")
        name_b = row.get("object_b_name", "")

        if not normalize_company_name(name_a):
            name_a = extract_company_name_from_profile(row.get("object_a_profile", ""))
        if not normalize_company_name(name_b):
            name_b = extract_company_name_from_profile(row.get("object_b_profile", ""))

        key = pair_key(name_a, name_b)
        if key is not None:
            keys.add(key)

    print(f"[Skip existing] Loaded {len(keys)} existing annotation pair keys from {path}")
    return keys


def skip_existing_annotation_pairs(
    df: pd.DataFrame,
    existing_pair_keys: set[tuple[str, str]],
) -> pd.DataFrame:
    if not existing_pair_keys:
        return df

    if "object_a_name" not in df.columns or "object_b_name" not in df.columns:
        print(
            "[Skip existing] Candidate CSV missing object_a_name/object_b_name; "
            "skip filter disabled for this job.",
            file=sys.stderr,
        )
        return df

    keep_mask = []
    skipped = 0
    for _, row in df.iterrows():
        key = pair_key(row.get("object_a_name", ""), row.get("object_b_name", ""))
        should_skip = key in existing_pair_keys if key is not None else False
        keep_mask.append(not should_skip)
        if should_skip:
            skipped += 1

    if skipped:
        print(f"[Skip existing] Skipped {skipped} candidate rows already in annotation pool.")
    else:
        print("[Skip existing] No candidate rows found in existing annotation pool.")

    return df.loc[keep_mask].copy()


def load_existing_output_pair_ids(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()

    pair_ids = set()
    with path.open("r", encoding="utf-8") as fin:
        for line_no, line in enumerate(fin, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                print(
                    f"[Output resume] Ignored invalid JSON at {path}, line {line_no}",
                    file=sys.stderr,
                )
                continue
            pair_id = obj.get("pair_id")
            if pair_id:
                pair_ids.add(str(pair_id))

    return pair_ids


def skip_existing_output_pairs(df: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    if "pair_id" not in df.columns:
        return df

    existing_pair_ids = load_existing_output_pair_ids(output_path)
    if not existing_pair_ids:
        return df

    before = len(df)
    filtered = df[~df["pair_id"].astype(str).isin(existing_pair_ids)].copy()
    skipped = before - len(filtered)
    print(f"[Output resume] Skipped {skipped} candidate rows already in {output_path}.")
    return filtered


def load_existing_output_pair_keys(
    data_dir: Path,
    output_dir: Path,
) -> set[tuple[str, str]]:
    """
    Load pair_ids from all built-in output JSONLs, then resolve them through
    their candidate CSVs to company-name pair keys.
    """
    keys: set[tuple[str, str]] = set()

    for job in JOBS.values():
        output_path = output_dir / job.output_jsonl
        pair_ids = load_existing_output_pair_ids(output_path)
        if not pair_ids:
            continue

        candidate_path = data_dir / job.input_csv
        if not candidate_path.exists():
            print(
                f"[Output global skip] Candidate CSV not found, cannot resolve "
                f"{output_path}: {candidate_path}",
                file=sys.stderr,
            )
            continue

        try:
            candidates = pd.read_csv(
                candidate_path,
                usecols=["pair_id", "object_a_name", "object_b_name"],
                low_memory=False,
            )
        except ValueError:
            candidates = pd.read_csv(candidate_path, low_memory=False)

        required = {"pair_id", "object_a_name", "object_b_name"}
        if not required.issubset(candidates.columns):
            print(
                f"[Output global skip] Candidate CSV missing required columns: {candidate_path}",
                file=sys.stderr,
            )
            continue

        screened = candidates[candidates["pair_id"].astype(str).isin(pair_ids)]
        for _, row in screened.iterrows():
            key = pair_key(row.get("object_a_name", ""), row.get("object_b_name", ""))
            if key is not None:
                keys.add(key)

    print(f"[Output global skip] Loaded {len(keys)} company pair keys from built-in output JSONLs.")
    return keys


def skip_existing_output_pair_keys(
    df: pd.DataFrame,
    existing_output_pair_keys: set[tuple[str, str]],
) -> pd.DataFrame:
    if not existing_output_pair_keys:
        return df

    if "object_a_name" not in df.columns or "object_b_name" not in df.columns:
        print(
            "[Output global skip] Candidate CSV missing object_a_name/object_b_name; "
            "global output pair skip disabled for this job.",
            file=sys.stderr,
        )
        return df

    keep_mask = []
    skipped = 0
    for _, row in df.iterrows():
        key = pair_key(row.get("object_a_name", ""), row.get("object_b_name", ""))
        should_skip = key in existing_output_pair_keys if key is not None else False
        keep_mask.append(not should_skip)
        if should_skip:
            skipped += 1

    if skipped:
        print(f"[Output global skip] Skipped {skipped} candidate rows already screened in built-in outputs.")
    else:
        print("[Output global skip] No candidate rows found in built-in output history.")

    return df.loc[keep_mask].copy()


def select_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for c in PREFERRED_COLUMNS:
        if c in df.columns and c not in LEAKAGE_COLUMNS:
            cols.append(c)

    # Include additional non-leakage columns only if they look useful and concise.
    for c in df.columns:
        if c in cols or c in LEAKAGE_COLUMNS:
            continue
        if c.startswith("label_"):
            continue
        if c.lower() in {"reason", "action_plan", "raw_json", "edge_type", "match_type", "status"}:
            continue

        # Names may help identify duplicate entities during AI quality screening.
        if c in {"object_a_name", "object_b_name"}:
            cols.append(c)
        elif c.startswith("object_") or c.startswith("industry") or c.endswith("_score"):
            cols.append(c)

    return cols


def make_batch_text(batch_df: pd.DataFrame) -> str:
    """
    Convert a batch of candidate pairs into compact JSON text.
    """
    cols = select_columns(batch_df)
    records: list[dict[str, Any]] = []

    for _, row in batch_df.iterrows():
        rec = {}
        for c in cols:
            value = clean_cell(row.get(c, ""))
            if value != "":
                rec[c] = value
        records.append(rec)

    return json.dumps(records, ensure_ascii=False, indent=2)


def strip_markdown_fences(text: str) -> str:
    """
    Some models may wrap JSONL in ```json or ```jsonl fences.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:jsonl|json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def normalize_jsonl(text: str) -> str:
    """
    Best-effort normalization:
    - remove Markdown code fences
    - if model returns a JSON array, convert it to JSONL
    - if model returns line-by-line JSON objects, keep valid JSONL lines
    """
    text = strip_markdown_fences(text)

    if not text:
        return ""

    # Case 1: JSON array or single JSON object.
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            records = [x for x in obj if isinstance(x, dict)]
            skipped = len(obj) - len(records)
            if skipped:
                print(
                    f"[Warning] Ignored {skipped} non-object values from model JSON array.",
                    file=sys.stderr,
                )
            return "\n".join(json.dumps(x, ensure_ascii=False) for x in records)
        if isinstance(obj, dict):
            return json.dumps(obj, ensure_ascii=False)
    except Exception:
        pass

    # Case 2: JSONL.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    valid_lines = []
    invalid_lines = []

    for line in lines:
        # Remove bullet prefix if accidentally generated.
        line = re.sub(r"^[\-\*\d\.\)\s]+(?=\{)", "", line).strip()
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                valid_lines.append(json.dumps(parsed, ensure_ascii=False))
            else:
                invalid_lines.append(line)
        except Exception:
            invalid_lines.append(line)

    if valid_lines:
        if invalid_lines:
            print(
                f"[Warning] Ignored {len(invalid_lines)} non-JSON lines from model output.",
                file=sys.stderr,
            )
        return "\n".join(valid_lines)

    # Fallback: return raw text for debugging.
    print("[Warning] Model output is not valid JSON/JSONL. Saving raw output.", file=sys.stderr)
    return text


def call_model(
    client: OpenAI,
    model: str,
    prompt: str,
    batch_text: str,
    enable_thinking: bool,
) -> str:
    """
    Call Aliyun Bailian / DashScope OpenAI-compatible Chat Completions API.

    We stream the response and collect only delta.content as final answer.
    If enable_thinking=True, reasoning_content may be returned by the model,
    but it is intentionally not written into the JSONL output.
    """
    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": (
                "下面是一批候选 pair。请严格按照 system prompt 的要求输出 JSONL，"
                "不要输出解释性文字、Markdown 代码块或额外说明。\n\n"
                f"{batch_text}"
            ),
        },
    ]

    extra_body = {"enable_thinking": True} if enable_thinking else None

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if extra_body is not None:
        kwargs["extra_body"] = extra_body

    completion = client.chat.completions.create(**kwargs)

    content_parts = []
    for chunk in completion:
        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta
        # Do not save reasoning_content. It is not part of the JSONL answer.
        if hasattr(delta, "content") and delta.content:
            content_parts.append(delta.content)

    return "".join(content_parts).strip()


def process_batches(
    client: OpenAI,
    df: pd.DataFrame,
    prompt: str,
    output_path: Path,
    model: str,
    batch_size: int,
    sleep_seconds: float,
    max_retries: int,
    enable_thinking: bool,
    append: bool,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if append else "w"
    write_path = output_path
    if not append:
        write_path = output_path.with_name(f"{output_path.name}.tmp")
        if write_path.exists():
            write_path.unlink()

    total = len(df)
    print(f"Total rows to process: {total}")
    print(f"Output: {output_path}")
    print(f"Model: {model}")

    with write_path.open(mode, encoding="utf-8") as fout:
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch_df = df.iloc[start:end]
            print(f"Processing rows {start} - {end - 1}")

            batch_text = make_batch_text(batch_df)
            last_error: Exception | None = None
            result_text = ""

            for attempt in range(1, max_retries + 1):
                try:
                    raw_text = call_model(
                        client=client,
                        model=model,
                        prompt=prompt,
                        batch_text=batch_text,
                        enable_thinking=enable_thinking,
                    )
                    result_text = normalize_jsonl(raw_text)
                    break
                except Exception as e:
                    last_error = e
                    wait = min(2**attempt, 30)
                    print(
                        f"[Error] Batch {start}-{end - 1}, attempt {attempt}/{max_retries} failed: {e}",
                        file=sys.stderr,
                    )
                    if attempt < max_retries:
                        print(f"Retrying in {wait}s...", file=sys.stderr)
                        time.sleep(wait)

            if not result_text:
                error_record = {
                    "batch_start": start,
                    "batch_end": end - 1,
                    "error": str(last_error) if last_error else "empty_model_output",
                }
                fout.write(json.dumps(error_record, ensure_ascii=False) + "\n")
            else:
                fout.write(result_text.strip() + "\n")

            fout.flush()
            time.sleep(sleep_seconds)

    if not append:
        write_path.replace(output_path)

    print(f"Done. Results saved to {output_path}")


def run_one_job(
    input_path: Path,
    prompt_path: Path,
    output_path: Path,
    args: argparse.Namespace,
    existing_pair_keys: set[tuple[str, str]],
    existing_output_pair_keys: set[tuple[str, str]],
) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    df = pd.read_csv(input_path, low_memory=False)

    if args.start < 0:
        raise ValueError("--start must be >= 0")

    df = df.iloc[args.start :]
    if args.limit is not None:
        df = df.iloc[: args.limit]

    if not args.overwrite_output and not args.no_skip_existing_output_pairs:
        df = skip_existing_output_pairs(df, output_path)
        df = skip_existing_output_pair_keys(df, existing_output_pair_keys)

    if not args.no_skip_existing_annotation_pairs:
        df = skip_existing_annotation_pairs(df, existing_pair_keys)

    if len(df) == 0:
        print(f"No rows to process: {input_path}")
        return

    prompt = prompt_path.read_text(encoding="utf-8")

    print("=" * 80)
    print(f"Input : {input_path}")
    print(f"Prompt: {prompt_path}")
    print(f"Output: {output_path}")
    print("=" * 80)

    client = get_client(api_key_env=args.api_key_env, base_url=args.base_url)

    append_output = not args.overwrite_output
    if append_output and output_path.exists() and output_path.stat().st_size > 0:
        print(f"[Output resume] Appending new rows to existing output: {output_path}")

    process_batches(
        client=client,
        df=df,
        prompt=prompt,
        output_path=output_path,
        model=args.model,
        batch_size=args.batch_size,
        sleep_seconds=args.sleep,
        max_retries=args.max_retries,
        enable_thinking=args.enable_thinking,
        append=append_output,
    )


def resolve_jobs(args: argparse.Namespace) -> list[tuple[Path, Path, Path]]:
    data_dir = Path(args.data_dir)
    prompt_dir = Path(args.prompt_dir)
    output_dir = Path(args.output_dir)

    if args.all:
        selected_jobs = [JOBS[k] for k in ["high_score", "mid_low", "hard_negative", "random_negative"]]  ## "high_score", 
        return [
            (data_dir / job.input_csv, prompt_dir / job.prompt_file, output_dir / job.output_jsonl)
            for job in selected_jobs
        ]

    if args.job:
        job = JOBS[args.job]
        return [(data_dir / job.input_csv, prompt_dir / job.prompt_file, output_dir / job.output_jsonl)]

    # Custom single-file mode. Keep backward compatibility.
    input_path = Path(args.input or data_dir / JOBS["high_score"].input_csv)
    prompt_path = Path(args.prompt or prompt_dir / JOBS["high_score"].prompt_file)
    output_path = Path(args.output or output_dir / JOBS["high_score"].output_jsonl)
    return [(input_path, prompt_path, output_path)]


def main() -> None:
    args = parse_args()
    jobs_to_run = resolve_jobs(args)
    existing_pair_keys = set()
    existing_output_pair_keys = set()

    if not args.no_skip_existing_annotation_pairs:
        existing_pair_keys = load_existing_annotation_pair_keys(
            Path(args.existing_annotation_csv)
        )

    if not args.overwrite_output and not args.no_skip_existing_output_pairs:
        existing_output_pair_keys = load_existing_output_pair_keys(
            Path(args.data_dir),
            Path(args.output_dir),
        )

    for idx, (input_path, prompt_path, output_path) in enumerate(jobs_to_run, start=1):
        print(f"\n[{idx}/{len(jobs_to_run)}] Starting screening job")
        run_one_job(
            input_path=input_path,
            prompt_path=prompt_path,
            output_path=output_path,
            args=args,
            existing_pair_keys=existing_pair_keys,
            existing_output_pair_keys=existing_output_pair_keys,
        )
        if idx < len(jobs_to_run):
            time.sleep(args.job_sleep)

    print("\nAll requested screening jobs finished.")


if __name__ == "__main__":
    main()
