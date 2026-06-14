# Quickstart

Status: active
Owner area: common local workflow
Last verified: 2026-06-14
Primary code: `contextsafe_hsd/cli.py`, package metadata, tests

Use this for first-run setup and the shortest local privacy-protection path.
The public workflow is:

```text
Input CSV -> Privacy Detection -> Meaning Protection -> Verification
```

## Install And Verify

```bash
python -m pip install .
python -m pytest -q
contextsafe-hsd protect --help
```

For package-installed usage, use `contextsafe-hsd`. The `privhsd` console
script and `python -m privhsd.cli` remain compatibility aliases.

## Protect A CSV

```bash
contextsafe-hsd protect \
  --input INPUT.csv \
  --output data/outputs/INPUT.protected.csv \
  --text-col text \
  --id-col id \
  --manifest data/outputs/INPUT.protected.manifest.json
```

This defaults to `--preset exact`. It writes cleaned text back into the input
text column and preserves the source schema: columns, column order, row count,
row order, IDs, labels, and non-text metadata values. It does not append HSD
prediction columns.

The manifest leads with three stages:

- `privacy_detection`: deterministic baseline plus any ready local PII Assist.
- `meaning_protection`: checks that target/action/negation/reporting cues are
  not erased by masking.
- `verification`: residual identifier checks, exact-shape checks, optional HSD
  advisory drift status, metadata leakage status, and author-risk hook status.

Missing optional local components should be recorded as skipped or unavailable,
not treated as a failure for exact output.

## Presets

```bash
contextsafe-hsd protect --preset exact \
  --input INPUT.csv \
  --output data/outputs/INPUT.protected.csv \
  --text-col text \
  --id-col id \
  --manifest data/outputs/INPUT.protected.manifest.json
```

Use `exact` for the default cleaned CSV plus manifest.

```bash
contextsafe-hsd protect --preset analysis \
  --input INPUT.csv \
  --output data/outputs/INPUT.analysis.csv \
  --text-col text \
  --id-col id \
  --manifest data/outputs/INPUT.analysis.manifest.json
```

Use `analysis` only for local review. It may append advisory HSD prediction
columns after sanitization. These columns are not production classifier truth
and are not part of exact-format output.

```bash
contextsafe-hsd protect --preset audit \
  --input INPUT.csv \
  --output data/outputs/INPUT.audit.csv \
  --text-col text \
  --id-col id \
  --manifest data/outputs/INPUT.audit.manifest.json
```

Use `audit` when you want exact output plus deeper sidecar reporting where the
installed runtime supports it.

## Prepare Public Development Data

```bash
contextsafe-hsd prepare-recommended-datasets \
  --output-dir data/public_dev \
  --raw-dir data/public_dev/raw \
  --merged-output data/public_dev/recommended_merged.csv
```

Downloaded raw files stay under ignored `data/public_dev/raw/`.

## Validate Exact Shape

```bash
contextsafe-hsd validate-submission \
  --source data/public_dev/recommended_merged.csv \
  --submission data/outputs/recommended_merged.protected.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/recommended_merged.validation.json
```

Validation should pass before any output is shared. Do not tune or compare
alternate runs until the exact cleaned CSV exists and its manifest is readable.

## Minimal Evidence Pass

```bash
contextsafe-hsd source-regression-report \
  --original data/public_dev/recommended_merged.csv \
  --protected data/outputs/recommended_merged.protected.csv \
  --original-text-col text \
  --protected-text-col text \
  --id-col id \
  --group-col source \
  --group-col label \
  --group-col split \
  --group-col platform \
  --group-col type \
  --output data/outputs/recommended_merged.source_regression.json
```

Use only group columns that exist in the dataset. If an author/user column is
available and repeated-author analysis is needed, record whether that
Verification hook ran or why it was skipped.

## Python API

The CLI is the public path. Python callers can invoke the same exact `auto`
path directly:

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

## Run Notes

Keep dated notes under ignored `data/outputs/`. Record commands, commit hash,
artifact paths, aggregate local metrics, official scores when available, and
limitations. Do not commit raw examples or generated run logs.
