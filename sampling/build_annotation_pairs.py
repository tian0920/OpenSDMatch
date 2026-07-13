import json
from pathlib import Path

import pandas as pd

from clean_annotation_profiles import clean_profile_text


RANDOM_SEED = 20260607

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"

# 最终人工标注数量
TARGET_COUNTS = {
    "high_score_ai_edge": 750,
    "mid_low_score_ai_edge": 750,
    "same_industry_hard_negative": 750,
    "random_negative": 750,
}

FILES = {
    "high_score_ai_edge": {
        "candidates": DATA_DIR / "high_score_ai_candidates.csv",
        "screening": OUTPUT_DIR / "high_score_ai_results.jsonl",
    },
    "mid_low_score_ai_edge": {
        "candidates": DATA_DIR / "mid_low_score_ai_candidates.csv",
        "screening": OUTPUT_DIR / "mid_low_score_ai_results.jsonl",
    },
    "same_industry_hard_negative": {
        "candidates": DATA_DIR / "hard_negative_candidates.csv",
        "screening": OUTPUT_DIR / "hard_negative_results.jsonl",
    },
    "random_negative": {
        "candidates": DATA_DIR / "random_negative_candidates.csv",
        "screening": OUTPUT_DIR / "random_negative_results.jsonl",
    },
}

SCREENING_JOBS = {
    "high_score_ai_edge": "high_score",
    "mid_low_score_ai_edge": "mid_low",
    "same_industry_hard_negative": "hard_negative",
    "random_negative": "random_negative",
}


def load_jsonl(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Screening JSONL not found: {path}")

    if path.stat().st_size == 0:
        return pd.DataFrame()

    records = []
    skipped_non_dict = 0
    invalid_lines = []
    decoder = json.JSONDecoder()

    text = path.read_text(encoding="utf-8")
    idx = 0
    n = len(text)

    while idx < n:
        while idx < n and text[idx].isspace():
            idx += 1

        if idx >= n:
            break

        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            line_no = text.count("\n", 0, idx) + 1
            line_end = text.find("\n", idx)
            if line_end == -1:
                line_end = n
            snippet = text[idx:line_end].strip()
            if snippet:
                invalid_lines.append((line_no, snippet[:120]))
            idx = line_end + 1
            continue

        if isinstance(obj, dict):
            records.append(obj)
        elif isinstance(obj, list):
            dict_items = [item for item in obj if isinstance(item, dict)]
            records.extend(dict_items)
            skipped_non_dict += len(obj) - len(dict_items)
        else:
            skipped_non_dict += 1

        idx = end

    if invalid_lines:
        for line_no, snippet in invalid_lines[:10]:
            print(f"[WARN] Invalid JSON at {path}, line {line_no}: {snippet}")
        if len(invalid_lines) > 10:
            print(f"[WARN] ... skipped {len(invalid_lines) - 10} more invalid lines in {path}")

    if skipped_non_dict:
        print(f"[WARN] Skipped {skipped_non_dict} non-object JSON values in {path}")

    return pd.DataFrame(records)


def require_pair_id_screening(group: str, path: Path, screening: pd.DataFrame) -> None:
    if "pair_id" in screening.columns:
        return

    job = SCREENING_JOBS[group]
    columns = ", ".join(screening.columns.astype(str)) if len(screening.columns) else "(none)"
    raise ValueError(
        f"{path} has no usable pair_id rows for group {group}.\n"
        f"Loaded screening rows: {len(screening)}; columns: {columns}\n\n"
        f"Please generate the screening file first, for example:\n"
        f"  export DASHSCOPE_API_KEY=\"your_api_key\"\n"
        f"  python sampling/run_ai_sampling.py --job {job} --append\n\n"
        f"If you intentionally want to rebuild from scratch, remove the stale file first "
        f"or run without --append."
    )


def main():
    all_selected = []

    for group, cfg in FILES.items():
        print(f"\nProcessing group: {group}")

        candidates = pd.read_csv(cfg["candidates"])
        screening = load_jsonl(cfg["screening"])

        if "pair_id" not in candidates.columns:
            raise ValueError(f"{cfg['candidates']} missing pair_id")

        require_pair_id_screening(group, cfg["screening"], screening)

        merged = candidates.merge(
            screening,
            on="pair_id",
            how="inner",
            suffixes=("", "_screening"),
        )

        # 基础过滤：推荐进入人工标注池
        if "recommend_for_annotation" in merged.columns:
            merged = merged[merged["recommend_for_annotation"] == True]

        # 过滤泄漏风险
        if "leakage_risk" in merged.columns:
            merged = merged[merged["leakage_risk"].isin(["none", "low"])]

        # 优先保留不需要人工复核的样本
        if "needs_manual_review" in merged.columns:
            preferred = merged[merged["needs_manual_review"] == False]
            backup = merged[merged["needs_manual_review"] == True]
        else:
            preferred = merged
            backup = merged.iloc[0:0]

        target_n = TARGET_COUNTS[group]

        if len(preferred) >= target_n:
            selected = preferred.sample(n=target_n, random_state=RANDOM_SEED)
        else:
            need = target_n - len(preferred)
            backup_selected = backup.sample(
                n=min(need, len(backup)),
                random_state=RANDOM_SEED,
            )
            selected = pd.concat([preferred, backup_selected], ignore_index=True)

        print(f"Selected {len(selected)} / target {target_n}")

        selected["final_sampling_group"] = group
        all_selected.append(selected)

    final_df = pd.concat(all_selected, ignore_index=True)

    # 打乱顺序，避免标注者看出样本类别
    final_df = final_df.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)

    # 重新生成盲标 ID，隐藏原始类别信息
    final_df["annotation_id"] = [
        f"ANN_{i:05d}" for i in range(1, len(final_df) + 1)
    ]

    # 给人工标注者看的 blind 表
    blind_cols = [
        "annotation_id",
        "object_a_profile",
        "object_b_profile",
    ]

    blind_df = final_df[blind_cols].copy()
    for col in ["object_a_profile", "object_b_profile"]:
        blind_df[col] = blind_df[col].apply(clean_profile_text)

    # 人工标注空列
    blind_df["has_opportunity"] = ""
    blind_df["opportunity_score"] = ""
    blind_df["cooperation_type"] = ""
    blind_df["role_direction"] = ""
    blind_df["confidence"] = ""

    blind_df.to_csv(
        BASE_DIR / "annotation_pairs_blind.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # 自己保留的 meta 表，不给标注者
    meta_cols = [
        "annotation_id",
        "pair_id",
        "object_a_name",
        "object_b_name",
        "industry_a",
        "industry_b",
        "final_sampling_group",
        "source",
        "sampling_group",
        "ai_score",
        "tag_similarity_score",
        "complementarity_score",
        "shared_tags",
        "recommend_for_annotation",
        "difficulty",
        "selection_reason",
        "diversity_tags",
        "data_quality_flags",
        "leakage_risk",
        "needs_manual_review",
    ]

    meta_cols = [c for c in meta_cols if c in final_df.columns]

    meta_df = final_df[meta_cols].copy()
    meta_df.to_csv(
        BASE_DIR / "annotation_pairs_meta.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print("\nDone.")
    print(f"annotation_pairs_blind.csv rows: {len(blind_df)}")
    print(f"annotation_pairs_meta.csv rows: {len(meta_df)}")


if __name__ == "__main__":
    main()
