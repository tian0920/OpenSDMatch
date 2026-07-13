# Local model setup for `model_test`

This project stores downloaded Hugging Face models under:

```bash
/home/ecs-user/OpenSDMatch/models/hf/
```

Prediction outputs should go under:

```bash
/home/ecs-user/OpenSDMatch/model_test/model_outputs/
```

## Model aliases

| Alias | Hugging Face repo |
| --- | --- |
| `qwen3-4b` | `Qwen/Qwen3-4B` |
| `qwen3-8b` | `Qwen/Qwen3-8B` |
| `deepseek-r1-distill-qwen-7b` | `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` |
| `llama-3.1-8b-instruct` | `meta-llama/Llama-3.1-8B-Instruct` |
| `gemma-3-12b-it` | `google/gemma-3-12b-it` |

## Install download tooling

```bash
python -m pip install -r model_test/requirements-download.txt
```

Optional, usually faster:

```bash
export HF_HUB_ENABLE_HF_TRANSFER=1
```

## Login for gated models

`Llama-3.1-8B-Instruct` and `Gemma-3-12B-it` usually require a Hugging Face account, a token, and accepted model terms on their model pages.

```bash
huggingface-cli login
```

If you do not want interactive login:

```bash
export HF_TOKEN=hf_xxx
```

## Download models

Download all models:

```bash
python model_test/scripts/download_hf_models.py --model all
```

Download one model:

```bash
python model_test/scripts/download_hf_models.py --model qwen3-4b
```

Downloaded files are resumable. If the network disconnects, rerun the same command.

## Install inference tooling

The current machine does not expose an NVIDIA GPU. CPU inference for 7B-12B models will be very slow. For practical batch prediction, run this on a GPU machine with enough VRAM.

```bash
python -m pip install -r model_test/requirements-inference.txt
```

## Run gold predictions

The local prediction script uses the same evaluation slice as the API script:
`model_test/gold/annotation_pairs_test.csv`, filtered to rows where `has_opportunity` is non-empty.
The gold CSV is encoded as `utf-8-sig`, so the prediction script uses that by default.

```bash
python model_test/scripts/predict_local_hf.py --model qwen3-4b --limit 10
```

Full run:

```bash
python model_test/scripts/predict_local_hf.py \
  --models qwen3-4b,qwen3-8b,deepseek-r1-distill-qwen-7b,llama-3.1-8b-instruct
```

The generic prediction script is designed for text-generation CausalLM models. `google/gemma-3-12b-it` is a multimodal Gemma 3 model, so use a recent `transformers` version and verify loading on the target GPU host before running the full 10k-row batch.
