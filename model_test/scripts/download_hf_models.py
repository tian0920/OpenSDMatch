#!/usr/bin/env python3
"""Download the local HF models used by model_test."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.errors import GatedRepoError, HfHubHTTPError, RepositoryNotFoundError


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_DIR = ROOT / "models" / "hf"

MODELS = {
    #"qwen3-4b": "Qwen/Qwen3-4B",
    #"qwen3-8b": "Qwen/Qwen3-8B",
    #"deepseek-r1-distill-qwen-7b": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    #"llama-3.1-8b-instruct": "meta-llama/Llama-3.1-8B-Instruct",
    "gemma-3-12b-it": "google/gemma-3-12b-it",
    "qwen3-2b": "Qwen/Qwen3-2B",
    "gemma-4-26B-A4B-it": "google/gemma-4-26B-A4B-it",
    "qwen3_6-27b": "Qwen/Qwen3.6-27B",
    "qwen3_5-27b": "Qwen/Qwen3.5-27B",
    "qwen3_5-2b": "Qwen/Qwen3.5-2B",
}

ALLOW_PATTERNS = [
    "*.json",
    "*.model",
    "*.safetensors",
    "*.txt",
    "*.tiktoken",
    "tokenizer*",
    "generation_config.json",
    "chat_template*",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        choices=["all", *MODELS.keys()],
        default="all",
        help="Model alias to download.",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=DEFAULT_MODEL_DIR,
        help="Directory where model snapshots are stored.",
    )
    parser.add_argument(
        "--revision",
        default=None,
        help="Optional HF revision, branch, tag, or commit hash.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("HF_TOKEN"),
        help="Hugging Face token. Defaults to HF_TOKEN.",
    )
    return parser.parse_args()


def download(alias: str, repo_id: str, model_dir: Path, revision: str | None, token: str | None) -> dict:
    target_dir = model_dir / alias
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n==> {alias}: {repo_id}")
    print(f"    saving to: {target_dir}")

    path = snapshot_download(
        repo_id=repo_id,
        revision=revision,
        local_dir=target_dir,
        allow_patterns=ALLOW_PATTERNS,
        token=token,
    )
    info = HfApi(token=token).model_info(repo_id, revision=revision)
    result = {
        "alias": alias,
        "repo_id": repo_id,
        "local_path": str(Path(path).resolve()),
        "revision": info.sha,
    }
    (target_dir / "opensdmatch_model_meta.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"    done: {result['revision']}")
    return result


def main() -> int:
    args = parse_args()
    args.model_dir.mkdir(parents=True, exist_ok=True)

    selected = MODELS.items() if args.model == "all" else [(args.model, MODELS[args.model])]
    failed: list[tuple[str, str]] = []

    for alias, repo_id in selected:
        try:
            download(alias, repo_id, args.model_dir, args.revision, args.token)
        except (GatedRepoError, RepositoryNotFoundError, HfHubHTTPError) as exc:
            failed.append((alias, str(exc).splitlines()[0]))
            print(f"    failed: {failed[-1][1]}")

    if failed:
        print("\nSome models were not downloaded:")
        for alias, reason in failed:
            print(f"- {alias}: {reason}")
        print("\nFor gated models, run `huggingface-cli login` or set HF_TOKEN after accepting the model terms.")
        return 1

    print("\nAll selected models downloaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
