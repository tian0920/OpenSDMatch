#!/usr/bin/env python3
"""Predict labeled gold rows with Alibaba Model Studio / DashScope OpenAI-compatible SDK.

The script appends JSONL records and skips annotation_ids that already exist in
the output file, so it can be rerun safely after adding more gold rows.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "model_test" / "gold" / "annotation_pairs_test.csv"
DEFAULT_PROMPT = ROOT / "model_test" / "prompts" / "sd_model_predict_label"
DEFAULT_OUTPUT_DIR = ROOT / "model_test" / "model_outputs"
DEFAULT_BASE_URL = "https://llm-jhxtd03gjg0gd2o2.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODELS = [
    # "deepseek-v3.2",
    # "qwen3.6-35b-a3b",
    # "qwen3-vl-8b-instruct",
    # "qwen3.6-max-preview",
    # "qwen3.7-plus",
    # "qwen3.6-27b",
    # "glm-5.2",
    "kimi-k2.7-code",
    # "glm-5.1",
    # "deepseek-v4-flash",
]

LABEL_COLUMNS = [
    "has_opportunity",
    "opportunity_score",
    "cooperation_type",
    "role_direction",
    "confidence",
]

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
RETRIABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
COMPACT_FIELDS = ["annotation_id", "model", "gold", "prediction"]
OpenAI = Any
APIConnectionError: type[Exception]
APIStatusError: type[Exception]
APITimeoutError: type[Exception]
OpenAIError: type[Exception]


class ApiRequestError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def ensure_openai_sdk() -> None:
    global APIConnectionError, APIStatusError, APITimeoutError, OpenAI, OpenAIError
    try:
        from openai import APIConnectionError as _APIConnectionError
        from openai import APIStatusError as _APIStatusError
        from openai import APITimeoutError as _APITimeoutError
        from openai import OpenAI as _OpenAI
        from openai import OpenAIError as _OpenAIError
    except ModuleNotFoundError as exc:
        raise SystemExit("Missing dependency: install with `python -m pip install openai`.") from exc

    APIConnectionError = _APIConnectionError
    APIStatusError = _APIStatusError
    APITimeoutError = _APITimeoutError
    OpenAI = _OpenAI
    OpenAIError = _OpenAIError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--input-encoding", default="utf-8-sig")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--compact-output", type=Path, default=None)
    parser.add_argument(
        "--model",
        "--models",
        dest="models",
        action="append",
        metavar="MODEL",
        default=None,
        help="Model name. Can be repeated or comma-separated. Defaults to DEFAULT_MODELS.",
    )
    parser.add_argument("--base-url", default=os.environ.get("API_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument(
        "--api-key-env",
        default=os.environ.get("API_KEY_ENV"),
        help="Environment variable containing the API key. Auto-detected from --base-url if omitted.",
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between requests.")
    parser.add_argument("--json-mode", action="store_true", help="Request response_format=json_object.")
    parser.add_argument(
        "--thinking",
        choices=["enabled", "disabled"],
        default="disabled",
        help="Alibaba Model Studio deep-thinking switch. Mapped to extra_body={'enable_thinking': ...}.",
    )
    parser.add_argument("--reasoning-effort", choices=["high", "max"], default=None)
    parser.add_argument("--stream", action="store_true", help="Use streaming chat completions.")
    parser.add_argument("--retry-errors", action="store_true", help="Do not skip existing rows with parse/API errors.")
    parser.add_argument("--dry-run", action="store_true", help="Only print row counts and output path.")
    return parser.parse_args()


def parse_model_list(values: list[str] | None) -> list[str]:
    if not values:
        return DEFAULT_MODELS
    models: list[str] = []
    for value in values:
        models.extend(model.strip() for model in value.split(",") if model.strip())
    return models


def infer_api_key_env(base_url: str) -> str:
    lowered = base_url.lower()
    if "aliyuncs.com" in lowered or "dashscope" in lowered:
        return "DASHSCOPE_API_KEY"
    if "deepseek.com" in lowered:
        return "DEEPSEEK_API_KEY"
    if "openrouter.ai" in lowered:
        return "OPENROUTER_API_KEY"
    return "API_KEY"


def masked_key(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def auth_error_hint(base_url: str, api_key_env: str) -> str:
    lowered = base_url.lower()
    if "aliyuncs.com" in lowered or "dashscope" in lowered:
        return (
            "Alibaba Model Studio returned an authentication error. "
            f"Verify that {api_key_env} is a Model Studio API key, not an AccessKey secret; "
            "verify there are no extra spaces/newlines; and verify the key type matches the endpoint. "
            "General Singapore DashScope keys usually use "
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1, while dedicated plan/workspace keys "
            "must use their matching dedicated endpoint."
        )
    if "deepseek.com" in lowered:
        return "DeepSeek returned an authentication error. Verify DEEPSEEK_API_KEY and account status."
    return "The provider returned an authentication error. Verify the API key and base URL belong together."


def api_error_hint(error: str, base_url: str, api_key_env: str) -> str:
    lowered = error.lower()
    if "free quota has been exhausted" in lowered or "quota" in lowered:
        return (
            "The provider says the free quota is exhausted. Add billing/payment information, "
            "use a paid-enabled key/workspace, switch to another provider/model, or wait for quota renewal. "
            "If you changed keys, make sure the new key and endpoint belong to the same Alibaba Model Studio "
            "workspace/plan."
        )
    return auth_error_hint(base_url, api_key_env)


def fatal_api_error_label(error: str) -> str:
    lowered = error.lower()
    if "free quota has been exhausted" in lowered or "quota" in lowered:
        return "quota/billing error"
    if "authentication" in lowered or "unauthorized" in lowered or "invalid api key" in lowered:
        return "authentication error"
    return "permission error"


def safe_model_name(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_") or "model"


def default_output_path(output_dir: Path, model: str) -> Path:
    return output_dir / f"api_{safe_model_name(model)}_annotation_pairs_test.jsonl"


def default_compact_output_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.compact{output_path.suffix}")


def compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record.get(field) for field in COMPACT_FIELDS}


def load_gold_rows(path: Path, encoding: str) -> list[dict[str, str]]:
    with path.open(newline="", encoding=encoding) as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if is_labeled_row(row)]


def is_labeled_row(row: dict[str, str]) -> bool:
    return bool((row.get("has_opportunity") or row.get("label_match") or "").strip())


def load_completed_ids(path: Path, retry_errors: bool) -> set[str]:
    completed: set[str] = set()
    if not path.exists():
        return completed
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            annotation_id = record.get("annotation_id")
            if not annotation_id:
                continue
            has_error = bool(record.get("api_error") or record.get("parse_error"))
            if retry_errors and has_error:
                continue
            completed.add(annotation_id)
    return completed


def build_prompt(template: str, row: dict[str, str]) -> str:
    return (
        template.replace("{object_a_profile}", row.get("object_a_profile", ""))
        .replace("{object_b_profile}", row.get("object_b_profile", ""))
    )


def extract_json(text: str) -> dict[str, Any]:
    match = JSON_OBJECT_RE.search(text)
    if not match:
        raise ValueError("no JSON object found in model content")
    return json.loads(match.group(0))


def openai_object_to_dict(value: Any) -> Any:
    """Convert OpenAI SDK pydantic objects to plain Python data when possible."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [openai_object_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: openai_object_to_dict(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def format_openai_error(exc: Exception) -> tuple[str, int | None]:
    status_code = getattr(exc, "status_code", None)

    if isinstance(exc, APIStatusError):
        body = getattr(exc, "body", None)
        if body is None:
            try:
                body = exc.response.text
            except Exception:
                body = str(exc)
        if not isinstance(body, str):
            body = json.dumps(body, ensure_ascii=False)
        return f"HTTP {exc.status_code}: {body[:1000]}", exc.status_code

    return f"{type(exc).__name__}: {str(exc)[:1000]}", status_code


def create_client(args: argparse.Namespace, api_key: str) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url=args.base_url,
        timeout=args.timeout,
        # We do retry outside so that auth/permission errors can stop immediately
        # and the JSONL record can be written consistently.
        max_retries=0,
    )


def build_create_kwargs(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": args.stream,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }
    if args.stream:
        # Ask streaming responses to include usage when the provider supports it.
        kwargs["stream_options"] = {"include_usage": True}

    if args.json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    # Alibaba Model Studio / DashScope official template uses:
    # extra_body={"enable_thinking": True}
    extra_body: dict[str, Any] = {
        "enable_thinking": args.thinking == "enabled",
    }
    if args.reasoning_effort:
        extra_body["reasoning_effort"] = args.reasoning_effort
    kwargs["extra_body"] = extra_body

    return kwargs


def get_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def non_stream_chat_completion(client: OpenAI, args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    completion = client.chat.completions.create(**build_create_kwargs(args, prompt))
    response = openai_object_to_dict(completion)
    choices = response.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}

    return {
        "id": response.get("id"),
        "usage": response.get("usage"),
        "choices": [
            {
                "finish_reason": choice.get("finish_reason"),
                "message": {
                    "content": (message.get("content") or "").strip(),
                    "reasoning_content": message.get("reasoning_content"),
                },
            }
        ],
        "response_debug": response,
    }


def stream_chat_completion(client: OpenAI, args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    """Call the OpenAI-compatible SDK exactly like the Alibaba template and merge stream chunks."""
    raw_content_parts: list[str] = []
    reasoning_content_parts: list[str] = []
    response_id: str | None = None
    finish_reason: str | None = None
    usage: Any = None
    chunk_debug: list[Any] = []

    completion = client.chat.completions.create(**build_create_kwargs(args, prompt))

    for chunk in completion:
        chunk_dict = openai_object_to_dict(chunk)
        if len(chunk_debug) < 5:
            chunk_debug.append(chunk_dict)
        response_id = response_id or get_value(chunk, "id")

        chunk_usage = get_value(chunk, "usage")
        if chunk_usage is not None:
            usage = chunk_usage

        choices = get_value(chunk, "choices") or []
        if not choices:
            continue

        choice = choices[0]
        choice_finish_reason = get_value(choice, "finish_reason")
        if choice_finish_reason:
            finish_reason = choice_finish_reason

        delta = get_value(choice, "delta")
        if delta is None:
            continue

        reasoning_content = get_value(delta, "reasoning_content")
        if reasoning_content is not None:
            reasoning_content_parts.append(reasoning_content)

        content = get_value(delta, "content")
        if content:
            raw_content_parts.append(content)

    return {
        "id": response_id,
        "usage": openai_object_to_dict(usage),
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {
                    "content": "".join(raw_content_parts).strip(),
                    "reasoning_content": "".join(reasoning_content_parts) or None,
                },
            }
        ],
        "response_debug": {"first_stream_chunks": chunk_debug},
    }


def call_with_retries(
    client: OpenAI,
    args: argparse.Namespace,
    prompt: str,
) -> dict[str, Any]:
    last_error: str | None = None
    last_status_code: int | None = None

    for attempt in range(args.retries + 1):
        try:
            if args.stream:
                return stream_chat_completion(client, args, prompt)
            return non_stream_chat_completion(client, args, prompt)
        except (APIStatusError, APIConnectionError, APITimeoutError, OpenAIError) as exc:
            last_error, last_status_code = format_openai_error(exc)
            if last_status_code not in RETRIABLE_STATUS_CODES:
                raise ApiRequestError(last_error, last_status_code) from exc
        except (TimeoutError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            last_status_code = None

        if attempt < args.retries:
            time.sleep(min(60, 2**attempt))

    raise ApiRequestError(last_error or "unknown API error", last_status_code)


def normalize_role_direction(value: str) -> str:
    mapping = {
        "A supplies B": "A_to_B",
        "A_supplies_B": "A_to_B",
        "B supplies A": "B_to_A",
        "B_supplies_A": "B_to_A",
        "Unclear / Not applicable": "None",
    }
    return mapping.get(value.strip(), value.strip())


def normalize_cooperation_type(value: str) -> str:
    mapping = {
        "None": "None",
        "不适用": "None",
        "不匹配": "None",
    }
    return mapping.get(value.strip(), value.strip())


def gold_labels(row: dict[str, str]) -> dict[str, Any]:
    labels = {
        "has_opportunity": (row.get("has_opportunity") or "").strip(),
        "opportunity_score": (row.get("opportunity_score") or "").strip(),
        "cooperation_type": (row.get("cooperation_type") or "").strip(),
        "role_direction": (row.get("role_direction") or "").strip(),
        "confidence": (row.get("confidence") or "").strip(),
    }
    if not labels["has_opportunity"] and (row.get("label_match") or "").strip():
        label_match = (row.get("label_match") or "").strip()
        labels["has_opportunity"] = "No" if label_match == "0" else "Yes"
        labels["opportunity_score"] = "None" if label_match == "0" else label_match
        labels["cooperation_type"] = normalize_cooperation_type(row.get("label_cooperation_type") or "")
        labels["role_direction"] = normalize_role_direction(row.get("label_direction") or "")
        labels["confidence"] = (row.get("label_confidence") or "").strip()
    labels["role_direction_normalized"] = normalize_role_direction(labels["role_direction"])
    labels["cooperation_type_normalized"] = normalize_cooperation_type(labels["cooperation_type"])
    return labels


def run_model(args: argparse.Namespace, model: str) -> None:
    args.model = model
    if not args.api_key_env:
        args.api_key_env = infer_api_key_env(args.base_url)
    output_path = args.output or default_output_path(args.output_dir, model)
    compact_output_path = args.compact_output or default_compact_output_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    compact_output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = load_gold_rows(args.input, args.input_encoding)
    completed_ids = load_completed_ids(output_path, args.retry_errors)
    pending_rows = [row for row in rows if row.get("annotation_id") not in completed_ids]
    if args.limit is not None:
        pending_rows = pending_rows[: args.limit]

    print(f"input labeled rows: {len(rows)}")
    print(f"already completed: {len(completed_ids)}")
    print(f"pending this run: {len(pending_rows)}")
    print(f"model: {model}")
    print(f"base_url: {args.base_url}")
    print(f"api_key_env: {args.api_key_env}")
    print(f"thinking: {args.thinking}")
    print(f"output_raw: {output_path}")
    print(f"output_compact: {compact_output_path}")
    if args.dry_run or not pending_rows:
        return 0

    api_key = args.api_key or os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"Missing API key. Set {args.api_key_env} or pass --api-key.")
    print(f"api_key: {masked_key(api_key)}")

    ensure_openai_sdk()
    client = create_client(args, api_key)
    template = args.prompt.read_text(encoding="utf-8")

    with output_path.open("a", encoding="utf-8") as out, compact_output_path.open("a", encoding="utf-8") as compact_out:
        for index, row in enumerate(pending_rows, 1):
            annotation_id = row.get("annotation_id")
            prompt = build_prompt(template, row)
            started_at = time.time()
            api_error = None
            parse_error = None
            prediction = None
            raw_content = ""
            finish_reason = None
            response_id = None
            usage = None
            reasoning_content = None
            response_debug = None

            stop_after_record = False
            try:
                response = call_with_retries(client, args, prompt)
                response_id = response.get("id")
                usage = response.get("usage")
                response_debug = response.get("response_debug")
                choice = (response.get("choices") or [{}])[0]
                finish_reason = choice.get("finish_reason")
                message = choice.get("message") or {}
                raw_content = (message.get("content") or "").strip()
                reasoning_content = message.get("reasoning_content")
                try:
                    prediction = extract_json(raw_content)
                except Exception as exc:
                    parse_error = str(exc)
            except ApiRequestError as exc:
                api_error = str(exc)
                stop_after_record = exc.status_code in {401, 403}
            except Exception as exc:
                api_error = f"{type(exc).__name__}: {exc}"

            record = {
                "annotation_id": annotation_id,
                "model": model,
                "base_url": args.base_url,
                "gold": gold_labels(row),
                "prediction": prediction,
                "parse_error": parse_error,
                "api_error": api_error,
                "raw_output": raw_content,
                "reasoning_content": reasoning_content,
                "finish_reason": finish_reason,
                "usage": usage,
                "api_response_id": response_id,
                "response_debug": response_debug,
                "elapsed_seconds": round(time.time() - started_at, 3),
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            compact_out.write(json.dumps(compact_record(record), ensure_ascii=False) + "\n")
            compact_out.flush()

            if api_error:
                status = f"api_error {api_error[:160]}"
            elif parse_error:
                if not raw_content:
                    status = f"empty_content finish_reason={finish_reason}"
                else:
                    status = f"parse_error {parse_error[:160]}"
            else:
                status = "ok"
            print(f"[{index}/{len(pending_rows)}] {annotation_id} {status}")
            if stop_after_record:
                raise SystemExit(
                    f"Stopping after {fatal_api_error_label(api_error)}. "
                    f"Check your API key in {args.api_key_env} or pass --api-key.\n"
                    + api_error_hint(api_error, args.base_url, args.api_key_env)
                )
            if args.sleep:
                time.sleep(args.sleep)


def main() -> int:
    args = parse_args()
    models = parse_model_list(args.models)
    if not models:
        raise SystemExit("Missing --model.")
    if len(models) > 1 and (args.output or args.compact_output):
        raise SystemExit("--output and --compact-output can only be used with one model.")

    print(f"models: {', '.join(models)}")
    for index, model in enumerate(models, 1):
        if len(models) > 1:
            print(f"\n=== model {index}/{len(models)}: {model} ===")
        run_model(args, model)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
