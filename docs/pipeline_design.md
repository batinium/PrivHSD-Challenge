# Pipeline Design

## Current Package

The active implementation is in `privhsd/`.

```text
privhsd/
  ablation.py      multi-mode ablation report runner
  cli.py           command-line interface
  csv_pipeline.py  CSV read/write, audit, and batch processing
  detectors.py     deterministic span detectors
  metrics.py       local privacy/utility proxy metrics
  pipeline.py      single-text privatization API
  utility_benchmark.py  optional scikit-learn utility-delta benchmark
```

## CLI Contract

Privatize a CSV:

```bash
python -m privhsd.cli anonymize \
  --input data/public_dev/dynahate.csv \
  --output data/outputs/dynahate.privatized.csv \
  --text-col text \
  --id-col id \
  --audit data/outputs/dynahate.audit.json \
  --mode balanced
```

Evaluate a privatized CSV:

```bash
python -m privhsd.cli evaluate \
  --input data/outputs/dynahate.privatized.csv \
  --text-col text \
  --privatized-col privatized_text \
  --output data/outputs/dynahate.metrics.json
```

Benchmark downstream utility with an optional local classifier:

```bash
python -m pip install '.[benchmark]'
python -m privhsd.cli benchmark-utility \
  --input data/outputs/dynahate.privatized.csv \
  --text-col text \
  --privatized-col privatized_text \
  --label-col label \
  --id-col id \
  --output data/outputs/dynahate.utility_benchmark.json
```

`benchmark-utility` trains a TF-IDF + logistic regression classifier only on the
original-text training split, then compares dev-split predictions on original
text and `privatized_text`. It reports accuracy, macro-F1, prediction
agreement, label recall deltas, and confidence drift. This is a local relative
utility proxy, not a production hate-speech classifier and not a replacement for
the official challenge evaluator.

Compare privatization variants in one machine-readable report:

```bash
python -m privhsd.cli ablate \
  --input data/public_dev/dynahate.csv \
  --text-col text \
  --id-col id \
  --label-col label \
  --output data/outputs/dynahate.ablation.json \
  --output-dir data/outputs/dynahate_ablation
```

`ablate` compares:

- `identity`: no privatization.
- `regex_only`: direct regex detectors only, no context detectors, no target
  generalization.
- `balanced`: current default.
- `privacy`: privacy mode.
- `balanced_with_targets`: balanced mode plus target-group generalization.

The JSON report contains input and column configuration, variant definitions,
aggregate proxy metrics, per-row metric/audit metadata without raw text, and
optional utility benchmark summaries. If `--output-dir` is provided, one CSV per
variant is written with original columns preserved and a `privatized_text`
column added. If `--label-col` is provided and scikit-learn is installed, the
report includes the same local relative utility benchmark used by
`benchmark-utility` for each variant. If scikit-learn is not installed, the
report includes `utility_benchmark_skipped` with the install hint and still
writes the deterministic ablation metrics.

## Local Metrics

`privhsd evaluate`, anonymize audit summaries, and ablation reports use the same
deterministic proxy metrics from `privhsd.metrics`. Existing compatibility keys
such as `privacy_gain_mean`, `utility_cue_retention_mean`,
`character_utility_retention_mean`, `proxy_tradeoff_mean`, and
`identifier_counts` remain stable.

Row-level metrics also include:

- placeholder and mask density: `mask_density`, `placeholder_density`,
  `placeholder_count`, `placeholder_counts_by_type`, and
  `placeholder_character_count`
- residual leakage indicators: `residual_identifier_count`,
  `residual_direct_identifier_count`, `residual_quasi_identifier_count`, and
  residual counts by entity type
- quasi-identifier signals: before/after counts for `AGE`, `DATE`, `LOCATION`,
  and `ORGANIZATION`, plus `quasi_identifier_flags`
- target cue retention: target cue/category counts, literal target term
  retention, and target category retention
- warning lists: `privacy_warnings`, `overmasking_warnings`, and combined
  `warnings`

Aggregate metrics roll these fields up with totals, means, warning counts, and
rows-with-warning counts. These are local explainability signals for comparing
runs; they are not official challenge scores.

## Data Contract

Input CSV must have:

- a text column, passed as `--text-col`
- optionally an ID column, passed as `--id-col`

Output CSV must:

- preserve row count
- preserve row order
- preserve existing columns
- preserve labels and metadata
- add `privatized_text` unless `--replace-text` is explicitly used

## Modes

`utility`

Conservative privacy transformation. Masks direct identifiers and preserves
target-group terms.

`balanced`

Default mode. Masks direct identifiers while preserving hate-speech cues. Use
this mode first for official leaderboard submissions.

`privacy`

More aggressive. Also generalizes known target-group mentions into typed
categories. Useful for policy demos, but it may reduce classifier utility.

## Transformation Style

Use typed placeholders:

```text
[USER]
[EMAIL]
[PHONE]
[URL]
[PERSON]
[LOCATION]
[ORG]
[DATE]
[ID]
[TARGET_GROUP:category]
```

Prefer typed placeholders over deletion because deletion destroys context.

## Design Rule

The core pipeline must work without LLMs. LLMs may be used later only as optional
experiments or demo support, not as a required dependency for the challenge
submission.

The base install remains dependency-free. Optional evaluator extras such as
`privhsd[benchmark]` must not become required for `anonymize`.
