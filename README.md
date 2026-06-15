# ContextSafe-HSD

ContextSafe-HSD is a local CSV privatization pipeline for hate-speech detection
datasets. It replaces personal and re-identifying details while preserving the
target, action, negation, quotation, counterspeech, and reporting cues needed for
downstream HSD review.

It is preprocessing infrastructure. It is not a production classifier, a
moderation system, or a guarantee that every identifier has been removed.

## Final Pipeline

```text
input CSV
  -> deterministic PII sanitization
  -> Presidio/scrubadub PII Assist
  -> span fusion, residual cleanup, and candidate selection
  -> HSD cue safeguards
  -> local LLM sidecar review on cleaned text only
  -> exact-format output CSV with only the text column replaced
  -> manifest/audit sidecars
```

Run the final path:

```bash
python -m contextsafe_hsd.cli protect \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --llm-review local-llm \
  --local-llm-endpoint http://100.120.207.64:1234/v1/chat/completions \
  --local-llm-model openai/gpt-oss-20b \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json
```

The output CSV keeps the input row order, row count, and columns exactly. Only
the selected text column is replaced. LLM labels, reason tags, diagnostics,
suggestions, and warnings stay in JSON sidecars.

For an offline run without the sidecar reviewer, pass `--llm-review off`. The
manifest records the skipped review status and counts.

Validate the exact CSV shape:

```bash
python -m contextsafe_hsd.cli validate-submission \
  --source INPUT.csv \
  --submission OUTPUT.csv \
  --text-col text \
  --output OUTPUT.validation.json
```

Use `--id-col` only when both files contain the same privacy-safe stable key.
Raw author/user IDs should not be treated as review case IDs.

## Public Surface

- `protect`: final exact CSV pipeline with optional audit sidecar depth.
- `validate-submission`: row/order/column contract validation.
- `profile-dataset`: raw-text-free incoming CSV profile.

Python callers can use:

```python
from pathlib import Path
from contextsafe_hsd import run_final_csv_pipeline, validate_submission

run_final_csv_pipeline(
    Path("INPUT.csv"),
    Path("OUTPUT.csv"),
    text_col="text",
    id_col="ID",
    manifest_path=Path("OUTPUT.manifest.json"),
    audit_path=Path("OUTPUT.audit.json"),
)

validate_submission(
    Path("INPUT.csv"),
    Path("OUTPUT.csv"),
    text_cols=["text"],
)
```

## Install And Test

```bash
python -m pip install -e '.[dev]'
python -m ruff check contextsafe_hsd tests workbench/backend
python -m pytest -q
```

Optional local helpers:

```bash
python -m pip install -e '.[presidio,scrubadub,workbench]'
```

## Repository Map

```text
contextsafe_hsd/     Final Python package
tests/               Regression tests for exact output, cue preservation, LLM sidecars
docs/reference/      Stable contracts
docs/runbooks/       Operating commands
docs/planning/       Current status only
workbench/           Optional local FastAPI + React demo
data/                Ignored local data, models, outputs, and run notes
```

Start with `docs/reference/pipeline.md`,
`docs/reference/data_contract.md`, and `docs/runbooks/quickstart.md`.

## Data Policy

Keep downloaded datasets, generated CSVs, model weights, manifests, reports, and
run notes under ignored `data/` paths. Do not commit raw sensitive examples,
local model outputs, `.vscode/`, or generated demo caches.
