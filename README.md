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
  -> cue-safe author style scrub and repeated author-group residual masking
  -> span fusion, residual cleanup, and candidate selection
  -> HSD cue safeguards
  -> default HF sidecar classification on cleaned text only
  -> optional second-pass verifier on positive HSD labels
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
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json
```

The output CSV keeps the input row order, row count, and columns exactly. Only
the selected text column is replaced. Labels, diagnostics, suggestions, and
warnings from sidecars stay in JSON sidecars.

Scalable HSD labels default to the fine-tuned local HF classifier sidecar:

```bash
--hsd-classifier hf \
--hf-hsd-model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
--hf-hsd-threshold 0.850469
```

Use `--hsd-classifier off` only for deterministic privacy-only runs without
sidecar labels.

The selected checkpoint is `Hate-speech-CNERG/dehatebert-mono-english`
fine-tuned with 5-fold official-train validation. Out-of-fold best F1 was
`0.8289` at threshold `0.850469`; every OOF row was predicted by a model that
did not train on that row. GPT/local LLM classification remains a backup or
audit path. To run the older local LLM sidecar extension, pass:

```bash
--llm-review local-llm \
--local-llm-endpoint http://100.120.207.64:1234/v1/chat/completions \
--local-llm-model openai/gpt-oss-20b \
--llm-verifier local-llm
```

The optional verifier reviews only rows the main sidecar classifier marked
positive, uses cleaned text only, and records disagreement/uncertainty in the
manifest/audit without changing the CSV.

Author-risk reduction is also on by default. The pipeline normalizes
author-identifying style markers with cue safeguards and masks detector-backed
factual spans that repeat across rows from the same author/user column. Use
`--no-style-scrub` or `--no-author-group-masking` only for ablations.

The PrivHSD trade-off score is optimized as:

```text
TO = Utility_protected / Utility_original - Privacy_protected / Privacy_original
```

Higher is better. The default strategy therefore removes deterministic direct
and technical identifiers aggressively while preserving hate-speech semantics
and avoiding broad text rewrites that damage HSD utility.

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

Research-only:

- `mini-verifier-eval`: isolated local-model verifier evaluation. It
  writes ignored artifacts under `data/outputs/` and does not alter the exact
  CSV runtime.

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
python -m pip install -e '.[presidio,scrubadub,hf,workbench]'
```

## Repository Map

```text
contextsafe_hsd/     Final Python package
tests/               Regression tests for exact output, cue preservation, LLM sidecars
docs/reference/      Stable contracts
docs/runbooks/       Operating commands
docs/planning/       Current status and active research handoffs
workbench/           Optional local FastAPI + React demo
data/                Ignored local data, models, outputs, and run notes
```

Start with `docs/reference/pipeline.md`,
`docs/reference/data_contract.md`, and `docs/runbooks/quickstart.md`.

The current small-model verifier handoff is
`docs/planning/mini_verifier_eval/prompt.md`.

## Data Policy

Keep downloaded datasets, generated CSVs, model weights, manifests, reports, and
run notes under ignored `data/` paths. Do not commit raw sensitive examples,
local model outputs, `.vscode/`, or generated demo caches.
