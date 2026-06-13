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
docs/project/        Methodology, pipeline, evidence, and operating workflow
docs/challenge/      Rules, rights framing, checklist, and pitch material
workbench/           Decoupled FastAPI + React demo app
data/                Ignored local datasets, models, and reports
```

Start with [docs/README.md](docs/README.md). For a full method explanation,
read [docs/project/methodology_justification.md](docs/project/methodology_justification.md).

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
```

`.[token-policy]` uses PyTorch/Transformers and will use CUDA when the local
PyTorch build sees a CUDA GPU.

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

`--mode auto` runs deterministic balanced masking for every row, discovers
local optional providers/models, routes only risky rows to them, and writes the
selected text back into the original text column. A four-column CSV such as
`source,author_id,text,is_hate_speech` stays exactly four columns in that order
when `--replace-text` is used.

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

- `auto` is the primary exact-format CSV path. It records provider/model
  discovery status and falls back to deterministic balanced masking when
  optional dependencies or local artifacts are missing.
- `balanced` remains the deterministic compatibility fallback: auditable,
  target-preserving, and low-dependency.
- On the merged public regression bundle, `balanced` reduced identifier
  detections from 40,304 to 5 while preserving target and utility cues at
  0.9999.
- Source-aware regression adds slice checks by source, label, split, platform,
  and type, with rationale/span preservation reported by row ID only.
- A CUDA fine-tuned RoBERTa token-policy model reached dev macro F1 0.9061 on
  weak token-action labels.
- Grouped 5-fold RoBERTa token-policy training reached macro F1 mean 0.8977
  with zero duplicate text overlap across folds.
- On external TweetEval hate/offensive data, the equal RoBERTa plus HateBERT
  ensemble reached macro F1 0.8837 and `PROTECT_TARGET` F1 0.8143 on weak
  token-action labels.

The token-policy models are advisory/reranking support. They do not replace
the deterministic anonymizer unless an audited candidate path improves official
privacy and utility scores.

Default exact submissions use `--metric-depth fast`, which avoids expensive
target-cue variant, spaced-token, profanity, and semantic scans on every row.
Use `--metric-depth sampled` or `--metric-depth deep` only for local audit runs
under ignored `data/` paths.

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
