# Official Submission Runbook

Status: active
Owner area: official CSV workflow
Last verified: 2026-06-14
Primary code: `privhsd/csv_pipeline.py`, `privhsd/submission.py`,
`privhsd/auto/`

Use this when an official or challenge-style CSV arrives.

## 1. Isolate Raw Data

Put official files under ignored `data/official/` or `data/public_dev/`.
Do not paste raw rows into docs, chat, commits, screenshots, or issue comments.
Reports should identify rows by ID only.

## 2. Profile Columns

```bash
python -m privhsd.cli profile-dataset \
  --input data/official/OFFICIAL.csv \
  --output data/outputs/official.profile.json
```

Confirm the text column, ID column, label/source/split columns, repeated
author/user-like columns, blank text, duplicate text, missing labels, and odd
columns.

If the profiler guesses wrong:

```bash
python -m privhsd.cli profile-dataset \
  --input data/official/OFFICIAL.csv \
  --text-col TEXT_COLUMN \
  --id-col ID_COLUMN \
  --label-col LABEL_COLUMN \
  --output data/outputs/official.profile.json
```

## 3. Create The First Exact Output

```bash
python -m privhsd.cli create-submission \
  --input data/official/OFFICIAL.csv \
  --output data/outputs/official.auto.csv \
  --text-col TEXT_COLUMN \
  --id-col ID_COLUMN \
  --replace-text \
  --mode auto \
  --metric-depth fast \
  --manifest data/outputs/official.auto.manifest.json
```

Do not pass `--allow-model-download` on official data unless the run note
explicitly approves downloading optional local model weights.

This command must use `--replace-text`. It preserves the source column names,
column order, row count, row order, IDs, and non-text metadata, and the manifest
records hashes, metrics, provider/model status, load counts, preserved columns,
and strict validation. It does not append helper columns or HSD predictions.

## 4. Validate Shape

```bash
python -m privhsd.cli validate-submission \
  --source data/official/OFFICIAL.csv \
  --submission data/outputs/official.auto.csv \
  --text-col TEXT_COLUMN \
  --id-col ID_COLUMN \
  --output data/outputs/official.auto.validation.json
```

Do not tune before this exact-format output exists.

## 5. Run Evidence

Run source-aware regression with only columns that exist:

```bash
python -m privhsd.cli source-regression-report \
  --original data/official/OFFICIAL.csv \
  --protected data/outputs/official.auto.csv \
  --original-text-col TEXT_COLUMN \
  --protected-text-col TEXT_COLUMN \
  --id-col ID_COLUMN \
  --group-col SOURCE_COLUMN \
  --group-col LABEL_COLUMN \
  --group-col SPLIT_COLUMN \
  --output data/outputs/official.auto.source_regression.json
```

If labels are available, run utility benchmarking. If repeated author/user
columns exist, run author-risk evaluation. If they do not, record the
structured skip rather than inventing an author label.

## 6. Submit In This Order

1. `auto` exact-format output.
2. Deterministic `balanced` only if auto provider/model behavior looks weak or
   official feedback indicates it.
3. Style-scrubbed or reranked exact output only after validation.
4. Provider-fusion or token-policy candidate paths only after reranking and
   exact-format validation.

Never upload raw Presidio, raw GLiNER, raw scrubadub, DPMLM, SanText, or LLM
output directly. Those historical/planning paths are candidate or comparison
tools only; the current operational upload path is the single exact-format
submission pipeline.

## Decision Rule

Prefer the candidate that passes exact validation, reduces identifiers and
style risk, preserves target/action/negation/modality cues, has a reproducible
manifest, and can be explained as preprocessing support for human review.
