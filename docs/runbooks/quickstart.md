# Quickstart

Status: active
Owner area: common local workflow
Last verified: 2026-06-13
Primary code: `privhsd/cli.py`, package metadata, tests

Use this for first-run setup and the shortest local validation path.

## Install And Verify

```bash
python -m pip install .
python -m pytest -q
contextsafe-hsd --help
```

Optional extras are installed only for workflows that need them:

```bash
python -m pip install '.[benchmark]'
python -m pip install '.[presidio]'
python -m pip install '.[token-policy]'
```

## Prepare Public Data

```bash
python -m privhsd.cli prepare-recommended-datasets \
  --output-dir data/public_dev \
  --raw-dir data/public_dev/raw \
  --merged-output data/public_dev/recommended_merged.csv
```

Downloaded raw files stay under ignored `data/public_dev/raw/`.

## Create And Validate An Exact Auto Candidate

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

python -m privhsd.cli validate-submission \
  --source data/public_dev/recommended_merged.csv \
  --submission data/outputs/recommended_merged.auto.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/recommended_merged.auto.validation.json
```

For a package-installed command, replace `python -m privhsd.cli` with
`contextsafe-hsd`.

## Minimal Evidence Pass

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

Use `--metric-depth fast` for exact submissions. Use `sampled` or `deep` only
for explicit local audits under ignored `data/`.

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

## Run Notes

For official or benchmark runs, keep dated notes under ignored
`data/outputs/`. Record commands, commit hash, artifact paths, aggregate local
metrics, official scores, and limitations. Do not commit raw examples or
generated run logs.
