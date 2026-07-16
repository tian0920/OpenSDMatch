#!/usr/bin/env python3
"""Summarize evaluation metric JSON files into filterable tables."""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import math
import re
import socket
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVAL_DIR = ROOT / "model_test" / "eval_results"
DEFAULT_OUTPUT_BASENAME = "eval_metrics_summary"


def find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def get_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Model names or shell-style patterns to include, e.g. qwen3-* api_*.",
    )
    parser.add_argument(
        "--metrics",
        nargs="*",
        default=None,
        help=(
            "Metric names or shell-style patterns to include, e.g. "
            "task_2_binary_opportunity_detection.* *.macro_f1."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for saved CSV files. Defaults to --eval-dir.",
    )
    parser.add_argument("--output-basename", default=DEFAULT_OUTPUT_BASENAME)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--share",
        action="store_true",
        help="Allow access from other machines by binding to 0.0.0.0.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Start the web page server without opening a browser automatically.",
    )
    parser.add_argument(
        "--export-static",
        action="store_true",
        help="Write CSV/HTML/JSON files once and exit instead of starting the web page server.",
    )
    parser.add_argument("--csv", type=Path, default=None, help="CSV output path for --export-static.")
    parser.add_argument("--html", type=Path, default=None, help="HTML output path for --export-static.")
    parser.add_argument(
        "--json",
        dest="output_json",
        type=Path,
        default=None,
        help="JSON output path for --export-static.",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Print available models and exit without writing files.",
    )
    parser.add_argument(
        "--list-metrics",
        action="store_true",
        help="Print available metrics and exit without writing files.",
    )
    return parser.parse_args()


def model_name_from_path(path: Path) -> str:
    stem = path.stem
    if stem.endswith(".metrics"):
        stem = stem[: -len(".metrics")]
    suffix = "_gold"
    return stem[: -len(suffix)] if stem.endswith(suffix) else stem


def metric_sort_key(name: str) -> tuple[Any, ...]:
    order = {
        "metadata": 0,
        "task_1_opportunity_detection": 1,
        "task_1_match_classification": 1,
        "task_2_binary_opportunity_detection": 2,
        "task_2_binary_match_detection": 2,
        "task_3_opportunity_score": 3,
        "task_3_direction_reasoning": 3,
        "task_4_role_direction": 4,
        "task_4_cooperation_type_prediction": 4,
        "task_5_cooperation_type": 5,
        "task_5_joint_prediction": 5,
        "task_6_joint_prediction": 6,
        "task_6_reliability": 6,
        "task_7_reliability": 7,
    }
    first = name.split(".", 1)[0]
    return (order.get(first, 999), name)


def matches_any(value: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return True
    return any(value == pattern or fnmatch.fnmatch(value, pattern) for pattern in patterns)


def flatten_metrics(value: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}

    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flat.update(flatten_metrics(item, path))
        return flat

    if isinstance(value, list):
        if prefix.endswith(("missing_predictions", "invalid_predictions")):
            flat[f"{prefix}.count"] = len(value)
            return flat

        if all(isinstance(item, dict) for item in value):
            for index, item in enumerate(value):
                label = item.get("confidence", index) if isinstance(item, dict) else index
                path = f"{prefix}.confidence_{label}" if "confidence" in item else f"{prefix}.{index}"
                flat.update(flatten_metrics(item, path))
            return flat

        if all(isinstance(item, list) for item in value):
            for row_index, row in enumerate(value):
                for col_index, item in enumerate(row):
                    flat.update(flatten_metrics(item, f"{prefix}.row_{row_index}.col_{col_index}"))
            return flat

        flat[f"{prefix}.count"] = len(value)
        return flat

    if isinstance(value, (str, int, float, bool)) or value is None:
        flat[prefix] = value
    return flat


def load_rows(eval_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(eval_dir.glob("*.metrics.json")):
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        rows.append(
            {
                "model": model_name_from_path(path),
                "path": path,
                "metrics": flatten_metrics(data),
            }
        )
    return rows


def filtered_table(
    rows: list[dict[str, Any]],
    model_patterns: list[str] | None,
    metric_patterns: list[str] | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    selected_rows = [row for row in rows if matches_any(row["model"], model_patterns)]
    all_metrics = sorted(
        {metric for row in rows for metric in row["metrics"]},
        key=metric_sort_key,
    )
    selected_metrics = [
        metric for metric in all_metrics if matches_any(metric, metric_patterns)
    ]
    return selected_metrics, selected_rows


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return f"{value:.6g}"
    return str(value)


def write_csv(path: Path, metrics: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", *metrics])
        for row in rows:
            writer.writerow(
                [row["model"], *[format_value(row["metrics"].get(metric)) for metric in metrics]]
            )


def write_json(path: Path, metrics: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_payload(metrics, rows), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_markdown(path: Path, metrics: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["model", *metrics]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        values = [row["model"], *[format_value(row["metrics"].get(metric)) for metric in metrics]]
        escaped = [value.replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_payload(metrics: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    table_rows = [
        {
            "model": row["model"],
            "metrics": {metric: format_value(row["metrics"].get(metric)) for metric in metrics},
        }
        for row in rows
    ]
    return {
        "models": [row["model"] for row in rows],
        "metrics": metrics,
        "rows": table_rows,
    }


def build_html(metrics: list[str], rows: list[dict[str, Any]], default_csv_name: str) -> str:
    payload = build_payload(metrics, rows)
    payload = {
        **payload,
        "defaultCsvName": default_csv_name,
    }
    payload_json = (
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Eval Metrics Summary</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #5d6b7a;
      --line: #d9e0e7;
      --accent: #1264a3;
      --accent-soft: #e8f2fb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
    }}
    header {{
      padding: 22px 28px 14px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .subtle {{ color: var(--muted); }}
    .top-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    .save-tools {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .save-tools input {{
      width: 230px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 9px;
      font: inherit;
    }}
    .primary {{
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }}
    .primary:hover {{
      color: #fff;
      background: #0d558c;
    }}
    #save-status {{
      min-width: 180px;
      color: var(--muted);
    }}
    main {{
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      gap: 18px;
      padding: 18px;
    }}
    aside {{
      align-self: start;
      display: grid;
      gap: 14px;
      position: sticky;
      top: 18px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 0;
    }}
    .filter-panel {{ padding: 14px; }}
    .panel-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 10px;
      font-weight: 650;
    }}
    .actions {{ display: flex; gap: 6px; }}
    button {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 5px 8px;
      cursor: pointer;
      font: inherit;
    }}
    button:hover {{ border-color: var(--accent); color: var(--accent); }}
    input[type="search"] {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 9px;
      margin-bottom: 8px;
      font: inherit;
    }}
    .check-list {{
      max-height: 260px;
      overflow: auto;
      display: grid;
      gap: 6px;
      padding-right: 3px;
    }}
    label {{
      display: grid;
      grid-template-columns: 18px minmax(0, 1fr);
      gap: 8px;
      align-items: start;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }}
    .table-wrap {{
      overflow: auto;
      max-height: calc(100vh - 126px);
    }}
    table {{
      border-collapse: separate;
      border-spacing: 0;
      min-width: 100%;
      width: max-content;
    }}
    th, td {{
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      white-space: nowrap;
      text-align: right;
    }}
    th:first-child, td:first-child {{
      position: sticky;
      left: 0;
      z-index: 1;
      text-align: left;
      background: #fff;
      font-weight: 650;
    }}
    th {{
      position: sticky;
      top: 0;
      z-index: 2;
      max-width: 260px;
      background: var(--accent-soft);
      color: #0d3f66;
      font-weight: 650;
      text-align: left;
    }}
    th:first-child {{ z-index: 3; background: var(--accent-soft); }}
    .empty {{
      padding: 28px;
      color: var(--muted);
      text-align: center;
    }}
    @media (max-width: 900px) {{
      main {{ grid-template-columns: 1fr; }}
      aside {{ position: static; }}
      .table-wrap {{ max-height: none; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="top-row">
      <div>
        <h1>Eval Metrics Summary</h1>
        <div class="subtle">模型和指标均可勾选筛选，表格会即时更新。</div>
      </div>
      <div class="save-tools">
        <input id="csv-name" value="{default_csv_name}" aria-label="CSV 文件名">
        <button type="button" class="primary" id="save-csv">保存 CSV</button>
        <span id="save-status"></span>
      </div>
    </div>
  </header>
  <main>
    <aside>
      <section class="filter-panel">
        <div class="panel-title">
          <span>模型</span>
          <span class="actions">
            <button type="button" data-action="all-models">全选</button>
            <button type="button" data-action="none-models">清空</button>
          </span>
        </div>
        <input type="search" id="model-search" placeholder="搜索模型">
        <div id="model-list" class="check-list"></div>
      </section>
      <section class="filter-panel">
        <div class="panel-title">
          <span>指标</span>
          <span class="actions">
            <button type="button" data-action="all-metrics">全选</button>
            <button type="button" data-action="none-metrics">清空</button>
          </span>
        </div>
        <input type="search" id="metric-search" placeholder="搜索指标">
        <div id="metric-list" class="check-list"></div>
      </section>
    </aside>
    <section>
      <div class="table-wrap">
        <table id="metrics-table"></table>
        <div id="empty" class="empty" hidden>请选择至少一个模型和一个指标。</div>
      </div>
    </section>
  </main>
  <script id="metrics-data" type="application/json">{payload_json}</script>
  <script>
    const data = JSON.parse(document.getElementById('metrics-data').textContent);
    const state = {{
      models: new Set(data.models),
      metrics: new Set(data.metrics)
    }};

    function makeCheckbox(containerId, values, group) {{
      const container = document.getElementById(containerId);
      container.innerHTML = '';
      values.forEach((value) => {{
        const label = document.createElement('label');
        label.dataset.value = value.toLowerCase();
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = true;
        input.value = value;
        input.addEventListener('change', () => {{
          input.checked ? state[group].add(value) : state[group].delete(value);
          renderTable();
        }});
        const span = document.createElement('span');
        span.textContent = value;
        label.append(input, span);
        container.append(label);
      }});
    }}

    function applySearch(inputId, listId) {{
      const query = document.getElementById(inputId).value.trim().toLowerCase();
      document.querySelectorAll(`#${{listId}} label`).forEach((label) => {{
        label.hidden = query && !label.dataset.value.includes(query);
      }});
    }}

    function setGroup(group, checked) {{
      state[group] = checked ? new Set(data[group]) : new Set();
      document
        .querySelectorAll(`#${{group === 'models' ? 'model-list' : 'metric-list'}} input`)
        .forEach((input) => {{ input.checked = checked; }});
      renderTable();
    }}

    function renderTable() {{
      const models = data.models.filter((model) => state.models.has(model));
      const metrics = data.metrics.filter((metric) => state.metrics.has(metric));
      const table = document.getElementById('metrics-table');
      const empty = document.getElementById('empty');
      table.innerHTML = '';

      if (!models.length || !metrics.length) {{
        empty.hidden = false;
        return;
      }}
      empty.hidden = true;

      const thead = document.createElement('thead');
      const headerRow = document.createElement('tr');
      ['model', ...metrics].forEach((heading) => {{
        const th = document.createElement('th');
        th.textContent = heading;
        headerRow.append(th);
      }});
      thead.append(headerRow);

      const tbody = document.createElement('tbody');
      data.rows
        .filter((row) => state.models.has(row.model))
        .forEach((row) => {{
          const tr = document.createElement('tr');
          const modelCell = document.createElement('td');
          modelCell.textContent = row.model;
          tr.append(modelCell);
          metrics.forEach((metric) => {{
            const td = document.createElement('td');
            td.textContent = row.metrics[metric] ?? '';
            tr.append(td);
          }});
          tbody.append(tr);
        }});

      table.append(thead, tbody);
    }}

    async function saveCsv() {{
      const models = data.models.filter((model) => state.models.has(model));
      const metrics = data.metrics.filter((metric) => state.metrics.has(metric));
      const status = document.getElementById('save-status');
      const filename = document.getElementById('csv-name').value.trim() || data.defaultCsvName;
      if (!models.length || !metrics.length) {{
        status.textContent = '请至少选择一个模型和一个指标';
        return;
      }}
      status.textContent = '保存中...';
      try {{
        const response = await fetch('/save-csv', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ models, metrics, filename }})
        }});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || '保存失败');
        status.textContent = `已保存：${{result.path}}`;
      }} catch (error) {{
        status.textContent = error.message;
      }}
    }}

    makeCheckbox('model-list', data.models, 'models');
    makeCheckbox('metric-list', data.metrics, 'metrics');
    renderTable();
    document.getElementById('model-search').addEventListener('input', () => applySearch('model-search', 'model-list'));
    document.getElementById('metric-search').addEventListener('input', () => applySearch('metric-search', 'metric-list'));
    document.querySelector('[data-action="all-models"]').addEventListener('click', () => setGroup('models', true));
    document.querySelector('[data-action="none-models"]').addEventListener('click', () => setGroup('models', false));
    document.querySelector('[data-action="all-metrics"]').addEventListener('click', () => setGroup('metrics', true));
    document.querySelector('[data-action="none-metrics"]').addEventListener('click', () => setGroup('metrics', false));
    document.getElementById('save-csv').addEventListener('click', saveCsv);
  </script>
</body>
</html>
"""
    return document


def write_html(path: Path, metrics: list[str], rows: list[dict[str, Any]], default_csv_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_html(metrics, rows, default_csv_name), encoding="utf-8")


def sanitize_csv_name(name: str) -> str:
    name = Path(name.strip() or f"{DEFAULT_OUTPUT_BASENAME}.csv").name
    name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name)
    if not name.endswith(".csv"):
        name += ".csv"
    return name


def serve_report(
    args: argparse.Namespace,
    metrics: list[str],
    rows: list[dict[str, Any]],
) -> None:
    output_dir = args.output_dir or args.eval_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    default_csv_name = f"{args.output_basename}.csv"
    html_document = build_html(metrics, rows, default_csv_name)
    row_by_model = {row["model"]: row for row in rows}
    metric_set = set(metrics)

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path not in {"/", "/index.html"}:
                self.send_error(404)
                return
            body = html_document.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path != "/save-csv":
                self.send_error(404)
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                requested_models = request.get("models") or []
                requested_metrics = request.get("metrics") or []
                selected_rows = [
                    row_by_model[model]
                    for model in requested_models
                    if model in row_by_model
                ]
                selected_metrics = [
                    metric for metric in requested_metrics if metric in metric_set
                ]
                if not selected_rows or not selected_metrics:
                    self._send_json(400, {"error": "请至少选择一个模型和一个指标。"})
                    return

                csv_path = output_dir / sanitize_csv_name(str(request.get("filename") or default_csv_name))
                write_csv(csv_path, selected_metrics, selected_rows)
                self._send_json(200, {"path": str(csv_path)})
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:
            return

    bind_host = "0.0.0.0" if args.share else args.host
    try:
        server = ThreadingHTTPServer((bind_host, args.port), Handler)
    except OSError as exc:
        if exc.errno != 98 or args.port == 0:
            raise
        fallback_port = find_free_port(bind_host)
        print(f"Port {args.port} is in use; using {fallback_port} instead.")
        server = ThreadingHTTPServer((bind_host, fallback_port), Handler)
    actual_host, actual_port = server.server_address
    browser_host = "127.0.0.1" if actual_host in {"", "0.0.0.0"} else actual_host
    url = f"http://{browser_host}:{actual_port}/"
    print(f"Serving eval metrics page at {url}")
    if args.share:
        lan_ip = get_lan_ip()
        if lan_ip:
            print(f"LAN URL: http://{lan_ip}:{actual_port}/")
        print("For public sharing, use your server public IP and make sure the port is open.")
    print("Press Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


def main() -> int:
    args = parse_args()
    rows = load_rows(args.eval_dir)
    metrics, selected_rows = filtered_table(rows, args.models, args.metrics)

    if args.list_models:
        print("\n".join(row["model"] for row in rows))
        return 0

    if args.list_metrics:
        print("\n".join(metrics))
        return 0

    if args.export_static:
        output_dir = args.output_dir or args.eval_dir
        csv_path = args.csv or output_dir / f"{args.output_basename}.csv"
        html_path = args.html or output_dir / f"{args.output_basename}.html"
        json_path = args.output_json or output_dir / f"{args.output_basename}.json"
        default_csv_name = f"{args.output_basename}.csv"

        write_csv(csv_path, metrics, selected_rows)
        write_json(json_path, metrics, selected_rows)
        write_html(html_path, metrics, selected_rows, default_csv_name)

        print(f"Wrote CSV: {csv_path}")
        print(f"Wrote JSON: {json_path}")
        print(f"Wrote HTML: {html_path}")
        print(f"Models: {len(selected_rows)}")
        print(f"Metrics: {len(metrics)}")
        return 0

    serve_report(args, metrics, selected_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
