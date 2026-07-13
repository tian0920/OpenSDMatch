#!/usr/bin/env python3
"""Independent web UI for third-pass tie-break annotation."""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR.parent
DEFAULT_CSV = BASE_DIR / "annotation_pairs_tiebreak.csv"
DEFAULT_GOLD_CSV = ROOT / "model_test" / "gold" / "annotation_pairs_test.csv"

VOTE_COLUMNS = ["has_opportunity", "opportunity_score", "cooperation_type", "role_direction", "confidence"]
REQUIRED_COLUMNS = ["annotation_id", "source_annotation_id", "object_a_profile", "object_b_profile", "tiebreak_fields"]
RESULT_COLUMNS = [
    "source_annotation_id",
    "annotation_id",
    "annotator_id",
    *VOTE_COLUMNS,
    "tiebreak_fields",
    "saved_at",
]

OPTIONS = {
    "has_opportunity": {"Yes", "No"},
    "opportunity_score": {"1", "2", "None"},
    "cooperation_type": {
        "供应与生产合作",
        "营销与分销合作",
        "许可与技术转移合作",
        "研发与共同开发合作",
        "资本与股权合作",
        "其他",
        "None",
    },
    "role_direction": {"A_to_B", "B_to_A", "Bidirectional", "Unclear", "None"},
    "confidence": {"1", "2"},
}


class TiebreakStore:
    def __init__(self, path: Path, gold_path: Path):
        self.path = path.resolve()
        self.gold_path = gold_path.resolve()
        self.annotations_path = self.path.with_suffix(self.path.suffix + ".annotations.csv")
        self.claims_path = self.path.with_suffix(self.path.suffix + ".claims.json")
        self.lock = threading.RLock()

    def _read_rows(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = [col for col in REQUIRED_COLUMNS if col not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"{self.path} missing columns: {missing}")
            return list(reader)

    def _read_annotations(self) -> dict[str, dict[str, str]]:
        if not self.annotations_path.exists():
            return {}
        with self.annotations_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            return {
                row["source_annotation_id"]: row
                for row in reader
                if row.get("source_annotation_id")
            }

    def _write_annotations(self, rows: dict[str, dict[str, str]]) -> None:
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

    def _read_claims(self) -> dict[str, dict[str, str]]:
        if not self.claims_path.exists():
            return {}
        with self.claims_path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _write_claims(self, claims: dict[str, dict[str, str]]) -> None:
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

    def _gold_source_ids(self) -> set[str]:
        if not self.gold_path.exists():
            return set()
        with self.gold_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            return {
                (row.get("source_annotation_id") or row.get("annotation_id") or "").strip()
                for row in reader
                if (row.get("source_annotation_id") or row.get("annotation_id") or "").strip()
            }

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _fields(row: dict[str, str]) -> list[str]:
        return [field for field in row.get("tiebreak_fields", "").split("|") if field in VOTE_COLUMNS]

    def _annotation_complete(self, annotation: dict[str, str] | None, row: dict[str, str]) -> bool:
        if not annotation:
            return False
        return all(str(annotation.get(field, "")).strip() for field in self._fields(row))

    def stats(self) -> dict:
        with self.lock:
            rows = self._read_rows()
            annotations = self._read_annotations()
            claims = self._read_claims()
            gold_ids = self._gold_source_ids()
            active_rows = [row for row in rows if row["source_annotation_id"] not in gold_ids]
            complete_ids = {
                row["source_annotation_id"]
                for row in active_rows
                if self._annotation_complete(annotations.get(row["source_annotation_id"]), row)
            }
            claimed = sum(1 for sid in claims if sid not in complete_ids and sid not in gold_ids)
        return {
            "total": len(active_rows),
            "annotated": len(complete_ids),
            "claimed": claimed,
            "available": len(active_rows) - len(complete_ids) - claimed,
            "csv_path": str(self.path),
            "annotations_path": str(self.annotations_path),
            "claims_path": str(self.claims_path),
            "gold_path": str(self.gold_path),
        }

    def claim_next(self, annotator_id: str) -> dict:
        if not annotator_id:
            raise ValueError("annotator_id is required")
        with self.lock:
            rows = self._read_rows()
            annotations = self._read_annotations()
            claims = self._read_claims()
            gold_ids = self._gold_source_ids()
            for row in rows:
                sid = row["source_annotation_id"]
                if sid in gold_ids or self._annotation_complete(annotations.get(sid), row):
                    continue
                claim = claims.get(sid)
                if claim and claim.get("annotator_id") != annotator_id:
                    continue
                if not claim:
                    claims[sid] = {"annotator_id": annotator_id, "claimed_at": self._now()}
                    self._write_claims(claims)
                return self._payload(row, annotations)
            return self._payload(None, annotations)

    def submit(self, source_annotation_id: str, annotator_id: str, labels: dict[str, str]) -> dict:
        if not annotator_id:
            raise ValueError("annotator_id is required")
        with self.lock:
            rows = self._read_rows()
            annotations = self._read_annotations()
            gold_ids = self._gold_source_ids()
            row = next((item for item in rows if item["source_annotation_id"] == source_annotation_id), None)
            if row is None:
                raise KeyError(source_annotation_id)
            if source_annotation_id in gold_ids:
                raise PermissionError("This item is already resolved into gold")
            if self._annotation_complete(annotations.get(source_annotation_id), row):
                raise PermissionError("This item was already tie-break annotated")

            fields = self._fields(row)
            merged = {column: row.get(column, "") for column in VOTE_COLUMNS}
            for field in fields:
                value = str(labels.get(field, "")).strip()
                if value not in OPTIONS[field]:
                    raise ValueError(f"Invalid {field}")
                merged[field] = value

            self._validate_consistency(merged)
            annotations[source_annotation_id] = {
                "source_annotation_id": source_annotation_id,
                "annotation_id": row.get("annotation_id", source_annotation_id),
                "annotator_id": annotator_id,
                **merged,
                "tiebreak_fields": "|".join(fields),
                "saved_at": self._now(),
            }
            self._write_annotations(annotations)
            return self._payload(None, annotations)

    @staticmethod
    def _validate_consistency(labels: dict[str, str]) -> None:
        if labels["has_opportunity"] == "No":
            if labels["opportunity_score"] != "None":
                raise ValueError("opportunity_score must be None when has_opportunity is No")
            if labels["cooperation_type"] != "None":
                raise ValueError("cooperation_type must be None when has_opportunity is No")
            if labels["role_direction"] != "None":
                raise ValueError("role_direction must be None when has_opportunity is No")
        elif labels["has_opportunity"] == "Yes":
            if labels["opportunity_score"] == "None":
                raise ValueError("opportunity_score is required when has_opportunity is Yes")
            if labels["cooperation_type"] == "None":
                raise ValueError("cooperation_type is required when has_opportunity is Yes")
            if labels["role_direction"] == "None":
                raise ValueError("role_direction cannot be None when has_opportunity is Yes")
        else:
            raise ValueError("has_opportunity must be Yes or No")

        if labels["confidence"] not in OPTIONS["confidence"]:
            raise ValueError("confidence must be 1 or 2")

    def _payload(self, row: dict[str, str] | None, annotations: dict[str, dict[str, str]]) -> dict:
        stats = self.stats()
        payload = {**stats, "item": None}
        if row:
            payload["item"] = {
                "annotation_id": row["annotation_id"],
                "source_annotation_id": row["source_annotation_id"],
                "object_a_profile": row["object_a_profile"],
                "object_b_profile": row["object_b_profile"],
                "tiebreak_fields": self._fields(row),
                **{column: row.get(column, "") for column in VOTE_COLUMNS},
            }
        return payload


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>第三方复核标注</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; background: #f6f7f4; color: #17201b; font: 15px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { position: sticky; top: 0; background: #f6f7f4f5; border-bottom: 1px solid #d9ded8; z-index: 2; }
    .topbar, main { max-width: 1480px; margin: 0 auto; padding: 14px 18px; }
    .topbar { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: center; }
    h1 { margin: 0; font-size: 18px; }
    .stats { color: #68716d; font-size: 13px; }
    input, button { font: inherit; }
    .annotator { display: flex; gap: 8px; align-items: center; }
    .annotator input { width: 160px; padding: 8px 10px; border: 1px solid #d9ded8; border-radius: 8px; }
    button { border: 0; border-radius: 8px; background: #0f766e; color: white; padding: 9px 14px; cursor: pointer; }
    button.secondary { background: #e8f2ef; color: #0f766e; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    main { display: grid; grid-template-columns: minmax(0, 1fr) 420px; gap: 16px; align-items: start; }
    .instruction, .profile, .form-panel { background: white; border: 1px solid #d9ded8; border-radius: 8px; padding: 16px; box-shadow: 0 10px 24px rgba(23, 32, 27, .08); }
    .instruction { grid-column: 1 / -1; }
    .instruction h2, .profile h2, .form-panel h2 { margin: 0 0 10px; font-size: 16px; }
    .instruction p { margin: 0; color: #34403a; }
    .profiles { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; }
    fieldset { border: 0; padding: 0; margin: 0 0 18px; }
    legend { font-weight: 700; margin-bottom: 8px; }
    .options { display: grid; gap: 8px; }
    .option { display: grid; grid-template-columns: auto 1fr; gap: 8px; border: 1px solid #d9ded8; border-radius: 8px; padding: 9px; cursor: pointer; }
    .option span { color: #68716d; }
    .option strong { display: block; color: #17201b; }
    .option:has(input:checked) { border-color: #0f766e; background: #e8f2ef; }
    .match-guide { display: grid; gap: 4px; margin-top: 8px; color: #68716d; font-size: 13px; }
    .guide-row { display: grid; grid-template-columns: 48px 1fr; gap: 8px; }
    .guide-label { font-weight: 700; color: #0f766e; }
    .field-note { margin-top: 8px; color: #68716d; font-size: 13px; }
    .muted { color: #68716d; }
    .status { min-height: 24px; color: #9a3412; }
    @media (max-width: 1100px) { main, .profiles { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<header>
  <div class="topbar">
    <div>
      <h1>第三方复核标注</h1>
      <div id="stats" class="stats"></div>
    </div>
    <div class="annotator">
      <label>标注员 <input id="annotator" autocomplete="off"></label>
      <button id="next">领取下一条</button>
      <button id="download" class="secondary">下载结果</button>
    </div>
  </div>
</header>
<main>
  <section class="instruction" aria-label="复核说明">
    <h2>复核说明</h2>
    <p>请基于企业 A 和企业 B 的基本经营信息，复核前两位标注员出现平票的字段。页面只展示需要第三人裁决的字段；未展示的字段已由前两轮投票确定，会随复核结果一起参与最终投票。</p>
  </section>
  <section class="profiles">
    <article class="profile"><h2>对象 A</h2><pre id="profileA"></pre></article>
    <article class="profile"><h2>对象 B</h2><pre id="profileB"></pre></article>
  </section>
  <form id="form" class="form-panel">
    <h2>仅复核平票字段</h2>
    <div id="meta" class="muted"></div>
    <div id="fields"></div>
    <div class="status" id="status"></div>
    <button id="submit" type="submit">提交复核</button>
  </form>
</main>
<script>
const VOTE_COLUMNS = ["has_opportunity", "opportunity_score", "cooperation_type", "role_direction", "confidence"];
const OPTIONS = {
  has_opportunity: [
    ["Yes", "Yes", "存在潜在合作机会"],
    ["No", "No", "无潜在合作机会"]
  ],
  opportunity_score: [
    ["1", "1 弱", "存在行业、标签或概念上的弱相关，但合作路径不明确"],
    ["2", "2 强", "合作路径较明确，双方产品、能力、渠道、场景或需求存在较好匹配"],
    ["None", "None", "无机会时使用"]
  ],
  cooperation_type: [
    ["供应与生产合作", "供应与生产合作", "合作核心是一方向另一方提供产品、服务、设备、零部件、产能、制造、物流或履约支持"],
    ["营销与分销合作", "营销与分销合作", "合作核心是一方帮助另一方触达客户、拓展渠道、扩大市场、获得订单或提升品牌影响"],
    ["许可与技术转移合作", "许可与技术转移合作", "合作核心是一方开放或授权技术、专利、品牌、IP、数据、接口、平台、资质、场景或经营体系给另一方使用"],
    ["研发与共同开发合作", "研发与共同开发合作", "合作核心是双方共同投入并共同开发新的产品、技术、方案、标准、知识产权或业务模式"],
    ["资本与股权合作", "资本与股权合作", "合作核心是投资、融资、股权、基金、授信、并购、融资租赁、担保或其他金融工具"],
    ["其他", "其他", "存在潜在合作机会，但主要形式不属于以上五类"],
    ["None", "None", "无机会时使用"]
  ],
  role_direction: [
    ["A_to_B", "A_to_B", "A 主要向 B 提供产品、服务、能力、资源或资本"],
    ["B_to_A", "B_to_A", "B 主要向 A 提供产品、服务、能力、资源或资本"],
    ["Bidirectional", "Bidirectional", "双向合作或共同创造"],
    ["Unclear", "Unclear", "存在合作机会，但基于现有信息无法判断方向"],
    ["None", "None", "无机会时使用"]
  ],
  confidence: [
    ["1", "1 低", "证据较弱或判断不确定"],
    ["2", "2 高", "证据较明确，判断较有把握"]
  ]
};
const LABELS = {
  has_opportunity: "Q1 是否存在潜在合作机会",
  opportunity_score: "Q2 机会强弱",
  cooperation_type: "Q3 合作类型",
  role_direction: "Q4 角色方向",
  confidence: "Q5 标注置信度"
};
let current = null;
const els = {
  annotator: document.getElementById("annotator"),
  next: document.getElementById("next"),
  download: document.getElementById("download"),
  stats: document.getElementById("stats"),
  profileA: document.getElementById("profileA"),
  profileB: document.getElementById("profileB"),
  form: document.getElementById("form"),
  fields: document.getElementById("fields"),
  meta: document.getElementById("meta"),
  status: document.getElementById("status"),
  submit: document.getElementById("submit")
};
els.annotator.value = localStorage.getItem("tiebreak_annotator") || "";
function annotator() {
  const value = els.annotator.value.trim();
  if (value) localStorage.setItem("tiebreak_annotator", value);
  return value;
}
function setStatus(text) { els.status.textContent = text || ""; }
function renderStats(data) {
  els.stats.textContent = `总计 ${data.total || 0} | 已复核 ${data.annotated || 0} | 已领取 ${data.claimed || 0} | 可领取 ${data.available || 0}`;
}
function renderItem(data) {
  renderStats(data);
  current = data.item;
  setStatus("");
  els.fields.innerHTML = "";
  if (!current) {
    els.profileA.textContent = "暂无待复核样本";
    els.profileB.textContent = "";
    els.meta.textContent = "";
    els.submit.disabled = true;
    return;
  }
  els.submit.disabled = false;
  els.profileA.textContent = current.object_a_profile || "";
  els.profileB.textContent = current.object_b_profile || "";
  els.meta.textContent = `source_annotation_id: ${current.source_annotation_id}；需复核字段：${current.tiebreak_fields.join(", ")}`;
  for (const name of current.tiebreak_fields) {
    const fs = document.createElement("fieldset");
    fs.innerHTML = `<legend>${LABELS[name]}</legend><div class="options"></div>`;
    const options = fs.querySelector(".options");
    for (const [value, title, desc] of OPTIONS[name]) {
      const label = document.createElement("label");
      label.className = "option";
      label.innerHTML = `<input type="radio" name="${name}" value="${value}"><div><strong>${title}</strong><span>${desc}</span></div>`;
      options.appendChild(label);
    }
    if (name !== "has_opportunity") {
      const note = document.createElement("div");
      note.className = "field-note";
      note.textContent = "若最终 Q1 = No，该字段应选择 None；若最终 Q1 = Yes，该字段应选择非 None 的具体结果。";
      fs.appendChild(note);
    }
    els.fields.appendChild(fs);
  }
}
async function api(path, payload) {
  const response = await fetch(path, {
    method: payload ? "POST" : "GET",
    headers: payload ? {"Content-Type": "application/json"} : {},
    body: payload ? JSON.stringify(payload) : undefined
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}
els.next.addEventListener("click", async () => {
  try {
    const id = annotator();
    if (!id) return setStatus("请先填写标注员 ID");
    renderItem(await api(`/api/next?annotator_id=${encodeURIComponent(id)}`));
  } catch (err) { setStatus(err.message); }
});
els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!current) return;
  const id = annotator();
  if (!id) return setStatus("请先填写标注员 ID");
  const form = new FormData(els.form);
  const labels = {};
  for (const field of current.tiebreak_fields) {
    labels[field] = form.get(field) || "";
    if (!labels[field]) return setStatus(`请选择 ${field}`);
  }
  try {
    renderItem(await api("/api/submit", {annotator_id: id, source_annotation_id: current.source_annotation_id, labels}));
    setStatus("已提交，请领取下一条");
  } catch (err) { setStatus(err.message); }
});
els.download.addEventListener("click", () => { location.href = "/download-annotations"; });
api("/api/stats").then(renderItem).catch(err => setStatus(err.message));
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    store: TiebreakStore

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                data = HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif parsed.path == "/api/stats":
                self._json(HTTPStatus.OK, self.store.stats())
            elif parsed.path == "/api/next":
                query = parse_qs(parsed.query)
                annotator_id = (query.get("annotator_id") or [""])[0].strip()
                self._json(HTTPStatus.OK, self.store.claim_next(annotator_id))
            elif parsed.path == "/download-annotations":
                self._send_file(self.store.annotations_path)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/submit":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = self.store.submit(
                str(payload.get("source_annotation_id", "")).strip(),
                str(payload.get("annotator_id", "")).strip(),
                payload.get("labels") or {},
            )
            self._json(HTTPStatus.OK, result)
        except Exception as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--gold-csv", type=Path, default=DEFAULT_GOLD_CSV)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    Handler.store = TiebreakStore(args.csv, args.gold_csv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Tiebreak annotating: {args.csv}")
    print(f"Gold: {args.gold_csv}")
    print(f"Annotations: {Handler.store.annotations_path}")
    print(f"Listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
