# API prediction for gold rows

Use this script when you want to evaluate a hosted OpenAI-compatible model before running local models.

The script reads:

```bash
model_test/gold/annotation_pairs_test.csv
```

It only keeps rows where `has_opportunity` is non-empty. Current labeled gold rows: 359 replicate annotations.

Outputs are appended as JSONL under:

```bash
model_test/model_outputs/
```

Default output names include `annotation_pairs_test`, so the voted gold run does not collide with older `_gold.jsonl` experiments. Each run skips `annotation_id` values that already exist in its output file, so rerunning after adding more gold labels only processes new samples.

## DeepSeek R1

DeepSeek's API is OpenAI-compatible. The default script settings are:

- base URL: `https://api.deepseek.com`
- model: `deepseek-reasoner`

As of 2026-06-08, DeepSeek docs also list `deepseek-v4-pro` and `deepseek-v4-flash`; `deepseek-reasoner` is still available for compatibility but is marked for deprecation on 2026-07-24.

Set your key:

```bash
export DEEPSEEK_API_KEY=sk-...
```

Dry run:

```bash
python model_test/scripts/predict_api.py --dry-run
```

Test a small batch:

```bash
python model_test/scripts/predict_api.py --limit 5 --json-mode
```

Full gold run:

```bash
python model_test/scripts/predict_api.py --json-mode
```

To run multiple hosted models in sequence, repeat `--model` or pass a comma-separated list:

```bash
python model_test/scripts/predict_api.py \
  --models deepseek-v3.2,deepseek-v4-pro \
  --json-mode
```

## Change model or provider

Any OpenAI-compatible chat-completions provider can be used:

```bash
python model_test/scripts/predict_api.py \
  --base-url https://api.deepseek.com \
  --model deepseek-v4-pro \
  --thinking enabled \
  --reasoning-effort high \
  --json-mode
```

For another provider:

```bash
export OPENROUTER_API_KEY=...
python model_test/scripts/predict_api.py \
  --api-key-env OPENROUTER_API_KEY \
  --base-url https://openrouter.ai/api/v1 \
  --model deepseek/deepseek-r1 \
  --json-mode
```

## Retry behavior

By default, any existing `annotation_id` in the output file is skipped, including records that previously had an API or parse error.

To retry failed records while still skipping successful ones:

```bash
python model_test/scripts/predict_api.py --retry-errors --json-mode
```
