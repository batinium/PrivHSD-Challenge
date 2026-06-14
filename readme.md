# ContextSafe-HSD

ContextSafe-HSD is a local privacy-preserving text privatization pipeline for
hate-speech detection datasets. It rewrites text to reduce direct identifiers,
quasi-identifiers, and author-style signals while preserving the target,
hostility, negation, and context cues that downstream HSD models or human
reviewers need.

This repository is a preprocessing system, not a production hate-speech
classifier and not an automated takedown tool.

## What Is In The System

```text
contextsafe_hsd/     Public Python package alias
privhsd/             CLI and implementation
tests/               Synthetic and regression tests
docs/runbooks/       Operational workflows and commands
docs/reference/      Stable contracts and architecture
docs/planning/       Current evidence, risks, decisions, and roadmap
docs/research/       Methodology and governance rationale
docs/challenge/      Rules, rights framing, checklist, and pitch material
workbench/           Decoupled FastAPI + React demo app
data/                Ignored local datasets, models, and reports
```

Start with [docs/README.md](docs/README.md). For a full method explanation,
read [docs/research/methodology.md](docs/research/methodology.md). For parallel
agent work, use [docs/agent_workstreams.md](docs/agent_workstreams.md).

## Install And Test

```bash
python -m pip install .
python -m pytest -q
```

Optional extras are installed only for the workflows that need them:

```bash
python -m pip install '.[benchmark]'
python -m pip install '.[presidio]'
python -m pip install '.[token-policy]'
python -m pip install '.[hsd-advisory]'
```

`.[token-policy]` uses PyTorch/Transformers and will use CUDA when the local
PyTorch build sees a CUDA GPU.

## One-Command Sanitize And Classify CSV

For a practical enriched output, replace the input text column in place and add
HSD prediction columns:

```bash
python -m privhsd.cli sanitize-classify \
  --input INPUT.csv \
  --output data/outputs/INPUT.sanitized_classified.csv \
  --text-col text \
  --id-col id \
  --manifest data/outputs/INPUT.sanitized_classified.manifest.json \
  --require-hate-classification \
  --max-model-batch-size 32
```

This command runs the single `auto` sanitization path with a deterministic
balanced baseline, replaces `text` in place, appends hate-speech prediction
columns, and writes a raw-text-free manifest with a `tradeoff` summary for
identifier removal, cue retention, overmask warnings, and
original-vs-sanitized HSD score drift. Default hate columns are
`is_hate_speech`, `hate_speech_score`, and `hate_speech_model_count`; if the
label column already exists, the prediction label is written to
`predicted_is_hate_speech` unless `--overwrite-hate-columns` is set. Because
prediction columns are added, this is an enriched analysis output, not an
exact-format upload.

The always-available layer is deterministic masking. Auto mode reports status
for optional Presidio, scrubadub, GLiNER, token-policy, semantic, local LLM,
and HSD advisory components. Providers and models that are actually available
to the current engine are lazy-loaded only when the route needs them. Model
downloads are off by default; pass `--allow-model-download` only when you
explicitly want approved OSS Hugging Face models downloaded or refreshed. The
default HSD advisory registry is:

```text
facebook/roberta-hate-speech-dynabench-r4-target
cardiffnlp/twitter-roberta-base-hate-latest
```

## Create An Exact-Format Candidate

```bash
python -m privhsd.cli create-submission \
  --input data/public_dev/recommended_merged.csv \
  --output data/outputs/recommended_merged.auto.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --metric-depth fast \
  --manifest data/outputs/recommended_merged.auto.manifest.json
```

`create-submission` requires `--replace-text`. `--mode auto` runs deterministic
balanced masking for every row, discovers local optional providers/models,
routes only risky rows to them, and writes the selected text back into the
original text column. The output preserves the source columns and order; a
four-column CSV such as `source,author_id,text,is_hate_speech` stays exactly
four columns in that order. The manifest records `artifact_type:
exact_format_submission`, input/output hashes, preserved columns, metrics,
provider/model status for `auto`, and strict validation results.

Validate upload shape:

```bash
python -m privhsd.cli validate-submission \
  --source data/public_dev/recommended_merged.csv \
  --submission data/outputs/recommended_merged.auto.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/recommended_merged.auto.validation.json
```

Run source-aware regression:

```bash
python -m privhsd.cli source-regression-report \
  --original data/public_dev/recommended_merged.csv \
  --protected data/outputs/recommended_merged.auto.csv \
  --original-text-col text \
  --protected-text-col text \
  --id-col id \
  --group-col source \
  --group-col label \
  --group-col split \
  --group-col platform \
  --group-col type \
  --output data/outputs/recommended_merged.auto.source_regression.json
```

## Current Evidence Snapshot

Current evidence, readiness, and caveats live in
[docs/planning/current_status.md](docs/planning/current_status.md).

The short version: `auto` is the primary exact-format path, `balanced` remains
the deterministic fallback, token-policy models are advisory/reranking support,
and exact submissions use `--metric-depth fast` by default. `privacy` mode, or
`--generalize-targets`, can generalize protected target cues; the default
submission path preserves them for HSD review. Use sampled or deep metrics only
for explicit local audits under ignored `data/` paths.

## Demo Workbench

The local web demo lives in [workbench/](workbench/). It runs a FastAPI backend
against the existing `privhsd` APIs and a React/Vite frontend for paste-text
testing, span highlighting, risk gauges, and audit JSON export.

Launch both servers from the repository root:

```bash
python launch.py --install
```

After dependencies are installed once:

```bash
python launch.py
```

Backend reload mode is opt-in for development:

```bash
python launch.py --reload
```

## Python API

```python
from pathlib import Path

import contextsafe_hsd as hsd

hsd.create_submission(
    Path("INPUT.csv"),
    Path("SUBMISSION.csv"),
    text_cols=["text"],
    id_col="id",
    manifest_path=Path("SUBMISSION.manifest.json"),
    replace_text=True,
    mode="auto",
)
```

## Data Policy

Downloaded datasets, generated CSVs, model weights, and reports under `data/`
are ignored by git. Keep raw sensitive examples out of markdown, commits,
issues, screenshots, and presentation material.
