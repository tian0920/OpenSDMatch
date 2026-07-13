import argparse
import csv
import errno
import json
import tempfile
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = BASE_DIR / "annotation_pairs_blind.csv"
DEFAULT_REPLICATES = 2

LABEL_COLUMNS = [
    "has_opportunity",
    "opportunity_score",
    "cooperation_type",
    "role_direction",
    "confidence",
]
LEGACY_LABEL_COLUMNS = [
    "label_match",
    "label_direction",
    "label_cooperation_type",
    "label_confidence",
]
REQUIRED_COLUMNS = [
    "annotation_id",
    "object_a_profile",
    "object_b_profile",
]
RESULT_COLUMNS = [
    "annotation_id",
    "source_annotation_id",
    "replicate_id",
    "annotator_id",
    *LABEL_COLUMNS,
    "saved_at",
]

HAS_OPPORTUNITY_OPTIONS = {"Yes", "No"}
OPPORTUNITY_SCORE_OPTIONS = {"1", "2", "None"}
COOPERATION_OPTIONS = {
    "供应与生产合作",
    "营销与分销合作",
    "许可与技术转移合作",
    "研发与共同开发合作",
    "资本与股权合作",
    "其他",
    "None",
}
ROLE_DIRECTION_OPTIONS = {
    "A_to_B",
    "B_to_A",
    "Bidirectional",
    "Unclear",
    "None",
}
CONFIDENCE_OPTIONS = {"1", "2"}


class CsvStore:
    def __init__(self, path: Path, replicates: int = DEFAULT_REPLICATES):
        self.path = path.resolve()
        self.replicates = replicates
        self.claims_path = self.path.with_suffix(self.path.suffix + ".claims.json")
        self.annotations_path = self.path.with_suffix(self.path.suffix + ".annotations.csv")
        self.lock = threading.Lock()

    def _read_unlocked(self) -> tuple[list[str], list[dict[str, str]]]:
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError(f"{self.path} is empty or missing a header row")
            missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
            if missing:
                raise ValueError(f"{self.path} missing columns: {missing}")
            fieldnames = self._normalized_fieldnames(reader.fieldnames)
            rows = [self._normalized_row(row) for row in reader]
            return fieldnames, rows

    def _write_unlocked(self, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        with tempfile.NamedTemporaryFile(
            "w",
            newline="",
            encoding="utf-8-sig",
            dir=self.path.parent,
            delete=False,
        ) as tmp:
            writer = csv.DictWriter(tmp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            tmp_path = Path(tmp.name)
        tmp_path.replace(self.path)

    def _read_annotations_unlocked(self) -> dict[str, dict[str, str]]:
        if not self.annotations_path.exists():
            return {}
        with open(self.annotations_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return {}
            rows = {}
            for row in reader:
                key = self._unit_key(row.get("annotation_id", ""), row.get("replicate_id", ""))
                if key:
                    rows[key] = row
            return rows

    def _write_annotations_unlocked(self, rows: dict[str, dict[str, str]]) -> None:
        with tempfile.NamedTemporaryFile(
            "w",
            newline="",
            encoding="utf-8-sig",
            dir=self.annotations_path.parent,
            delete=False,
        ) as tmp:
            writer = csv.DictWriter(tmp, fieldnames=RESULT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows[key] for key in sorted(rows))
            tmp_path = Path(tmp.name)
        tmp_path.replace(self.annotations_path)

    def _read_claims_unlocked(self) -> dict:
        if not self.claims_path.exists():
            return {}
        with open(self.claims_path, encoding="utf-8") as f:
            claims = json.load(f)
        return {
            key: claim
            for key, claim in claims.items()
            if "::R" in key and claim.get("annotation_id") and claim.get("replicate_id")
        }

    def _write_claims_unlocked(self, claims: dict) -> None:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.claims_path.parent,
            delete=False,
        ) as tmp:
            json.dump(claims, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp_path = Path(tmp.name)
        tmp_path.replace(self.claims_path)

    @staticmethod
    def _is_annotated(row: dict[str, str]) -> bool:
        return all(str(row.get(col, "")).strip() for col in LABEL_COLUMNS)

    @staticmethod
    def _unit_key(annotation_id: str, replicate_id: str | int) -> str:
        if not annotation_id or not replicate_id:
            return ""
        return f"{annotation_id}::R{replicate_id}"

    @staticmethod
    def _key_annotation_id(key: str) -> str:
        return key.split("::", 1)[0]

    @staticmethod
    def _key_replicate_id(key: str) -> str:
        return key.rsplit("R", 1)[-1]

    @staticmethod
    def _normalized_fieldnames(fieldnames: list[str]) -> list[str]:
        base = [col for col in fieldnames if col not in LABEL_COLUMNS and col not in LEGACY_LABEL_COLUMNS]
        return [*base, *LABEL_COLUMNS]

    @staticmethod
    def _normalized_row(row: dict[str, str]) -> dict[str, str]:
        normalized = {col: value for col, value in row.items() if col not in LEGACY_LABEL_COLUMNS}
        for col in LABEL_COLUMNS:
            normalized.setdefault(col, "")
        return normalized

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def stats(self) -> dict:
        with self.lock:
            _, rows = self._read_unlocked()
            annotations = self._read_annotations_unlocked()
            claims = self._read_claims_unlocked()
            annotated = len(annotations)
            claimed = sum(1 for key in claims if key not in annotations)
            total = len(rows) * self.replicates
        return {
            "total": total,
            "unique_total": len(rows),
            "annotated": annotated,
            "claimed": claimed,
            "available": total - annotated - claimed,
            "csv_path": str(self.path),
            "claims_path": str(self.claims_path),
            "annotations_path": str(self.annotations_path),
            "replicates": self.replicates,
        }

    def claim_next(self, annotator_id: str) -> dict:
        if not annotator_id:
            raise ValueError("annotator_id is required")

        with self.lock:
            _, rows = self._read_unlocked()
            annotations = self._read_annotations_unlocked()
            claims = self._read_claims_unlocked()

            for row in rows:
                for replicate_id in range(1, self.replicates + 1):
                    key = self._unit_key(row["annotation_id"], replicate_id)
                    if key in annotations:
                        continue
                    claim = claims.get(key)
                    if claim and claim.get("annotator_id") != annotator_id:
                        continue
                    if not claim and self._annotator_has_item(row["annotation_id"], annotator_id, claims, annotations):
                        continue
                    if not claim:
                        claims[key] = {
                            "annotation_id": row["annotation_id"],
                            "replicate_id": str(replicate_id),
                            "annotator_id": annotator_id,
                            "claimed_at": self._now(),
                        }
                        self._write_claims_unlocked(claims)
                    return self._build_payload(row, rows, claims, annotations, str(replicate_id))

            return self._build_payload(None, rows, claims, annotations)

    def get_item(self, annotation_id: str, annotator_id: str, replicate_id: str = "") -> dict:
        if not annotator_id:
            raise ValueError("annotator_id is required")

        with self.lock:
            _, rows = self._read_unlocked()
            annotations = self._read_annotations_unlocked()
            claims = self._read_claims_unlocked()
            row = next((row for row in rows if row["annotation_id"] == annotation_id), None)
            if row is None:
                raise KeyError(annotation_id)

            candidate_ids = [replicate_id] if replicate_id else [str(i) for i in range(1, self.replicates + 1)]
            selected_id = ""

            for rid in candidate_ids:
                key = self._unit_key(annotation_id, rid)
                saved = annotations.get(key)
                claim = claims.get(key)
                if saved and saved.get("annotator_id") == annotator_id:
                    selected_id = rid
                    break
                if claim and claim.get("annotator_id") == annotator_id:
                    selected_id = rid
                    break

            if not selected_id:
                for rid in candidate_ids:
                    key = self._unit_key(annotation_id, rid)
                    if key in annotations:
                        continue
                    claim = claims.get(key)
                    if claim and claim.get("annotator_id") != annotator_id:
                        continue
                    if self._annotator_has_item(annotation_id, annotator_id, claims, annotations):
                        continue
                    selected_id = rid
                    claims[key] = {
                        "annotator_id": annotator_id,
                        "annotation_id": annotation_id,
                        "replicate_id": str(rid),
                        "claimed_at": self._now(),
                    }
                    self._write_claims_unlocked(claims)
                    break

            if not selected_id:
                raise PermissionError("This item is unavailable for this annotator")

            return self._build_payload(row, rows, claims, annotations, selected_id)

    def update_annotation(self, annotation_id: str, annotator_id: str, replicate_id: str, labels: dict[str, str]) -> dict:
        self._validate_labels(labels)
        if not annotator_id:
            raise ValueError("annotator_id is required")
        if replicate_id not in {str(i) for i in range(1, self.replicates + 1)}:
            raise ValueError("Invalid replicate_id")

        with self.lock:
            _, rows = self._read_unlocked()
            annotations = self._read_annotations_unlocked()
            claims = self._read_claims_unlocked()
            target = next((row for row in rows if row["annotation_id"] == annotation_id), None)
            if target is None:
                raise KeyError(annotation_id)

            key = self._unit_key(annotation_id, replicate_id)
            claim = claims.get(key)
            if claim and claim.get("annotator_id") != annotator_id:
                raise PermissionError("This item was already claimed by another annotator")
            saved = annotations.get(key)
            if saved and saved.get("annotator_id") != annotator_id:
                raise PermissionError("This item was already saved by another annotator")
            if not claim and self._annotator_has_item(annotation_id, annotator_id, claims, annotations):
                raise PermissionError("This annotator already has this item")
            if not claim:
                claims[key] = {
                    "annotation_id": annotation_id,
                    "replicate_id": str(replicate_id),
                    "annotator_id": annotator_id,
                    "claimed_at": self._now(),
                }

            saved_at = self._now()
            annotations[key] = {
                "annotation_id": annotation_id,
                "source_annotation_id": target.get("source_annotation_id") or annotation_id,
                "replicate_id": str(replicate_id),
                "annotator_id": annotator_id,
                **{col: labels[col].strip() for col in LABEL_COLUMNS},
                "saved_at": saved_at,
            }
            for col in LABEL_COLUMNS:
                target[col] = labels[col].strip()
            claims[key]["saved_at"] = saved_at

            self._write_annotations_unlocked(annotations)
            self._write_claims_unlocked(claims)
            return self._build_payload(target, rows, claims, annotations, replicate_id)

    def _annotator_has_item(
        self,
        annotation_id: str,
        annotator_id: str,
        claims: dict,
        annotations: dict[str, dict[str, str]],
    ) -> bool:
        for key, item in annotations.items():
            if self._key_annotation_id(key) == annotation_id and item.get("annotator_id") == annotator_id:
                return True
        for claim in claims.values():
            if claim.get("annotation_id") == annotation_id and claim.get("annotator_id") == annotator_id:
                return True
        return False

    def _build_payload(
        self,
        row: dict[str, str] | None,
        rows: list[dict[str, str]],
        claims: dict,
        annotations: dict[str, dict[str, str]],
        replicate_id: str = "",
    ) -> dict:
        annotated = len(annotations)
        claimed = sum(1 for key in claims if key not in annotations)
        total = len(rows) * self.replicates
        payload = {
            "item": None,
            "total": total,
            "unique_total": len(rows),
            "annotated": annotated,
            "claimed": claimed,
            "available": total - annotated - claimed,
            "csv_path": str(self.path),
            "claims_path": str(self.claims_path),
            "annotations_path": str(self.annotations_path),
            "replicates": self.replicates,
        }
        if row is not None:
            key = self._unit_key(row["annotation_id"], replicate_id)
            saved = annotations.get(key, {})
            payload["item"] = {
                "annotation_id": row["annotation_id"],
                "source_annotation_id": row.get("source_annotation_id") or row["annotation_id"],
                "replicate_id": str(replicate_id),
                "unit_id": key,
                "object_a_profile": row["object_a_profile"],
                "object_b_profile": row["object_b_profile"],
                "has_opportunity": saved.get("has_opportunity", ""),
                "opportunity_score": saved.get("opportunity_score", ""),
                "cooperation_type": saved.get("cooperation_type", ""),
                "role_direction": saved.get("role_direction", ""),
                "confidence": saved.get("confidence", ""),
                "annotated": bool(saved),
            }
        return payload

    @staticmethod
    def _validate_labels(labels: dict[str, str]) -> None:
        missing = [col for col in LABEL_COLUMNS if not str(labels.get(col, "")).strip()]
        if missing:
            raise ValueError(f"Missing label fields: {missing}")
        if labels["has_opportunity"] not in HAS_OPPORTUNITY_OPTIONS:
            raise ValueError("has_opportunity must be Yes or No")
        if labels["opportunity_score"] not in OPPORTUNITY_SCORE_OPTIONS:
            raise ValueError("Invalid opportunity_score")
        if labels["cooperation_type"] not in COOPERATION_OPTIONS:
            raise ValueError("Invalid cooperation_type")
        if labels["role_direction"] not in ROLE_DIRECTION_OPTIONS:
            raise ValueError("Invalid role_direction")
        if labels["confidence"] not in CONFIDENCE_OPTIONS:
            raise ValueError("confidence must be 1 or 2")

        has_opportunity = labels["has_opportunity"]
        if has_opportunity == "Yes":
            if labels["opportunity_score"] == "None":
                raise ValueError("opportunity_score is required when has_opportunity is Yes")
            if labels["cooperation_type"] == "None":
                raise ValueError("cooperation_type is required when has_opportunity is Yes")
            if labels["role_direction"] == "None":
                raise ValueError("role_direction cannot be None when has_opportunity is Yes")
        else:
            if labels["opportunity_score"] != "None":
                raise ValueError("opportunity_score must be None unless has_opportunity is Yes")
            if labels["cooperation_type"] != "None":
                raise ValueError("cooperation_type must be None unless has_opportunity is Yes")
            if labels["role_direction"] != "None":
                raise ValueError("role_direction must be None unless has_opportunity is Yes")


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>人工标注</title>
  <style>
    :root {
      --bg: #f6f7f4;
      --panel: #fff;
      --ink: #17201b;
      --muted: #68716d;
      --line: #d9ded8;
      --accent: #0f766e;
      --soft: #e8f2ef;
      --warn: #9a3412;
      --shadow: 0 10px 24px rgba(23, 32, 27, .08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 15px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      position: sticky;
      top: 0;
      z-index: 3;
      border-bottom: 1px solid var(--line);
      background: rgba(246, 247, 244, .96);
      backdrop-filter: blur(10px);
    }
    .topbar {
      max-width: 1500px;
      margin: 0 auto;
      padding: 12px 18px;
      display: grid;
      grid-template-columns: minmax(200px, 1fr) auto auto;
      gap: 14px;
      align-items: center;
    }
    h1 { margin: 0; font-size: 18px; }
    .pill {
      display: inline-flex;
      min-height: 26px;
      align-items: center;
      padding: 2px 9px;
      border-radius: 999px;
      background: var(--soft);
      color: #0b554f;
      font-size: 13px;
    }
    .status {
      display: flex;
      gap: 10px;
      align-items: center;
      color: var(--muted);
      white-space: nowrap;
    }
    .progress {
      width: 180px;
      height: 8px;
      overflow: hidden;
      border-radius: 999px;
      background: #dfe5df;
    }
    .bar { height: 100%; width: 0; background: var(--accent); }
    .toolbar {
      display: flex;
      gap: 8px;
      justify-content: flex-end;
      flex-wrap: wrap;
      align-items: center;
    }
    button, input, textarea { font: inherit; }
    button {
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--panel);
      color: var(--ink);
      padding: 7px 11px;
      cursor: pointer;
    }
    button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }
    button:disabled { opacity: .45; cursor: not-allowed; }
    .search {
      width: 150px;
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 0 10px;
    }
    .annotator-control {
      height: 36px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding-left: 10px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--panel);
      color: var(--muted);
      font-size: 13px;
    }
    .annotator-control input {
      width: 150px;
      height: 34px;
      border: 0;
      border-left: 1px solid var(--line);
      padding: 0 10px;
      background: transparent;
      color: var(--ink);
      outline: none;
    }
    .annotator-control input[readonly] {
      cursor: default;
    }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      z-index: 20;
      display: none;
      place-items: center;
      padding: 18px;
      background: rgba(23, 32, 27, .38);
    }
    .modal-backdrop.open {
      display: grid;
    }
    .modal {
      width: min(420px, 100%);
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 18px 48px rgba(23, 32, 27, .22);
      padding: 18px;
    }
    .modal h2 {
      margin: 0 0 8px;
      font-size: 18px;
    }
    .modal p {
      margin: 0 0 14px;
      color: var(--muted);
    }
    .modal input {
      width: 100%;
      height: 40px;
      margin-bottom: 12px;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 0 10px;
    }
    .modal button {
      width: 100%;
    }
    main {
      max-width: 1500px;
      width: 100%;
      margin: 0 auto;
      padding: 18px;
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
    }
    .instruction {
      grid-column: 1 / -1;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      box-shadow: var(--shadow);
      padding: 10px 14px;
      line-height: 1.55;
    }
    .instruction h2 {
      margin: 0 0 4px;
      font-size: 15px;
    }
    .instruction p {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
    }
    .profiles {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }
    .profile, .form-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }
    .profile {
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: 300px;
      max-height: 360px;
    }
    .profile h2, .form-panel h2 {
      margin: 0;
      padding: 9px 12px;
      border-bottom: 1px solid var(--line);
      font-size: 15px;
    }
    .profile-text {
      padding: 12px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 14px;
      line-height: 1.6;
    }
    .form-panel {
      display: grid;
      grid-template-rows: auto auto;
      min-height: 0;
      overflow: hidden;
    }
    form {
      padding: 12px;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
    }
    fieldset {
      margin: 0;
      padding: 0;
      border: 0;
      min-width: 0;
    }
    legend {
      margin-bottom: 6px;
      color: var(--muted);
      font-weight: 700;
      font-size: 13px;
    }
    .segmented, .choice-list {
      display: grid;
      gap: 8px;
    }
    .segmented { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .two-choice { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .direction { grid-template-columns: 1fr; }
    .confidence { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    label.option {
      min-height: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 6px 8px;
      background: #fff;
      cursor: pointer;
      text-align: center;
      font-size: 13px;
    }
    .choice-list label.option { justify-content: flex-start; text-align: left; }
    label.option strong {
      display: block;
      color: var(--ink);
    }
    label.option span {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .compact-options label.option span {
      display: none;
    }
    .compact-options label.option:hover span,
    .compact-options label.option:has(input:checked) span {
      display: block;
    }
    .choice-list label.option {
      align-items: flex-start;
      flex-direction: column;
      gap: 2px;
    }
    .choice-list label.option:has(input:checked) span { color: #0b554f; }
    .field-note, .match-guide {
      display: grid;
      gap: 5px;
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .field-note {
      padding: 6px 8px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fbfcfa;
    }
    .guide-row {
      display: grid;
      grid-template-columns: 50px 1fr;
      gap: 6px;
      padding: 5px 7px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fbfcfa;
    }
    .guide-label {
      color: var(--ink);
      font-weight: 700;
      white-space: nowrap;
    }
    label.option input { position: absolute; opacity: 0; pointer-events: none; }
    label.option:has(input:checked) {
      border-color: var(--accent);
      background: var(--soft);
      color: #0b554f;
      font-weight: 700;
    }
    fieldset.disabled {
      opacity: .54;
    }
    fieldset.disabled label.option {
      cursor: not-allowed;
      background: #f7f8f6;
    }
    .footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 12px;
      border-top: 1px solid var(--line);
      background: #fbfcfa;
    }
    .actions {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 8px;
      min-width: 300px;
    }
    .message { min-height: 22px; color: var(--muted); }
    .message.error { color: var(--warn); }
    @media (max-width: 1120px) {
      .topbar, main { grid-template-columns: 1fr; }
      .toolbar { justify-content: flex-start; }
      .profiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      form { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .profile { min-height: 280px; max-height: 340px; }
    }
    @media (max-width: 700px) {
      .topbar, main { padding-left: 12px; padding-right: 12px; }
      .profiles, form, .segmented, .confidence { grid-template-columns: 1fr; }
      .status { flex-wrap: wrap; white-space: normal; }
      .progress { width: 100%; }
      .profile { max-height: none; }
      .footer { display: grid; }
      .actions { min-width: 0; }
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <h1>人工标注 <span class="pill" id="current-id">-</span></h1>
      <div class="status">
        <span id="counter">0 / 0</span>
        <div class="progress"><div class="bar" id="progress-bar"></div></div>
        <span id="progress-text">0%</span>
        <span id="claimed-text">已领取 0</span>
      </div>
      <div class="toolbar">
        <button id="next-btn" type="button">领取下一题</button>
        <label class="annotator-control"><span>标注人</span><input id="annotator-input" readonly placeholder="未登记"></label>
        <input class="search" id="jump-input" placeholder="ANN_00001">
        <button id="jump-btn" type="button">打开已领取</button>
      </div>
    </div>
  </header>
  <div class="modal-backdrop" id="annotator-modal">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="annotator-modal-title">
      <h2 id="annotator-modal-title">输入标注人编号</h2>
      <p>本次打开网站期间只需要填写一次，之后领取和保存都会固定使用这个编号。</p>
      <input id="annotator-start-input" autocomplete="name" placeholder="请输入标注人编号">
      <button id="annotator-start-btn" class="primary" type="button">开始标注</button>
    </div>
  </div>
  <main>
    <section class="instruction" aria-label="标注说明">
      <h2>标注说明</h2>
      <p>请基于企业 A 和企业 B 的基本经营信息，判断二者之间是否存在合理的潜在合作机会。标注时应依据企业的基本经营信息，判断双方是否存在潜在的、可解释的商业互补关系。若存在合作机会，请进一步判断其主要合作形式、合作潜力强度、合作方向；若不存在潜在合作机会，请标注为 No。</p>
    </section>
    <section class="profiles">
      <article class="profile">
        <h2>对象 A</h2>
        <div class="profile-text" id="profile-a"></div>
      </article>
      <article class="profile">
        <h2>对象 B</h2>
        <div class="profile-text" id="profile-b"></div>
      </article>
    </section>
    <aside class="form-panel">
      <h2>标注</h2>
      <form id="label-form">
        <fieldset>
          <legend>Q1 是否存在潜在合作机会？</legend>
          <div class="segmented two-choice">
            <label class="option"><input type="radio" name="has_opportunity" value="Yes">Yes 存在潜在合作机会</label>
            <label class="option"><input type="radio" name="has_opportunity" value="No">No 无潜在合作机会</label>
          </div>
          <div class="match-guide" aria-label="匹配标签说明">
            <div class="guide-row"><span class="guide-label">Yes</span><span>存在潜在合作机会</span></div>
            <div class="guide-row"><span class="guide-label">No</span><span>无潜在合作机会</span></div>
          </div>
        </fieldset>
        <fieldset data-yes-only>
          <legend>Q2 合作潜力评分</legend>
          <div class="segmented two-choice">
            <label class="option"><input type="radio" name="opportunity_score" value="1">1 弱</label>
            <label class="option"><input type="radio" name="opportunity_score" value="2">2 强</label>
          </div>
          <div class="match-guide" aria-label="合作潜力评分说明">
            <div class="guide-row"><span class="guide-label">1</span><span>存在行业、标签或概念上的弱相关，但合作路径不明确</span></div>
            <div class="guide-row"><span class="guide-label">2</span><span>合作路径较明确，双方产品、能力、渠道、场景或需求存在较好匹配</span></div>
          </div>
          <div class="field-note">仅当 Q1 = Yes 时标注，否则保存为 None。</div>
        </fieldset>
        <fieldset data-yes-only>
          <legend>Q3 主要合作形式</legend>
          <div class="choice-list compact-options">
            <label class="option"><input type="radio" name="cooperation_type" value="供应与生产合作"><strong>供应与生产合作</strong><span>合作核心是一方向另一方提供产品、服务、设备、零部件、产能、制造、物流或履约支持</span></label>
            <label class="option"><input type="radio" name="cooperation_type" value="营销与分销合作"><strong>营销与分销合作</strong><span>合作核心是一方帮助另一方触达客户、拓展渠道、扩大市场、获得订单或提升品牌影响</span></label>
            <label class="option"><input type="radio" name="cooperation_type" value="许可与技术转移合作"><strong>许可与技术转移合作</strong><span>合作核心是一方开放或授权技术、专利、品牌、IP、数据、接口、平台、资质、场景或经营体系给另一方使用</span></label>
            <label class="option"><input type="radio" name="cooperation_type" value="研发与共同开发合作"><strong>研发与共同开发合作</strong><span>合作核心是双方共同投入并共同开发新的产品、技术、方案、标准、知识产权或业务模式</span></label>
            <label class="option"><input type="radio" name="cooperation_type" value="资本与股权合作"><strong>资本与股权合作</strong><span>合作核心是投资、融资、股权、基金、授信、并购、融资租赁、担保或其他金融工具</span></label>
            <label class="option"><input type="radio" name="cooperation_type" value="其他"><strong>其他</strong><span>存在潜在合作机会，但主要形式不属于以上五类</span></label>
          </div>
          <div class="field-note">仅当 Q1 = Yes 时标注，否则保存为 None。</div>
        </fieldset>
        <fieldset data-yes-only>
          <legend>Q4 合作方向</legend>
          <div class="choice-list direction">
            <label class="option"><input type="radio" name="role_direction" value="A_to_B"><strong>A_to_B</strong><span>A 主要向 B 提供产品、服务、能力、资源或资本</span></label>
            <label class="option"><input type="radio" name="role_direction" value="B_to_A"><strong>B_to_A</strong><span>B 主要向 A 提供产品、服务、能力、资源或资本</span></label>
            <label class="option"><input type="radio" name="role_direction" value="Bidirectional"><strong>Bidirectional</strong><span>双向合作或共同创造</span></label>
            <label class="option"><input type="radio" name="role_direction" value="Unclear"><strong>Unclear</strong><span>基于现有信息无法判断方向</span></label>
          </div>
          <div class="field-note">仅当 Q1 = Yes 时标注，否则保存为 None。</div>
        </fieldset>
        <fieldset>
          <legend>Q5 标注信心</legend>
          <div class="segmented confidence">
            <label class="option"><input type="radio" name="confidence" value="1">1 低</label>
            <label class="option"><input type="radio" name="confidence" value="2">2 高</label>
          </div>
          <div class="match-guide" aria-label="信心评分说明">
            <div class="guide-row"><span class="guide-label">1</span><span>低信心，信息不足或判断较模糊</span></div>
            <div class="guide-row"><span class="guide-label">2</span><span>高信心，合作逻辑清晰且依据充分</span></div>
          </div>
        </fieldset>
      </form>
      <div class="footer">
        <div class="message" id="message"></div>
        <div class="actions">
          <button id="prev-btn" type="button">上一题</button>
          <button id="save-btn" class="primary" type="button">保存</button>
          <button id="save-next-btn" class="primary" type="button">保存并领取下一题</button>
        </div>
      </div>
    </aside>
  </main>

  <script>
    const state = {
      item: null,
      annotatorId: sessionStorage.getItem("annotation_session_annotator_id") || "",
      history: JSON.parse(sessionStorage.getItem("annotation_session_history") || "[]"),
      historyIndex: Number(sessionStorage.getItem("annotation_session_history_index") || "-1"),
    };
    const els = {
      currentId: document.getElementById("current-id"),
      counter: document.getElementById("counter"),
      progressBar: document.getElementById("progress-bar"),
      progressText: document.getElementById("progress-text"),
      claimedText: document.getElementById("claimed-text"),
      profileA: document.getElementById("profile-a"),
      profileB: document.getElementById("profile-b"),
      form: document.getElementById("label-form"),
      message: document.getElementById("message"),
      save: document.getElementById("save-btn"),
      saveNext: document.getElementById("save-next-btn"),
      next: document.getElementById("next-btn"),
      prev: document.getElementById("prev-btn"),
      annotatorInput: document.getElementById("annotator-input"),
      annotatorModal: document.getElementById("annotator-modal"),
      annotatorStartInput: document.getElementById("annotator-start-input"),
      annotatorStart: document.getElementById("annotator-start-btn"),
      jumpInput: document.getElementById("jump-input"),
      jump: document.getElementById("jump-btn"),
    };
    if (!Array.isArray(state.history) || state.historyIndex < -1 || state.historyIndex >= state.history.length) {
      state.history = [];
      state.historyIndex = -1;
    }

    function getAnnotatorId() {
      return state.annotatorId;
    }

    function setAnnotatorId(value) {
      state.annotatorId = value;
      sessionStorage.setItem("annotation_session_annotator_id", value);
      const historyAnnotator = sessionStorage.getItem("annotation_session_history_annotator_id") || "";
      if (historyAnnotator && historyAnnotator !== value) {
        state.history = [];
        state.historyIndex = -1;
        persistHistory();
      }
      sessionStorage.setItem("annotation_session_history_annotator_id", value);
      els.annotatorInput.value = value;
      els.annotatorInput.title = value;
    }

    function showAnnotatorModal() {
      els.annotatorModal.classList.add("open");
      window.setTimeout(() => els.annotatorStartInput.focus(), 0);
    }

    function hideAnnotatorModal() {
      els.annotatorModal.classList.remove("open");
    }

    function ensureAnnotator() {
      if (state.annotatorId) return true;
      showMessage("请先输入标注人编号", true);
      showAnnotatorModal();
      return false;
    }

    async function requestJson(url, options = {}) {
      const response = await fetch(url, options);
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }

    async function claimNext() {
      if (!ensureAnnotator()) return;
      const annotatorId = getAnnotatorId();
      const data = await requestJson(`/api/claim-next?annotator_id=${encodeURIComponent(annotatorId)}`);
      render(data, {pushHistory: true});
    }

    async function openClaimed(annotationId, replicateId = "", options = {}) {
      if (!ensureAnnotator()) return;
      const annotatorId = getAnnotatorId();
      const params = new URLSearchParams({annotator_id: annotatorId});
      if (replicateId) params.set("replicate_id", replicateId);
      const data = await requestJson(`/api/item/${encodeURIComponent(annotationId)}?${params.toString()}`);
      render(data, options);
    }

    function render(data, options = {}) {
      const annotated = data.annotated || 0;
      const total = data.total || 0;
      const pct = total ? Math.round((annotated / total) * 100) : 0;
      state.item = data.item;
      if (state.item && options.pushHistory) {
        pushHistory(state.item);
      }
      els.counter.textContent = `${annotated} / ${total}`;
      els.progressBar.style.width = `${pct}%`;
      els.progressText.textContent = `${pct}%`;
      els.claimedText.textContent = `已领取 ${data.claimed || 0}`;

      if (!state.item) {
        els.currentId.textContent = "-";
        els.profileA.textContent = "";
        els.profileB.textContent = "";
        els.form.reset();
        els.save.disabled = true;
        els.saveNext.disabled = true;
        updatePrevButton();
        showMessage("没有可领取的未标注题目");
        return;
      }

      els.save.disabled = false;
      els.saveNext.disabled = false;
      updatePrevButton();
      els.currentId.textContent = `${state.item.annotation_id} / R${state.item.replicate_id}`;
      els.profileA.textContent = state.item.object_a_profile;
      els.profileB.textContent = state.item.object_b_profile;
      fillForm(state.item);
      showMessage("该题的这一份标注已为你锁定，同一道题不会再次分配给你");
    }

    function unitFromItem(item) {
      return {
        annotation_id: item.annotation_id,
        replicate_id: String(item.replicate_id),
      };
    }

    function sameUnit(a, b) {
      return a && b && a.annotation_id === b.annotation_id && String(a.replicate_id) === String(b.replicate_id);
    }

    function pushHistory(item) {
      const unit = unitFromItem(item);
      if (state.historyIndex >= 0 && sameUnit(state.history[state.historyIndex], unit)) {
        persistHistory();
        return;
      }
      state.history = state.history.slice(0, state.historyIndex + 1);
      state.history.push(unit);
      state.historyIndex = state.history.length - 1;
      persistHistory();
    }

    function persistHistory() {
      sessionStorage.setItem("annotation_session_history", JSON.stringify(state.history));
      sessionStorage.setItem("annotation_session_history_index", String(state.historyIndex));
      updatePrevButton();
    }

    function updatePrevButton() {
      els.prev.disabled = state.historyIndex <= 0;
    }

    async function openPrevious() {
      if (!ensureAnnotator()) return;
      if (state.historyIndex <= 0) {
        showMessage("当前没有上一题可回溯");
        updatePrevButton();
        return;
      }
      state.historyIndex -= 1;
      persistHistory();
      const unit = state.history[state.historyIndex];
      await openClaimed(unit.annotation_id, unit.replicate_id, {pushHistory: false});
      showMessage("已回到上一题，可修改后重新保存");
    }

    function fillForm(item) {
      els.form.reset();
      setRadio("has_opportunity", item.has_opportunity);
      setRadio("opportunity_score", item.opportunity_score);
      setRadio("cooperation_type", item.cooperation_type);
      setRadio("role_direction", item.role_direction);
      setRadio("confidence", item.confidence);
      updateConditionalFields();
    }

    function setRadio(name, value) {
      if (!value) return;
      const input = els.form.querySelector(`input[name="${name}"][value="${cssEscape(value)}"]`);
      if (input) input.checked = true;
    }

    function cssEscape(value) {
      return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    }

    function collectLabels() {
      const form = new FormData(els.form);
      const hasOpportunity = form.get("has_opportunity") || "";
      const enabled = hasOpportunity === "Yes";
      return {
        has_opportunity: hasOpportunity,
        opportunity_score: enabled ? (form.get("opportunity_score") || "") : "None",
        cooperation_type: enabled ? (form.get("cooperation_type") || "") : "None",
        role_direction: enabled ? (form.get("role_direction") || "") : "None",
        confidence: form.get("confidence") || "",
      };
    }

    function validate(labels) {
      if (!labels.has_opportunity) return "请选择 Q1";
      if (labels.has_opportunity === "Yes" && labels.opportunity_score === "") return "请选择 Q2";
      if (labels.has_opportunity === "Yes" && labels.cooperation_type === "") return "请选择 Q3";
      if (labels.has_opportunity === "Yes" && labels.role_direction === "") return "请选择 Q4";
      if (!labels.confidence) return "请选择 Q5";
      return "";
    }

    function clearRadioGroup(name) {
      els.form.querySelectorAll(`input[name="${name}"]`).forEach(input => {
        input.checked = false;
      });
    }

    function updateConditionalFields() {
      const hasOpportunity = new FormData(els.form).get("has_opportunity") || "";
      const enabled = hasOpportunity === "Yes";
      els.form.querySelectorAll("[data-yes-only]").forEach(fieldset => {
        fieldset.classList.toggle("disabled", !enabled);
        fieldset.querySelectorAll("input").forEach(input => {
          input.disabled = !enabled;
        });
      });
      if (!enabled) {
        clearRadioGroup("opportunity_score");
        clearRadioGroup("cooperation_type");
        clearRadioGroup("role_direction");
      }
    }

    async function save(moveNext) {
      if (!state.item) return;
      if (!ensureAnnotator()) return;
      const labels = collectLabels();
      const error = validate(labels);
      if (error) {
        showMessage(error, true);
        return;
      }
      els.save.disabled = true;
      els.saveNext.disabled = true;
      const annotatorId = getAnnotatorId();
      await requestJson(
        `/api/annotation/${encodeURIComponent(state.item.annotation_id)}?annotator_id=${encodeURIComponent(annotatorId)}&replicate_id=${encodeURIComponent(state.item.replicate_id)}`,
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(labels),
        }
      );
      if (moveNext) {
        await claimNext();
      } else {
        await openClaimed(state.item.annotation_id, state.item.replicate_id, {pushHistory: false});
        showMessage("已保存到结果 CSV");
      }
    }

    function showMessage(text, isError = false) {
      els.message.textContent = text;
      els.message.classList.toggle("error", isError);
    }

    els.save.addEventListener("click", () => save(false).catch(error => showMessage(error.message, true)));
    els.saveNext.addEventListener("click", () => save(true).catch(error => showMessage(error.message, true)));
    els.next.addEventListener("click", () => claimNext().catch(error => showMessage(error.message, true)));
    els.prev.addEventListener("click", () => openPrevious().catch(error => showMessage(error.message, true)));
    els.annotatorStart.addEventListener("click", () => {
      const value = els.annotatorStartInput.value.trim();
      if (!value) {
        showMessage("请输入标注人编号", true);
        els.annotatorStartInput.focus();
        return;
      }
      setAnnotatorId(value);
      hideAnnotatorModal();
      claimNext().catch(error => showMessage(error.message, true));
    });
    els.annotatorStartInput.addEventListener("keydown", event => {
      if (event.key === "Enter") els.annotatorStart.click();
    });
    els.form.addEventListener("change", event => {
      if (event.target.name === "has_opportunity") updateConditionalFields();
    });
    els.jump.addEventListener("click", () => {
      openClaimed(els.jumpInput.value.trim(), "", {pushHistory: true}).catch(error => showMessage(error.message, true));
    });
    els.jumpInput.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        openClaimed(els.jumpInput.value.trim(), "", {pushHistory: true}).catch(error => showMessage(error.message, true));
      }
    });

    if (state.annotatorId) {
      setAnnotatorId(state.annotatorId);
      claimNext().catch(error => showMessage(error.message, true));
    } else {
      els.save.disabled = true;
      els.saveNext.disabled = true;
      updatePrevButton();
      showAnnotatorModal();
      showMessage("请先输入标注人编号");
    }
  </script>
</body>
</html>
"""


class AnnotationHandler(BaseHTTPRequestHandler):
    store: CsvStore

    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        annotator_id = query.get("annotator_id", [""])[0]
        try:
            if parsed.path == "/":
                self._send_html(HTML)
                return
            if parsed.path == "/api/stats":
                self._send_json(self.store.stats())
                return
            if parsed.path == "/api/claim-next":
                self._send_json(self.store.claim_next(annotator_id))
                return
            if parsed.path.startswith("/api/item/"):
                annotation_id = parsed.path.rsplit("/", 1)[-1]
                replicate_id = query.get("replicate_id", [""])[0]
                self._send_json(self.store.get_item(annotation_id, annotator_id, replicate_id))
                return
            if parsed.path == "/download":
                self._send_file(self.store.path)
                return
            if parsed.path == "/download-annotations":
                self._send_file(self.store.annotations_path)
                return
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "annotation_id not found")
            return
        except PermissionError as exc:
            self.send_error(HTTPStatus.CONFLICT, str(exc))
            return
        except ValueError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        annotator_id = query.get("annotator_id", [""])[0]
        if not parsed.path.startswith("/api/annotation/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        annotation_id = parsed.path.rsplit("/", 1)[-1]
        replicate_id = query.get("replicate_id", [""])[0]
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            labels = json.loads(body.decode("utf-8"))
            self._send_json(self.store.update_annotation(annotation_id, annotator_id, replicate_id, labels))
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND, "annotation_id not found")
        except PermissionError as exc:
            self.send_error(HTTPStatus.CONFLICT, str(exc))
        except (json.JSONDecodeError, ValueError) as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def _send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local CSV annotation web app.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help=f"CSV file to annotate. Default: {DEFAULT_CSV}")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="Bind port. Use 0 for any free port. Default: 8765")
    parser.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES, help=f"Annotations per item. Default: {DEFAULT_REPLICATES}")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.replicates < 1:
        raise ValueError("--replicates must be at least 1")
    AnnotationHandler.store = CsvStore(args.csv, args.replicates)
    try:
        server = ThreadingHTTPServer((args.host, args.port), AnnotationHandler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise SystemExit(
                f"Port {args.port} is already in use on {args.host}. "
                f"Stop the existing server or run with a different port, for example: "
                f"python {Path(__file__).as_posix()} --port 8766"
            ) from exc
        raise
    actual_host, actual_port = server.server_address
    print(f"Annotating: {AnnotationHandler.store.path}")
    print(f"Claims: {AnnotationHandler.store.claims_path}")
    print(f"Annotations: {AnnotationHandler.store.annotations_path}")
    print(f"Replicates per item: {AnnotationHandler.store.replicates}")
    print(f"Open: http://{actual_host}:{actual_port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
