#!/usr/bin/env python3
"""Run local HF model predictions for labeled gold rows."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TYPE = "english"
DEFAULT_INPUT = ROOT / "model_test" / "gold" / TYPE / "annotation_pairs_test.csv"
DEFAULT_PROMPT = ROOT / "model_test" / "prompts" / TYPE / "sd_model_predict_label"
DEFAULT_MODEL_DIR = ROOT / "models" / "hf"
DEFAULT_OUTPUT_DIR = ROOT / "model_test" / "model_outputs" / TYPE
DEFAULT_MODELS = [
    # "deepseek-r1-distill-qwen-7b",
    # "DeepSeek-R1-Distill-Qwen-1.5B",
    # "gemma-3-12b-it",
    # "gemma-4-26B-A4B-it",
    # "qwen3-2b",
    # "phi-4",
    # "phi-4-mini-instruct",
    # "mistral-7b-instruct-v0.3",
    "mistral-small-3.2-24b-instruct",
    "qwen3-4b",
    "qwen3-8b",
    "llama-3.1-8b-instant",
    "Llama-3.2-3B-Instruct",
]
MODEL_REPO_HINTS = {
    "DeepSeek-R1-Distill-Qwen-1.5B": "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
    "deepseek-r1-distill-qwen-7b": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "gemma-3-12b-it": "google/gemma-3-12b-it",
    "gemma-4-26B-A4B-it": "google/gemma-4-26B-A4B-it",
    "llama-3.1-8b-instruct": "meta-llama/Llama-3.1-8B-Instruct",
    "Llama-3.2-3B-Instruct": "meta-llama/Llama-3.2-3B-Instruct",
    "mistral-7b-instruct-v0.3": "mistralai/Mistral-7B-Instruct-v0.3",
    "mistral-small-3.2-24b-instruct": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
    "phi-4": "microsoft/phi-4",
    "phi-4-mini-instruct": "microsoft/Phi-4-mini-instruct",
    "qwen3-2b": "Qwen/Qwen3-2B",
    "qwen3-4b": "Qwen/Qwen3-4B",
    "qwen3-8b": "Qwen/Qwen3-8B",
}
TOKENIZER_FILES = (
    "tokenizer.json",
    "tokenizer.model",
    "tokenizer_config.json",
    "spiece.model",
)

LABEL_COLUMNS = [
    "has_opportunity",
    "opportunity_score",
    "cooperation_type",
    "role_direction",
    "confidence",
]
COMPACT_FIELDS = ["annotation_id", "model", "gold", "prediction"]
JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        "--models",
        dest="models",
        action="append",
        metavar="MODEL",
        default=None,
        help=(
            "Model directory name under --model-dir, or a direct local model path. "
            "Can be repeated or comma-separated. Defaults to DEFAULT_MODELS."
        ),
    )
    parser.add_argument("--list-models", action="store_true", help="List discovered local models and exit.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--input-encoding", default="utf-8-sig")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--compact-output", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-new-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--device-map", default="auto")
    parser.add_argument("--trust-remote-code", action="store_true", default=True)
    return parser.parse_args()


def parse_model_list(values: list[str] | None) -> list[str]:
    if not values:
        return DEFAULT_MODELS
    models: list[str] = []
    for value in values:
        models.extend(model.strip() for model in value.split(",") if model.strip())
    return models


def discover_models(model_dir: Path) -> dict[str, Path]:
    if not model_dir.exists():
        return {}
    return {
        path.parent.name: path.parent
        for path in sorted(model_dir.glob("*/config.json"))
        if path.parent.is_dir()
    }


def local_model_missing_files(path: Path) -> list[str]:
    missing: list[str] = []
    if not (path / "config.json").exists():
        missing.append("config.json")
    if not any((path / name).exists() for name in TOKENIZER_FILES):
        missing.append("tokenizer files")
    return missing


def format_incomplete_model_error(model: str, path: Path, missing: list[str]) -> str:
    message = (
        f"Incomplete local model snapshot for {model}: {path}\n"
        f"Missing: {', '.join(missing)}"
    )
    if model in MODEL_REPO_HINTS:
        message += (
            "\nDownload it with:\n"
            f"  python model_test/scripts/download_hf_models.py --model {model}"
        )
    message += "\nFor gated models, make sure HF_TOKEN is set or `huggingface-cli login` has been run."
    return message


def ensure_local_model_ready(model: str, path: Path) -> Path:
    missing = local_model_missing_files(path)
    if missing:
        raise SystemExit(format_incomplete_model_error(model, path, missing))
    return path.resolve()


def resolve_model_path(model: str, model_dir: Path, discovered_models: dict[str, Path]) -> Path:
    candidate = Path(model).expanduser()
    if candidate.exists():
        return ensure_local_model_ready(model, candidate)
    if model in discovered_models:
        return discovered_models[model]
    candidate = model_dir / model
    if candidate.exists():
        return ensure_local_model_ready(model, candidate)
    available = ", ".join(discovered_models) or "(none)"
    raise SystemExit(f"Model not found: {model}\nDiscovered models under {model_dir}: {available}")


def safe_output_name(model_path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model_path.name).strip("_") or "model"


def default_output_path(output_dir: Path, model_name: str) -> Path:
    return output_dir / f"{model_name}_annotation_pairs_test.jsonl"


def default_compact_output_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.compact{output_path.suffix}")


def compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record.get(field) for field in COMPACT_FIELDS}


def load_rows(path: Path, encoding: str, limit: int | None) -> list[dict[str, str]]:
    with path.open(newline="", encoding=encoding) as handle:
        rows = list(csv.DictReader(handle))
    rows = [row for row in rows if is_labeled_row(row)]
    return rows if limit is None else rows[:limit]


def is_labeled_row(row: dict[str, str]) -> bool:
    return bool((row.get("has_opportunity") or row.get("label_match") or "").strip())


def extract_json(text: str) -> dict[str, Any]:
    match = JSON_OBJECT_RE.search(text)
    if not match:
        raise ValueError("no JSON object found")
    return json.loads(match.group(0))


def build_prompt(template: str, row: dict[str, str]) -> str:
    return (
        template.replace("{object_a_profile}", row.get("object_a_profile", ""))
        .replace("{object_b_profile}", row.get("object_b_profile", ""))
    )


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


def gold_labels(row: dict[str, str]) -> dict[str, Any] | None:
    if not is_labeled_row(row):
        return None
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


def model_type_from_config(model_path: Path) -> str | None:
    """Read model_type without instantiating a model or downloading anything."""
    try:
        with (model_path / "config.json").open(encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    model_type = config.get("model_type")
    return model_type if isinstance(model_type, str) else None


def build_mistral3_text_inputs(tokenizer: Any, prompt: str, torch: Any, device: Any) -> dict[str, Any]:
    """Encode a text-only Mistral3 turn with the official Tekken tokenizer."""
    from mistral_common.protocol.instruct.messages import UserMessage
    from mistral_common.protocol.instruct.request import ChatCompletionRequest

    request = ChatCompletionRequest(messages=[UserMessage(content=prompt)])
    tokenized = tokenizer.encode_chat_completion(request)
    input_tensor = torch.tensor([tokenized.tokens], dtype=torch.long, device=device)
    return {
        "input_ids": input_tensor,
        "attention_mask": torch.ones_like(input_tensor),
    }


def run_model(
    args: argparse.Namespace,
    model_arg: str,
    discovered_models: dict[str, Path],
    torch: Any,
    auto_model_for_causal_lm: Any,
    mistral3_for_conditional_generation: Any,
    auto_tokenizer: Any,
) -> None:
    model_path = resolve_model_path(model_arg, args.model_dir, discovered_models)
    model_name = safe_output_name(model_path)

    model_type = model_type_from_config(model_path)
    if model_type == "mistral3":
        try:
            from mistral_common.tokens.tokenizers.mistral import MistralTokenizer
        except ImportError as exc:
            raise SystemExit(
                "Mistral3 requires mistral-common>=1.6.2; install it with: "
                "python -m pip install 'mistral-common>=1.6.2'"
            ) from exc
        tokenizer = MistralTokenizer.from_file(model_path / "tekken.json")
    else:
        tokenizer = auto_tokenizer.from_pretrained(model_path, trust_remote_code=args.trust_remote_code)
    # Mistral Small 3.1/3.2 uses the multimodal Mistral3 architecture, whose
    # config is intentionally not registered with AutoModelForCausalLM.  Text-
    # only generation still works through Mistral3ForConditionalGeneration.
    model_class = (
        mistral3_for_conditional_generation
        if model_type == "mistral3"
        else auto_model_for_causal_lm
    )
    print(f"model_type: {model_type or 'unknown'}; loader: {model_class.__name__}")
    model = model_class.from_pretrained(
        model_path,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        device_map=args.device_map,
        trust_remote_code=args.trust_remote_code,
    )

    prompt_template = args.prompt.read_text(encoding="utf-8")
    rows = load_rows(args.input, args.input_encoding, args.limit)
    output_path = args.output or default_output_path(args.output_dir, model_name)
    compact_output_path = args.compact_output or default_compact_output_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    compact_output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"input labeled rows: {len(rows)}")
    print(f"model: {model_name}")
    print(f"model_path: {model_path}")
    print(f"output_raw: {output_path}")
    print(f"output_compact: {compact_output_path}")

    with output_path.open("w", encoding="utf-8") as out, compact_output_path.open("w", encoding="utf-8") as compact_out:
        for index, row in enumerate(rows, 1):
            prompt = build_prompt(prompt_template, row)
            if model_type == "mistral3":
                inputs = build_mistral3_text_inputs(tokenizer, prompt, torch, model.device)
            else:
                messages = [{"role": "user", "content": prompt}]
                text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = tokenizer([text], return_tensors="pt").to(model.device)
            generation_kwargs = {
                "max_new_tokens": args.max_new_tokens,
                "do_sample": args.temperature > 0,
                "pad_token_id": (
                    tokenizer.instruct_tokenizer.tokenizer.eos_id
                    if model_type == "mistral3"
                    else tokenizer.eos_token_id
                ),
            }
            if args.temperature > 0:
                generation_kwargs["temperature"] = args.temperature
            generated = model.generate(**inputs, **generation_kwargs)
            output_ids = generated[0][inputs["input_ids"].shape[-1] :]
            if model_type == "mistral3":
                raw = tokenizer.decode(output_ids.tolist()).strip()
            else:
                raw = tokenizer.decode(output_ids, skip_special_tokens=True).strip()
            try:
                prediction = extract_json(raw)
                parse_error = None
            except Exception as exc:  # keep bad outputs for debugging and later repair.
                prediction = None
                parse_error = str(exc)

            record = {
                "annotation_id": row.get("annotation_id"),
                "model": model_name,
                "base_url": None,
                "model_path": str(model_path),
                "gold": gold_labels(row),
                "prediction": prediction,
                "parse_error": parse_error,
                "api_error": None,
                "raw_output": raw,
                "reasoning_content": None,
                "finish_reason": None,
                "usage": None,
                "api_response_id": None,
                "response_debug": None,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            compact_out.write(json.dumps(compact_record(record), ensure_ascii=False) + "\n")
            compact_out.flush()
            print(f"[{index}/{len(rows)}] {row.get('annotation_id')} parse_error={parse_error}")

    print(f"Saved predictions to {output_path}")
    print(f"Saved compact predictions to {compact_output_path}")


def main() -> int:
    args = parse_args()
    discovered_models = discover_models(args.model_dir)
    if args.list_models:
        if not discovered_models:
            print(f"No local models found under {args.model_dir}")
            return 0
        print(f"Discovered local models under {args.model_dir}:")
        for name, path in discovered_models.items():
            print(f"- {name}: {path}")
        return 0

    models = parse_model_list(args.models)
    if not models:
        available = ", ".join(discovered_models) or "(none)"
        raise SystemExit(f"Missing --model. Discovered models under {args.model_dir}: {available}")
    if len(models) > 1 and (args.output or args.compact_output):
        raise SystemExit("--output and --compact-output can only be used with one model.")

    # Imported lazily so CSV/prompt validation still works before installing inference deps.
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, Mistral3ForConditionalGeneration

    print(f"models: {', '.join(models)}")
    for index, model_arg in enumerate(models, 1):
        if len(models) > 1:
            print(f"\n=== model {index}/{len(models)}: {model_arg} ===")
        run_model(
            args,
            model_arg,
            discovered_models,
            torch,
            AutoModelForCausalLM,
            Mistral3ForConditionalGeneration,
            AutoTokenizer,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
