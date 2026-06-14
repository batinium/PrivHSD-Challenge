# Official Submission Runbook

Status: active
Owner area: official CSV workflow
Last verified: 2026-06-14
Primary code: `privhsd/csv_pipeline.py`, `privhsd/submission.py`,
`privhsd/auto/`

Use this when an official or challenge-style CSV arrives. The public workflow
is:

```text
Input CSV -> Privacy Detection -> Meaning Protection -> Verification
```

The first deliverable is always an exact cleaned CSV plus manifest.

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

## 3. Create Exact Output

```bash
python -m privhsd.cli protect \
  --preset exact \
  --input data/official/OFFICIAL.csv \
  --output data/outputs/official.protected.csv \
  --text-col TEXT_COLUMN \
  --id-col ID_COLUMN \
  --manifest data/outputs/official.protected.manifest.json
```

This is the documented default path. It preserves source column names, column
order, row count, row order, IDs, labels, and non-text metadata. It writes
cleaned text only and must not append helper columns or HSD predictions.

Do not enable external downloads or ad hoc model changes on official data.
Optional local components may be used only when already installed and
configured; unavailable components should appear as skipped or unavailable in
the manifest.

## 4. Validate Shape

```bash
python -m privhsd.cli validate-submission \
  --source data/official/OFFICIAL.csv \
  --submission data/outputs/official.protected.csv \
  --text-col TEXT_COLUMN \
  --id-col ID_COLUMN \
  --output data/outputs/official.validation.json
```

Do not tune before this exact-format output exists and validates.

## 5. Review The Manifest

The manifest should be explainable through three stages:

- `privacy_detection`: what was found and which local PII Assist components
  were ready, skipped, or unavailable.
- `meaning_protection`: whether masking preserved HSD-relevant cues such as
  target groups, threats/actions, negation, modality, quotation,
  counterspeech, and reporting/rationale cues.
- `verification`: residual direct identifiers, metadata leakage status, HSD
  advisory drift status, exact-shape validation, and author-risk hook status.

If an author/user column exists, the manifest should record whether
author-risk evaluation ran. If the data does not support repeated-author
analysis, record the skipped reason rather than inventing one.

## 6. Run Evidence

Run source-aware regression with only columns that exist:

```bash
python -m privhsd.cli source-regression-report \
  --original data/official/OFFICIAL.csv \
  --protected data/outputs/official.protected.csv \
  --original-text-col TEXT_COLUMN \
  --protected-text-col TEXT_COLUMN \
  --id-col ID_COLUMN \
  --group-col SOURCE_COLUMN \
  --group-col LABEL_COLUMN \
  --group-col SPLIT_COLUMN \
  --output data/outputs/official.source_regression.json
```

If labels are available, record local utility evidence separately from the
exact cleaned CSV. If repeated author/user columns exist, run author-risk
evaluation as a Verification sidecar; otherwise record the structured skip.

## 7. Submit

Submit the exact cleaned CSV produced by `protect --preset exact` after shape
validation and manifest review. Do not upload `analysis` output, audit
sidecars, raw provider output, or research/debug candidate output.

## Decision Rule

Prefer the candidate that validates exactly, reduces direct and quasi
identifiers, preserves HSD-relevant meaning cues, has a reproducible manifest,
and reports residual risk instead of hiding it.
