# Python Package

`glimo-hsd` is the standalone packaging boundary for the Glimo / PrivHSD
backend pipeline. The PyPI wheel does not include model weights or challenge
data.

## Core API

```python
from glimo_hsd import PipelineConfig, process_csv

result = process_csv(
    "input.csv",
    config=PipelineConfig(
        text_col="text",
        label_col="hs",
        model_id="batinium/glimo-dehatebert-hsd",
        classifier_backend="hf",
        restatement_backend="none",
        output_dir="outputs/run_001",
    ),
)
```

`PipelineResult` exposes paths instead of loading CSVs into memory:

- `source_csv`
- `scrubbed_csv`
- `predictions_csv`
- `importances_csv`
- `restatement_input_csv`
- `restated_csv`
- `audit_csv`
- `manifest_json`
- `output_dir`

## Offline Smoke Runs

Use `classifier_backend="keyword"` and `restatement_backend="none"` for local
smoke tests that should not download model weights or call a local LLM.

## Production Runs

Install the HF extra and point `model_id` to the uploaded checkpoint:

```bash
pip install "glimo-hsd[hf]"
glimo-hsd process input.csv --text-col text --label-col hs --out outputs/run_001
```

For Qwen or LM Studio-style restatement, expose an OpenAI-compatible local chat
completion endpoint and set:

```bash
--restatement-backend qwen \
--restatement-endpoint http://localhost:1234/v1 \
--restatement-model qwen3.5-4b
```

The restatement backend is provider-neutral only at the OpenAI-compatible API
layer. Glimo does not force instruct tokens or chat-template strings; the
provider/runtime applies those. Glimo does force an OpenAI-style tool-call
response with `tool_choice="required"` because the pipeline needs a strict,
ordered `restatements` array.

Model weights are not bundled in the PyPI package. Use `model_id` to point to a
Hugging Face repository or local model directory.
