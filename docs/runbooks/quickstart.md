# Quickstart

Status: active
Owner area: common local workflow
Last verified: 2026-06-14
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
python -m pip install '.[hsd-advisory]'
```

## Prepare Public Data

```bash
python -m privhsd.cli prepare-recommended-datasets \
  --output-dir data/public_dev \
  --raw-dir data/public_dev/raw \
  --merged-output data/public_dev/recommended_merged.csv
```

Downloaded raw files stay under ignored `data/public_dev/raw/`.

## Sanitize And Classify A CSV

Use this when you want one enriched CSV for local analysis or unseen-data
triage:

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

The output keeps original rows and columns, replaces `text` with sanitized
text, and appends HSD prediction columns. If the input already has
`is_hate_speech`, the command preserves it and writes
`predicted_is_hate_speech` unless `--overwrite-hate-columns` is set. Model
downloads are off by default; add `--allow-model-download` only for an explicit
OSS-model run. The manifest includes a `tradeoff` summary for identifier
removal, cue retention, overmask warnings, and original-vs-sanitized HSD score
drift.

The trusted local configuration uses deterministic masking, Presidio,
scrubadub, the local RoBERTa/HateBERT token-policy ensemble, and the two-model
RoBERTa HSD advisory ensemble:

```text
facebook/roberta-hate-speech-dynabench-r4-target
cardiffnlp/twitter-roberta-base-hate-latest
```

If those HSD models are not available locally and downloads are not explicitly
allowed, remove `--require-hate-classification` for a fallback run and treat the
missing model status in the manifest as a blocker for trusted hate columns.

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
