# glimo-hsd

Reusable Python package for privacy-aware harmful-speech dataset processing.
The package processes CSV files into privacy-scrubbed, classifier-ready,
optionally restated outputs while keeping model weights outside the PyPI wheel.

## Install

```bash
pip install glimo-hsd
pip install "glimo-hsd[hf]"  # Transformers / torch classifier support
```

## Python API

```python
from glimo_hsd import PipelineConfig, process_csv

result = process_csv(
    "input.csv",
    config=PipelineConfig(
        text_col="text",
        label_col="hs",
        model_id="ORG_OR_USER/dehatebert-hsd",
        restatement_backend="none",
        final_scrub=True,
    ),
)

print(result.restated_csv)
print(result.audit_csv)
```

Use `classifier_backend="keyword"` for offline smoke tests. Production runs
should use `classifier_backend="hf"` with the Hugging Face model repo or a local
model directory.

## LLM Restatement Backend

The package does not insert instruct tokens, chat-template markers, or
model-specific control text. Those are handled by the LLM provider or local
runtime.

When `restatement_backend` is `qwen` or `local-http`, the package sends an
OpenAI-compatible chat-completions request and requires a structured tool call
with `tool_choice="required"`. That tool contract is intentional: the
restatement step needs exactly one ordered restatement per input row. Providers
or runtimes used for restatement must support OpenAI-style tool calling.

## CLI

```bash
glimo-hsd process input.csv \
  --text-col text \
  --label-col hs \
  --out outputs/run_001 \
  --model-id ORG_OR_USER/dehatebert-hsd \
  --classifier-backend hf \
  --restatement-backend none \
  --final-scrub
```

The process command writes deterministic artifacts:

```text
source.csv
scrubbed.csv
dehatebert_predictions.csv
token_importances.csv
restatement_input.csv
restated.csv
final_scrubbed.csv
deviation_audit.csv
manifest.json
```

## Model Weights

The PyPI package does not include model weights. With
`classifier_backend="hf"`, pass a `model_id` for a compatible Hugging Face repo
or local model directory.

## Safety

Classifier scores and restatement audits are decision-support signals. They are
not appropriate for fully automated enforcement without human review. Do not
publish raw private datasets, admin uploads, or generated outputs containing
private source text.
