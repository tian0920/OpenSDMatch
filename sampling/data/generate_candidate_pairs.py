"""
Generate four candidate-pair pools for human blind annotation in OpenSDMatch-style benchmark construction.

Inputs expected in the same directory:
- company_sd_profiles.csv
- cooperation_edges.csv

Outputs:
- high_score_ai_candidates.csv
- mid_low_score_ai_candidates.csv
- hard_negative_candidates.csv
- random_negative_candidates.csv
- candidate_sampling_summary.csv

Notes:
- This script uses AI/system-generated cooperation edges only as candidate sources, not as gold labels.
- It excludes leakage fields such as reason, action_plan, raw_json from outputs.
- It optionally filters out sensitive defense/military-related companies for safer public benchmark use.
"""

from __future__ import annotations

import itertools
import random
import re
from pathlib import Path
from typing import Iterable, Set

import pandas as pd

RANDOM_SEED = 20260607
random.seed(RANDOM_SEED)

BASE_DIR = Path(__file__).resolve().parent
COMPANY_FILE = BASE_DIR / "company_sd_profiles.csv"
EDGE_FILE = BASE_DIR / "cooperation_edges.csv"

# Target candidate-pool sizes before AI-assisted screening.
N_HIGH_AI = 3000
N_MID_LOW_AI = 3000
N_HARD_NEG = 3000
N_RANDOM_NEG = 3000

# Score bands can be adjusted after checking score distribution.
HIGH_SCORE_MIN = 90
MID_LOW_SCORE_MIN = 60
MID_LOW_SCORE_MAX_EXCLUSIVE = 75

# Optional safety filter for public benchmark construction.
EXCLUDE_SENSITIVE_DEFENSE = True
SENSITIVE_PATTERNS = re.compile(r"国防|军事|军工|军用|武器|弹药|导弹|雷达|部队|解放军|集团军|战术|防务")


def clean_text(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def split_tags(x) -> list[str]:
    text = clean_text(x)
    if not text:
        return []
    # Supports Chinese/English punctuation and separators.
    parts = re.split(r"[;,，、；|/\n]+", text)
    return [p.strip() for p in parts if p and p.strip()]


def tag_set(*cols: str) -> Set[str]:
    out: Set[str] = set()
    for c in cols:
        out.update(split_tags(c))
    return {t for t in out if t}


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def profile_text(row: pd.Series) -> str:
    # Keep concise fields suitable for model screening and later human annotation.
    fields = [
        ("公司名称", row.get("company_name", "")),
        ("行业", row.get("industry", "")),
        ("主营业务", row.get("main_business", "")),
        ("产品/服务", row.get("products", "")),
        ("供给词", row.get("supply_words", "")),
        ("需求词", row.get("demand_words", "")),
        ("摘要", row.get("summary_text", "")),
    ]
    chunks = []
    for k, v in fields:
        v = clean_text(v)
        if v:
            # Limit very long fields to keep prompts short.
            if len(v) > 300:
                v = v[:300] + "…"
            chunks.append(f"{k}：{v}")
    return "\n".join(chunks)


def is_sensitive(row: pd.Series) -> bool:
    text = " ".join(clean_text(row.get(c, "")) for c in [
        "company_name", "industry", "main_business", "products", "supply_words", "demand_words", "summary_text"
    ])
    return bool(SENSITIVE_PATTERNS.search(text))


def make_pair_record(pair_id: str, a_name: str, b_name: str, comp: pd.DataFrame, **extra) -> dict:
    a = comp.loc[a_name]
    b = comp.loc[b_name]
    a_supply = tag_set(a.get("supply_words", ""))
    a_demand = tag_set(a.get("demand_words", ""))
    b_supply = tag_set(b.get("supply_words", ""))
    b_demand = tag_set(b.get("demand_words", ""))
    a_all = a_supply | a_demand
    b_all = b_supply | b_demand
    rec = {
        "pair_id": pair_id,
        "object_a_name": a_name,
        "object_b_name": b_name,
        "industry_a": clean_text(a.get("industry", "")),
        "industry_b": clean_text(b.get("industry", "")),
        "object_a_profile": profile_text(a),
        "object_b_profile": profile_text(b),
        "tag_similarity_score": round(jaccard(a_all, b_all), 4),
        "complementarity_score": round((jaccard(a_demand, b_supply) + jaccard(b_demand, a_supply)) / 2, 4),
        "shared_tags": "；".join(sorted(a_all & b_all)),
    }
    rec.update(extra)
    return rec


def ordered_pair(a: str, b: str) -> tuple[str, str]:
    return (a, b)


def unordered_pair(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted([a, b]))


def sample_or_all(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if len(df) <= n:
        return df.copy()
    return df.sample(n=n, random_state=RANDOM_SEED)


def main():
    # Load company profiles.
    comp = pd.read_csv(COMPANY_FILE, low_memory=False)
    comp = comp.drop_duplicates(subset=["company_name"]).copy()
    comp["company_name"] = comp["company_name"].astype(str).str.strip()
    comp = comp[comp["company_name"].ne("")]

    # Keep companies with at least minimal profile info.
    profile_cols = ["industry", "main_business", "products", "supply_words", "demand_words", "summary_text"]
    comp["profile_len"] = comp[profile_cols].fillna("").astype(str).agg(" ".join, axis=1).str.len()
    comp = comp[comp["profile_len"] >= 20].copy()

    if EXCLUDE_SENSITIVE_DEFENSE:
        comp["is_sensitive"] = comp.apply(is_sensitive, axis=1)
        comp = comp[~comp["is_sensitive"]].copy()

    comp = comp.set_index("company_name", drop=False)
    valid_names = set(comp.index)

    # Load edges with non-leaky columns only.
    edges = pd.read_csv(
        EDGE_FILE,
        usecols=["edge_type", "source_id", "target_id", "source_name", "target_name", "score"],
        low_memory=False,
    )
    edges = edges[edges["edge_type"].eq("company_supply_chain_match")].copy()
    edges["source_id"] = edges["source_id"].astype(str).str.strip()
    edges["target_id"] = edges["target_id"].astype(str).str.strip()
    edges = edges[edges["source_id"].isin(valid_names) & edges["target_id"].isin(valid_names)]
    edges = edges[edges["source_id"].ne(edges["target_id"])]

    existing_ordered = set(zip(edges["source_id"], edges["target_id"]))
    existing_unordered = {unordered_pair(a, b) for a, b in existing_ordered}

    # 1) High-score AI candidate edges.
    high_edges = edges[edges["score"] >= HIGH_SCORE_MIN].copy()
    high_edges = sample_or_all(high_edges, N_HIGH_AI)
    high_records = []
    for i, r in enumerate(high_edges.itertuples(index=False), start=1):
        high_records.append(make_pair_record(
            f"HSAI_{i:05d}", r.source_id, r.target_id, comp,
            source="ai_edge", sampling_group="high_score_ai_edge", ai_score=int(r.score),
            source_id=r.source_id, target_id=r.target_id,
        ))
    pd.DataFrame(high_records).to_csv(BASE_DIR / "high_score_ai_candidates.csv", index=False, encoding="utf-8-sig")

    # 2) Mid/low-score AI candidate edges.
    mid_edges = edges[(edges["score"] >= MID_LOW_SCORE_MIN) & (edges["score"] < MID_LOW_SCORE_MAX_EXCLUSIVE)].copy()
    mid_edges = sample_or_all(mid_edges, N_MID_LOW_AI)
    mid_records = []
    for i, r in enumerate(mid_edges.itertuples(index=False), start=1):
        mid_records.append(make_pair_record(
            f"MLAI_{i:05d}", r.source_id, r.target_id, comp,
            source="ai_edge", sampling_group="mid_low_score_ai_edge", ai_score=int(r.score),
            source_id=r.source_id, target_id=r.target_id,
        ))
    pd.DataFrame(mid_records).to_csv(BASE_DIR / "mid_low_score_ai_candidates.csv", index=False, encoding="utf-8-sig")

    # Precompute tag sets for negative sampling.
    names = list(comp.index)
    all_tags = {}
    supply_tags = {}
    demand_tags = {}
    for name, row in comp.iterrows():
        supply_tags[name] = tag_set(row.get("supply_words", ""))
        demand_tags[name] = tag_set(row.get("demand_words", ""))
        all_tags[name] = supply_tags[name] | demand_tags[name]

    # 3) Same-industry hard negatives.
    hard_pool = []
    grouped = comp.reset_index(drop=True).groupby("industry", dropna=True)
    industries = list(grouped.groups.keys())
    random.shuffle(industries)
    for industry in industries:
        g = grouped.get_group(industry)
        group_names = [n for n in g["company_name"].tolist() if n in valid_names]
        if len(group_names) < 2:
            continue
        # Sample pair attempts per industry; cap large industries.
        max_attempts = min(600, len(group_names) * 8)
        for _ in range(max_attempts):
            a, b = random.sample(group_names, 2)
            if unordered_pair(a, b) in existing_unordered:
                continue
            sim = jaccard(all_tags[a], all_tags[b])
            comp_score = (jaccard(demand_tags[a], supply_tags[b]) + jaccard(demand_tags[b], supply_tags[a])) / 2
            shared = all_tags[a] & all_tags[b]
            # Hard: same industry or tag-similar, but low direct complementarity.
            if sim >= 0.03 and comp_score <= 0.12:
                hard_pool.append((a, b, sim, comp_score))
            if len(hard_pool) >= N_HARD_NEG * 4:
                break
        if len(hard_pool) >= N_HARD_NEG * 4:
            break

    # If not enough, relax overlap condition while keeping same industry/non-edge.
    if len(hard_pool) < N_HARD_NEG:
        for industry in industries:
            g = grouped.get_group(industry)
            group_names = [n for n in g["company_name"].tolist() if n in valid_names]
            if len(group_names) < 2:
                continue
            for _ in range(min(500, len(group_names) * 5)):
                a, b = random.sample(group_names, 2)
                if unordered_pair(a, b) in existing_unordered:
                    continue
                comp_score = (jaccard(demand_tags[a], supply_tags[b]) + jaccard(demand_tags[b], supply_tags[a])) / 2
                if comp_score <= 0.08:
                    hard_pool.append((a, b, jaccard(all_tags[a], all_tags[b]), comp_score))
                if len(hard_pool) >= N_HARD_NEG * 2:
                    break
            if len(hard_pool) >= N_HARD_NEG * 2:
                break

    # Deduplicate hard pool.
    seen = set()
    hard_unique = []
    for a, b, sim, cs in hard_pool:
        key = unordered_pair(a, b)
        if key not in seen:
            seen.add(key)
            hard_unique.append((a, b, sim, cs))
    random.shuffle(hard_unique)
    hard_unique = hard_unique[:N_HARD_NEG]

    hard_records = []
    for i, (a, b, sim, cs) in enumerate(hard_unique, start=1):
        hard_records.append(make_pair_record(
            f"HNEG_{i:05d}", a, b, comp,
            source="programmatic_non_edge", sampling_group="same_industry_hard_negative",
            same_industry=True, existing_edge=False,
        ))
    pd.DataFrame(hard_records).to_csv(BASE_DIR / "hard_negative_candidates.csv", index=False, encoding="utf-8-sig")

    # 4) Random negatives.
    random_records = []
    seen_random = set()
    attempts = 0
    while len(random_records) < N_RANDOM_NEG and attempts < N_RANDOM_NEG * 100:
        attempts += 1
        a, b = random.sample(names, 2)
        key = unordered_pair(a, b)
        if key in seen_random or key in existing_unordered:
            continue
        seen_random.add(key)
        same_ind = clean_text(comp.loc[a, "industry"]) == clean_text(comp.loc[b, "industry"])
        random_records.append(make_pair_record(
            f"RNEG_{len(random_records)+1:05d}", a, b, comp,
            source="programmatic_non_edge", sampling_group="random_negative",
            same_industry=same_ind, existing_edge=False,
        ))
    pd.DataFrame(random_records).to_csv(BASE_DIR / "random_negative_candidates.csv", index=False, encoding="utf-8-sig")

    # Summary.
    summary = []
    for fname, group in [
        ("high_score_ai_candidates.csv", "high_score_ai_edge"),
        ("mid_low_score_ai_candidates.csv", "mid_low_score_ai_edge"),
        ("hard_negative_candidates.csv", "same_industry_hard_negative"),
        ("random_negative_candidates.csv", "random_negative"),
    ]:
        df = pd.read_csv(BASE_DIR / fname)
        summary.append({
            "file": fname,
            "sampling_group": group,
            "rows": len(df),
            "unique_industry_a": df["industry_a"].nunique(dropna=True),
            "unique_industry_b": df["industry_b"].nunique(dropna=True),
            "mean_tag_similarity": round(df["tag_similarity_score"].mean(), 4) if len(df) else None,
            "mean_complementarity": round(df["complementarity_score"].mean(), 4) if len(df) else None,
        })
    pd.DataFrame(summary).to_csv(BASE_DIR / "candidate_sampling_summary.csv", index=False, encoding="utf-8-sig")
    print(pd.DataFrame(summary).to_string(index=False))


if __name__ == "__main__":
    main()
