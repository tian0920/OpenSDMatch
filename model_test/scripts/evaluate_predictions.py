#!/usr/bin/env python3
"""Evaluate supply-demand matching predictions against gold labels."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_GOLD_CSV = ROOT / "model_test" / "gold" / "annotation_pairs_test.csv"
DEFAULT_EVAL_DIR = ROOT / "model_test" / "eval_results"
DEFAULT_PREDICTIONS_DIR = ROOT / "model_test" / "model_outputs"

# 默认自动评估 model_outputs 下所有 *.compact.jsonl。
# 如需在源码中固定一批文件名，可在这里填写；命令行的
# --prediction-file-names 会优先于这个列表。
PREDICTION_FILE_NAMES: list[str] = []

OPPORTUNITY_LABELS = ["No", "Yes"]
SCORE_LABELS = [1, 2]
DIRECTION_LABELS = ["A_to_B", "B_to_A", "Bidirectional", "Unclear"]
TYPE_LABELS = [
    "供应与生产合作",
    "营销与分销合作",
    "许可与技术转移合作",
    "研发与共同开发合作",
    "资本与股权合作",
    "其他",
    "None",
]

LABEL_COLUMNS = ["has_opportunity", "opportunity_score", "cooperation_type", "role_direction", "confidence"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-csv", type=Path, default=DEFAULT_GOLD_CSV)
    parser.add_argument("--gold-encoding", default="utf-8-sig")
    parser.add_argument(
        "--predictions",
        type=Path,
        default=None,
        help=(
            "Single prediction file to evaluate. "
            "If omitted, batch mode evaluates --prediction-file-names, "
            "PREDICTION_FILE_NAMES, or all *.compact.jsonl files in model_outputs."
        ),
    )
    parser.add_argument(
        "--prediction-file-names",
        nargs="*",
        default=None,
        help=(
            "Prediction file names under model_outputs to evaluate in batch mode. "
            "If omitted and PREDICTION_FILE_NAMES is empty, all *.compact.jsonl files "
            "under model_outputs are discovered automatically."
        ),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help=(
            "Output JSON path. Only recommended when evaluating one file with --predictions. "
            "When batch evaluating, default per-file output paths are used."
        ),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help=(
            "Output Markdown path. Only recommended when evaluating one file with --predictions. "
            "When batch evaluating, default per-file output paths are used."
        ),
    )
    parser.add_argument(
        "--high-confidence-threshold",
        type=int,
        default=2,
        help="Predicted confidence threshold for high-confidence error rate.",
    )
    parser.add_argument(
        "--reliability-target",
        choices=["match", "joint"],
        default="match",
        help="Correctness target for confidence-accuracy curve.",
    )
    return parser.parse_args()


def default_output_path(predictions_path: Path, suffix: str) -> Path:
    stem = predictions_path.stem
    if stem.endswith(".compact"):
        stem = stem[: -len(".compact")]
    return DEFAULT_EVAL_DIR / f"{stem}.metrics.{suffix}"


def get_prediction_paths(args: argparse.Namespace) -> list[Path]:
    if args.predictions is not None:
        return [args.predictions]

    if args.prediction_file_names is not None:
        return [
            DEFAULT_PREDICTIONS_DIR / file_name
            for file_name in args.prediction_file_names
        ]

    if PREDICTION_FILE_NAMES:
        return [
            DEFAULT_PREDICTIONS_DIR / file_name
            for file_name in PREDICTION_FILE_NAMES
        ]

    return [
        path
        for path in sorted(DEFAULT_PREDICTIONS_DIR.glob("*.compact.jsonl"))
    ]


def resolve_output_paths(
    args: argparse.Namespace,
    predictions_path: Path,
    batch_mode: bool,
) -> tuple[Path, Path]:
    if batch_mode:
        # 批量模式下强制使用每个预测文件自己的默认输出路径，避免互相覆盖。
        return (
            default_output_path(predictions_path, "json"),
            default_output_path(predictions_path, "md"),
        )

    output_json = args.output_json or default_output_path(predictions_path, "json")
    output_md = args.output_md or default_output_path(predictions_path, "md")
    return output_json, output_md


def normalize_has_opportunity(value: Any) -> str:
    value = str(value or "").strip()
    mapping = {
        "0": "No",
        "1": "Yes",
        "2": "Yes",
        "false": "No",
        "true": "Yes",
        "False": "No",
        "True": "Yes",
        "否": "No",
        "是": "Yes",
    }
    return mapping.get(value, value)


def normalize_role_direction(value: Any) -> str:
    value = str(value or "").strip()
    mapping = {
        "A supplies B": "A_to_B",
        "A_supplies_B": "A_to_B",
        "B supplies A": "B_to_A",
        "B_supplies_A": "B_to_A",
        "Unclear / Not applicable": "None",
        "Not applicable": "None",
        "N/A": "None",
        "None": "None",
        "": "None",
    }
    return mapping.get(value, value)


def normalize_type(value: Any) -> str:
    value = str(value or "").strip()
    mapping = {
        "采购/销售": "供应与生产合作",
        "技术服务": "供应与生产合作",
        "渠道合作": "营销与分销合作",
        "联合研发": "研发与共同开发合作",
        "投融资": "资本与股权合作",
        "不匹配": "None",
        "不适用": "None",
    }
    if value in {"", "None", "N/A", "Not applicable"}:
        return "None"
    if value == "资源对接":
        return "其他"
    if value == "招商合作":
        return "营销与分销合作"
    if value == "许可与技术转移合作":
        return value
    return mapping.get(value, value)


def has_new_labels(row: dict[str, Any]) -> bool:
    return bool(str(row.get("has_opportunity") or "").strip())


def has_old_labels(row: dict[str, Any]) -> bool:
    return bool(str(row.get("label_match") or "").strip())


def normalize_record_labels(row: dict[str, Any]) -> dict[str, Any]:
    if has_new_labels(row):
        has_opportunity = normalize_has_opportunity(row.get("has_opportunity"))
        opportunity_score = to_int(row.get("opportunity_score"))
        cooperation_type = normalize_type(
            row.get("cooperation_type_normalized", row.get("cooperation_type"))
        )
        role_direction = normalize_role_direction(
            row.get("role_direction_normalized", row.get("role_direction"))
        )
        confidence = to_int(row.get("confidence"))
    elif has_old_labels(row):
        label_match = to_int(row.get("label_match"))
        has_opportunity = "No" if label_match == 0 else "Yes"
        opportunity_score = None if label_match == 0 else label_match
        cooperation_type = normalize_type(
            row.get("label_cooperation_type_normalized", row.get("label_cooperation_type"))
        )
        role_direction = normalize_role_direction(
            row.get("label_direction_normalized", row.get("label_direction"))
        )
        confidence = to_int(row.get("label_confidence"))
    else:
        has_opportunity = ""
        opportunity_score = None
        cooperation_type = "None"
        role_direction = "None"
        confidence = None

    if has_opportunity == "No":
        opportunity_score = None
        cooperation_type = "None"
        role_direction = "None"
    return {
        "has_opportunity": has_opportunity,
        "opportunity_score": opportunity_score,
        "cooperation_type": cooperation_type,
        "role_direction": role_direction,
        "confidence": confidence,
    }


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def normalize_gold(row: dict[str, Any]) -> dict[str, Any]:
    return normalize_record_labels(row)


def normalize_prediction(prediction: dict[str, Any] | None) -> dict[str, Any]:
    labels = normalize_record_labels(prediction or {})
    labels["reason"] = (prediction or {}).get("reason") or (prediction or {}).get("label_reason")
    return labels


def load_gold(path: Path, encoding: str) -> dict[str, dict[str, Any]]:
    with path.open(newline="", encoding=encoding) as handle:
        rows = list(csv.DictReader(handle))
    return {
        row["annotation_id"]: normalize_gold(row)
        for row in rows
        if row.get("annotation_id") and (has_new_labels(row) or has_old_labels(row))
    }


def load_predictions(path: Path) -> dict[str, dict[str, Any]]:
    predictions: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            annotation_id = record.get("annotation_id")
            if not annotation_id:
                raise ValueError(f"{path}:{line_number} missing annotation_id")
            predictions[annotation_id] = record
    return predictions


def safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def precision_recall_f1(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = safe_divide(tp, tp + fp)
    recall = safe_divide(tp, tp + fn)
    f1 = safe_divide(2 * precision * recall, precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def per_class_stats(y_true: list[Any], y_pred: list[Any], labels: list[Any]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for label in labels:
        tp = sum(true == label and pred == label for true, pred in zip(y_true, y_pred))
        fp = sum(true != label and pred == label for true, pred in zip(y_true, y_pred))
        fn = sum(true == label and pred != label for true, pred in zip(y_true, y_pred))
        support = sum(true == label for true in y_true)
        metrics = precision_recall_f1(tp, fp, fn)
        stats[str(label)] = {**metrics, "support": support, "tp": tp, "fp": fp, "fn": fn}
    return stats


def macro_f1(y_true: list[Any], y_pred: list[Any], labels: list[Any]) -> float:
    stats = per_class_stats(y_true, y_pred, labels)
    return safe_divide(sum(item["f1"] for item in stats.values()), len(labels))


def confusion_matrix(y_true: list[Any], y_pred: list[Any], labels: list[Any]) -> dict[str, Any]:
    counts = Counter(zip(y_true, y_pred))
    return {
        "labels": labels,
        "rows_gold_cols_pred": [
            [counts[(gold_label, pred_label)] for pred_label in labels] for gold_label in labels
        ],
    }


def quadratic_weighted_kappa(y_true: list[int], y_pred: list[int], labels: list[int]) -> float:
    if not y_true:
        return 0.0

    label_to_index = {label: index for index, label in enumerate(labels)}
    n = len(labels)
    observed = [[0.0 for _ in labels] for _ in labels]
    true_hist = [0.0 for _ in labels]
    pred_hist = [0.0 for _ in labels]

    for true, pred in zip(y_true, y_pred):
        if true not in label_to_index or pred not in label_to_index:
            continue
        i = label_to_index[true]
        j = label_to_index[pred]
        observed[i][j] += 1
        true_hist[i] += 1
        pred_hist[j] += 1

    total = sum(true_hist)
    if total == 0:
        return 0.0

    weighted_observed = 0.0
    weighted_expected = 0.0
    max_distance_squared = (n - 1) ** 2

    for i in range(n):
        for j in range(n):
            weight = ((i - j) ** 2) / max_distance_squared if max_distance_squared else 0.0
            expected = true_hist[i] * pred_hist[j] / total
            weighted_observed += weight * observed[i][j]
            weighted_expected += weight * expected

    return 1.0 - safe_divide(weighted_observed, weighted_expected)


def matthews_corrcoef_binary(y_true: list[int], y_pred: list[int]) -> float:
    tp = sum(true == 1 and pred == 1 for true, pred in zip(y_true, y_pred))
    tn = sum(true == 0 and pred == 0 for true, pred in zip(y_true, y_pred))
    fp = sum(true == 0 and pred == 1 for true, pred in zip(y_true, y_pred))
    fn = sum(true == 1 and pred == 0 for true, pred in zip(y_true, y_pred))
    denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return safe_divide((tp * tn) - (fp * fn), denominator)


def binary_metrics(y_true: list[int], y_pred: list[int]) -> dict[str, Any]:
    tp = sum(true == 1 and pred == 1 for true, pred in zip(y_true, y_pred))
    tn = sum(true == 0 and pred == 0 for true, pred in zip(y_true, y_pred))
    fp = sum(true == 0 and pred == 1 for true, pred in zip(y_true, y_pred))
    fn = sum(true == 1 and pred == 0 for true, pred in zip(y_true, y_pred))
    metrics = precision_recall_f1(tp, fp, fn)
    return {
        **metrics,
        "mcc": matthews_corrcoef_binary(y_true, y_pred),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def accuracy(y_true: list[Any], y_pred: list[Any]) -> float:
    return safe_divide(sum(true == pred for true, pred in zip(y_true, y_pred)), len(y_true))


def confidence_accuracy_curve(rows: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
    curve = []
    for confidence in range(1, 3):
        bucket = [row for row in rows if row["pred"]["confidence"] == confidence]
        if target == "joint":
            correct = sum(row["joint_correct"] for row in bucket)
        else:
            correct = sum(row["gold"]["has_opportunity"] == row["pred"]["has_opportunity"] for row in bucket)
        curve.append(
            {
                "confidence": confidence,
                "n": len(bucket),
                "accuracy": safe_divide(correct, len(bucket)),
                "errors": len(bucket) - correct,
            }
        )
    return curve


def evaluate(
    gold_by_id: dict[str, dict[str, Any]],
    prediction_records: dict[str, dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    rows = []
    missing_predictions = []
    invalid_predictions = []

    for annotation_id, gold in gold_by_id.items():
        record = prediction_records.get(annotation_id)
        if not record:
            missing_predictions.append(annotation_id)
            continue

        pred = normalize_prediction(record.get("prediction"))
        if pred["has_opportunity"] not in OPPORTUNITY_LABELS:
            invalid_predictions.append(annotation_id)
            continue

        joint_correct = (
            gold["has_opportunity"] == pred["has_opportunity"]
            and gold["opportunity_score"] == pred["opportunity_score"]
            and gold["role_direction"] == pred["role_direction"]
            and gold["cooperation_type"] == pred["cooperation_type"]
        )
        rows.append(
            {
                "annotation_id": annotation_id,
                "gold": gold,
                "pred": pred,
                "joint_correct": joint_correct,
            }
        )

    y_opportunity_true = [row["gold"]["has_opportunity"] for row in rows]
    y_opportunity_pred = [row["pred"]["has_opportunity"] for row in rows]
    y_binary_true = [1 if value == "Yes" else 0 for value in y_opportunity_true]
    y_binary_pred = [1 if value == "Yes" else 0 for value in y_opportunity_pred]

    positive_rows = [row for row in rows if row["gold"]["has_opportunity"] == "Yes"]
    y_score_true = [row["gold"]["opportunity_score"] for row in positive_rows]
    y_score_pred = [row["pred"]["opportunity_score"] for row in positive_rows]
    y_direction_true = [row["gold"]["role_direction"] for row in positive_rows]
    y_direction_pred = [row["pred"]["role_direction"] for row in positive_rows]
    y_type_true = [row["gold"]["cooperation_type"] for row in positive_rows]
    y_type_pred = [row["pred"]["cooperation_type"] for row in positive_rows]

    high_conf_rows = [
        row for row in rows if (row["pred"]["confidence"] or 0) >= args.high_confidence_threshold
    ]
    high_conf_opportunity_errors = sum(
        row["gold"]["has_opportunity"] != row["pred"]["has_opportunity"] for row in high_conf_rows
    )
    high_conf_joint_errors = sum(not row["joint_correct"] for row in high_conf_rows)

    return {
        "metadata": {
            "gold_csv": str(args.gold_csv),
            "predictions": str(args.predictions),
            "gold_rows": len(gold_by_id),
            "prediction_rows": len(prediction_records),
            "evaluated_rows": len(rows),
            "missing_predictions": missing_predictions,
            "invalid_predictions": invalid_predictions,
        },
        "task_1_opportunity_detection": {
            "macro_f1": macro_f1(y_opportunity_true, y_opportunity_pred, OPPORTUNITY_LABELS),
            "confusion_matrix": confusion_matrix(y_opportunity_true, y_opportunity_pred, OPPORTUNITY_LABELS),
            "per_class": per_class_stats(y_opportunity_true, y_opportunity_pred, OPPORTUNITY_LABELS),
        },
        "task_2_binary_opportunity_detection": binary_metrics(y_binary_true, y_binary_pred),
        "task_3_opportunity_score": {
            "condition": "gold has_opportunity == Yes",
            "support": len(positive_rows),
            "conditional_score_accuracy": accuracy(y_score_true, y_score_pred),
            "score_macro_f1": macro_f1(y_score_true, y_score_pred, SCORE_LABELS),
            "per_class": per_class_stats(y_score_true, y_score_pred, SCORE_LABELS),
        },
        "task_4_role_direction": {
            "condition": "gold has_opportunity == Yes",
            "support": len(positive_rows),
            "conditional_direction_accuracy": accuracy(y_direction_true, y_direction_pred),
            "direction_macro_f1": macro_f1(y_direction_true, y_direction_pred, DIRECTION_LABELS),
            "per_class": per_class_stats(y_direction_true, y_direction_pred, DIRECTION_LABELS),
        },
        "task_5_cooperation_type": {
            "condition": "gold has_opportunity == Yes",
            "support": len(positive_rows),
            "conditional_type_macro_f1": macro_f1(y_type_true, y_type_pred, TYPE_LABELS),
            "per_class_f1": {
                label: stats["f1"]
                for label, stats in per_class_stats(y_type_true, y_type_pred, TYPE_LABELS).items()
            },
            "per_class": per_class_stats(y_type_true, y_type_pred, TYPE_LABELS),
        },
        "task_6_joint_prediction": {
            "opportunity_score_direction_type_exact_match": safe_divide(
                sum(row["joint_correct"] for row in rows),
                len(rows),
            ),
            "opportunity_score_direction_type_exact_match_on_gold_positive": safe_divide(
                sum(row["joint_correct"] for row in positive_rows),
                len(positive_rows),
            ),
        },
        "task_7_reliability": {
            "confidence_accuracy_target": args.reliability_target,
            "confidence_accuracy_curve": confidence_accuracy_curve(rows, args.reliability_target),
            "high_confidence_threshold": args.high_confidence_threshold,
            "high_confidence_count": len(high_conf_rows),
            "high_confidence_opportunity_error_rate": safe_divide(
                high_conf_opportunity_errors,
                len(high_conf_rows),
            ),
            "high_confidence_joint_error_rate": safe_divide(
                high_conf_joint_errors,
                len(high_conf_rows),
            ),
        },
    }


def fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def matrix_to_markdown(matrix: dict[str, Any]) -> str:
    labels = matrix["labels"]
    rows = matrix["rows_gold_cols_pred"]
    lines = ["| gold \\ pred | " + " | ".join(map(str, labels)) + " |"]
    lines.append("|---|" + "|".join(["---"] * len(labels)) + "|")
    for label, values in zip(labels, rows):
        lines.append("| " + str(label) + " | " + " | ".join(map(str, values)) + " |")
    return "\n".join(lines)


def render_markdown(results: dict[str, Any]) -> str:
    t1 = results["task_1_opportunity_detection"]
    t2 = results["task_2_binary_opportunity_detection"]
    t3 = results["task_3_opportunity_score"]
    t4 = results["task_4_role_direction"]
    t5 = results["task_5_cooperation_type"]
    t6 = results["task_6_joint_prediction"]
    t7 = results["task_7_reliability"]

    lines = [
        "# Prediction Evaluation",
        "",
        "## Metadata",
        f"- Gold rows: {results['metadata']['gold_rows']}",
        f"- Prediction rows: {results['metadata']['prediction_rows']}",
        f"- Evaluated rows: {results['metadata']['evaluated_rows']}",
        f"- Missing predictions: {len(results['metadata']['missing_predictions'])}",
        f"- Invalid predictions: {len(results['metadata']['invalid_predictions'])}",
        "",
        "## Task 1 Opportunity Detection",
        f"- Macro-F1: {fmt(t1['macro_f1'])}",
        "",
        matrix_to_markdown(t1["confusion_matrix"]),
        "",
        "## Task 2 Binary Opportunity Detection",
        f"- F1: {fmt(t2['f1'])}",
        f"- MCC: {fmt(t2['mcc'])}",
        f"- Precision: {fmt(t2['precision'])}",
        f"- Recall: {fmt(t2['recall'])}",
        f"- TP/TN/FP/FN: {t2['tp']}/{t2['tn']}/{t2['fp']}/{t2['fn']}",
        "",
        "## Task 3 Opportunity Score",
        f"- Condition: {t3['condition']}",
        f"- Support: {t3['support']}",
        f"- Conditional Score Accuracy: {fmt(t3['conditional_score_accuracy'])}",
        f"- Score Macro-F1: {fmt(t3['score_macro_f1'])}",
        "",
        "## Task 4 Role Direction",
        f"- Condition: {t4['condition']}",
        f"- Support: {t4['support']}",
        f"- Conditional Direction Accuracy: {fmt(t4['conditional_direction_accuracy'])}",
        f"- Direction Macro-F1: {fmt(t4['direction_macro_f1'])}",
        "",
        "## Task 5 Cooperation Type",
        f"- Condition: {t5['condition']}",
        f"- Support: {t5['support']}",
        f"- Conditional Type Macro-F1: {fmt(t5['conditional_type_macro_f1'])}",
        "",
        "| class | F1 |",
        "|---|---:|",
    ]

    for label, f1 in t5["per_class_f1"].items():
        lines.append(f"| {label} | {fmt(f1)} |")

    lines.extend(
        [
            "",
            "## Task 6 Joint Prediction",
            f"- Opportunity + Score + Direction + Type Exact Match: {fmt(t6['opportunity_score_direction_type_exact_match'])}",
            f"- Exact Match on Gold Positive: {fmt(t6['opportunity_score_direction_type_exact_match_on_gold_positive'])}",
            "",
            "## Task 7 Reliability",
            f"- Confidence-Accuracy Target: {t7['confidence_accuracy_target']}",
            f"- High-confidence Threshold: >= {t7['high_confidence_threshold']}",
            f"- High-confidence Count: {t7['high_confidence_count']}",
            f"- High-confidence Opportunity Error Rate: {fmt(t7['high_confidence_opportunity_error_rate'])}",
            f"- High-confidence Joint Error Rate: {fmt(t7['high_confidence_joint_error_rate'])}",
            "",
            "| confidence | n | accuracy | errors |",
            "|---:|---:|---:|---:|",
        ]
    )

    for bucket in t7["confidence_accuracy_curve"]:
        lines.append(
            f"| {bucket['confidence']} | {bucket['n']} | {fmt(bucket['accuracy'])} | {bucket['errors']} |"
        )

    lines.append("")
    return "\n".join(lines)


def evaluate_one_file(
    predictions_path: Path,
    gold_by_id: dict[str, dict[str, Any]],
    args: argparse.Namespace,
    output_json: Path,
    output_md: Path,
) -> dict[str, Any]:
    args.predictions = predictions_path

    prediction_records = load_predictions(predictions_path)
    results = evaluate(gold_by_id, prediction_records, args)
    markdown = render_markdown(results)

    print(f"\n\n===== Evaluating {predictions_path.name} =====\n")
    print(markdown)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote JSON metrics to {output_json}")

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown, encoding="utf-8")
    print(f"Wrote Markdown metrics to {output_md}")

    return results


def main() -> int:
    args = parse_args()

    prediction_paths = get_prediction_paths(args)
    if not prediction_paths:
        raise ValueError(
            f"No *.compact.jsonl prediction files found in {DEFAULT_PREDICTIONS_DIR}."
        )

    batch_mode = args.predictions is None

    if batch_mode and (args.output_json is not None or args.output_md is not None):
        print(
            "Warning: --output-json and --output-md are ignored in batch mode "
            "to avoid overwriting outputs. Per-file default output paths will be used."
        )

    gold_by_id = load_gold(args.gold_csv, args.gold_encoding)

    for predictions_path in prediction_paths:
        if not predictions_path.exists():
            print(f"Warning: prediction file not found, skipped: {predictions_path}")
            continue

        output_json, output_md = resolve_output_paths(
            args=args,
            predictions_path=predictions_path,
            batch_mode=batch_mode,
        )

        evaluate_one_file(
            predictions_path=predictions_path,
            gold_by_id=gold_by_id,
            args=args,
            output_json=output_json,
            output_md=output_md,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
