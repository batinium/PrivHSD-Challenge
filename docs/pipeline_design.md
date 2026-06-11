# Pipeline Design

## Current Package

The active implementation is in `privhsd/`.

```text
privhsd/
  ablation.py      multi-mode ablation report runner
  author_risk.py   optional local authorship-risk adversary
  classifier.py    optional local CSV train/evaluate/predict classifier
  cli.py           command-line interface
  csv_pipeline.py  CSV read/write, audit, and batch processing
  detectors.py     deterministic span detectors
  dpmlm_spike.py   bounded optional DPMLM spike/blocker report
  hf_utility.py    optional Hugging Face utility model registry/evaluator
  metrics.py       local privacy/utility proxy metrics
  pipeline.py      single-text privatization API
  rerank.py        row-local candidate generation and reranking
  style.py         deterministic style scrubbing for author cues
  submission.py    exact-format submission creator/validator
  utility_benchmark.py  optional scikit-learn utility-delta benchmark
```

The deterministic detectors cover direct identifiers and conservative
quasi-identifiers including handles, emails, phone numbers, URLs, IP addresses,
dates, context names, context locations, schools/organizations, common ID
formats, and explicit aliases such as `alias`, `aka`, `known as`, and
`goes by`.

The next roadmap step is broader authorship-risk reduction. PII masking is only
one part of privacy; author style, syntax, formatting, repeated expressions, and
contextual habits can also identify an author.

## CLI Contract

Privatize a CSV:

```bash
python -m privhsd.cli anonymize \
  --input data/public_dev/dynahate.csv \
  --output data/outputs/dynahate.privatized.csv \
  --text-col text \
  --id-col id \
  --audit data/outputs/dynahate.audit.json \
  --mode balanced \
  --style-scrub
```

`--style-scrub` is optional. It runs after privacy masking and normalizes
authorship style cues such as casing, whitespace, repeated punctuation,
repeated letters, emoji/symbol bursts, self-tags, signatures, and common
idiolect markers while preserving placeholders, target-group terms, negation,
modality, and hate/action cues.

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

Train a local baseline hate-speech classifier:

```bash
python -m pip install '.[classifier]'
python -m privhsd.cli train-classifier \
  --input data/public_dev/dynahate.csv \
  --text-col text \
  --label-col label \
  --id-col id \
  --model data/outputs/dynahate.classifier.pkl \
  --output data/outputs/dynahate.classifier.train.json
```

Evaluate a saved classifier:

```bash
python -m privhsd.cli evaluate-classifier \
  --input data/public_dev/dynahate.csv \
  --model data/outputs/dynahate.classifier.pkl \
  --text-col text \
  --label-col label \
  --id-col id \
  --output data/outputs/dynahate.classifier.evaluate.json
```

Write row-preserving predictions:

```bash
python -m privhsd.cli predict-classifier \
  --input data/outputs/dynahate.privatized.csv \
  --model data/outputs/dynahate.classifier.pkl \
  --text-col privatized_text \
  --id-col id \
  --output data/outputs/dynahate.classifier.predictions.csv
```

`train-classifier`, `evaluate-classifier`, and `predict-classifier` are optional
scikit-learn workflows. They use a TF-IDF + logistic regression baseline and
write outputs under `data/outputs/` by default. Metrics JSON includes accuracy,
macro-F1, per-label precision/recall/F1/support, confusion matrix/counts,
prediction counts, split configuration, label counts, and a warning that this
is only a local baseline. `predict-classifier` preserves row count, row order,
IDs, labels if present, and metadata columns, then adds `predicted_label` and
`predicted_confidence`.

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

Evaluate authorship risk when an author column is available:

```bash
python -m privhsd.cli evaluate-author-risk \
  --input data/outputs/dynahate.privatized.csv \
  --text-col text \
  --privatized-col privatized_text \
  --author-col author \
  --id-col id \
  --output data/outputs/author_risk.json
```

`evaluate-author-risk` is optional and uses scikit-learn only when this command
is run. It trains a local TF-IDF logistic-regression author adversary on
original text, then compares author accuracy, macro-F1, true-author confidence,
and residual high-risk row IDs on original versus privatized dev text. If the
requested author column is absent, it writes a structured skipped report instead
of failing.

List approved optional Hugging Face utility probes:

```bash
python -m privhsd.cli hf-model-registry \
  --output data/outputs/hf_model_registry.json
```

Evaluate original versus privatized HSD/toxicity score drift on a small sample:

```bash
python -m privhsd.cli evaluate-hf-utility \
  --input data/outputs/dynahate.privatized.csv \
  --text-col text \
  --privatized-col privatized_text \
  --id-col id \
  --label-col label \
  --sample-size 100 \
  --output data/outputs/dynahate.hf_utility.json
```

`evaluate-hf-utility` is optional through `privhsd[hf-utility]`. It defaults to
the approved Dynabench and CardiffNLP probes, reports model ID, revision when
available, device, runtime, sample size, score drift, threshold agreement, and
row IDs with large utility drops. Missing dependencies, model-load failures, and
inference failures are recorded as structured skips rather than making
`privhsd anonymize` depend on Hugging Face.

Generate row-local candidates and choose the best privacy/HSD tradeoff:

```bash
python -m privhsd.cli rerank-candidates \
  --input data/public_dev/dynahate.csv \
  --output data/outputs/dynahate.reranked.csv \
  --text-col text \
  --id-col id \
  --audit data/outputs/dynahate.rerank.audit.json
```

`rerank-candidates` generates deterministic `balanced`, `style_scrubbed`,
`privacy`, and `target_generalized` candidates per row. Optional rewrite
candidate columns can be supplied with repeatable `--candidate-col` arguments.
The scorer penalizes residual identifiers, residual style signals, optional
author-risk confidence when an author column and scikit-learn are available,
target/action cue loss, and length/character drift. It writes only the chosen
text column by default; per-candidate scores go to the audit JSON without raw
text.

Run a bounded DPMLM protected-cue spike or blocker report:

```bash
python -m privhsd.cli dpmlm-spike \
  --input data/outputs/dynahate.privatized.csv \
  --text-col text \
  --privatized-col privatized_text \
  --id-col id \
  --sample-size 25 \
  --epsilon 25 \
  --epsilon 50 \
  --output data/outputs/dynahate.dpmlm_spike.json
```

`dpmlm-spike` is an experiment harness, not core anonymization. It records the
epsilon sweep, sample IDs, protected target/action/negation cue manifest,
backend detection, runtime, existing privatized-column baseline metrics when
provided, and structured blockers when no supported local DPMLM backend or
audited adapter is available.

Create an exact-format upload CSV and manifest:

```bash
python -m privhsd.cli create-submission \
  --input data/public_dev/dynahate.csv \
  --output data/outputs/dynahate.submission.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode balanced \
  --manifest data/outputs/dynahate.submission.manifest.json
```

Validate an exact-format upload CSV:

```bash
python -m privhsd.cli validate-submission \
  --source data/public_dev/dynahate.csv \
  --submission data/outputs/dynahate.submission.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/dynahate.submission.validation.json
```

`create-submission` requires `--replace-text` and writes the same columns in the
same order as the source dataset. It supports repeatable `--text-col` for
official formats with multiple text fields. The manifest records the command,
git commit, input/output paths and SHA-256 hashes, mode, text columns,
row-preservation validation, and local aggregate metrics. `validate-submission`
checks row count, column set/order, ID order, metadata preservation, and helper
columns; helper columns are rejected by default for upload mode.

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
- optionally normalize author style with `--style-scrub` while preserving the
  same row and metadata contract
- optionally use `rerank-candidates` to choose among row-local deterministic
  and supplied rewrite candidates without adding helper columns by default
- official upload creation should use `create-submission --replace-text` so the
  provided text columns are privatized in place and no helper columns are added

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

Target-group policy:

- `utility` and `balanced` preserve target-group terms by default so downstream
  hate-speech cues remain visible.
- `privacy` and `--generalize-targets` generalize target-group terms into typed
  categories.
- Broad gender terms such as `woman`, `women`, `man`, `men`, `girl`, `girls`,
  `boy`, and `boys` are context-gated before generalization. They are preserved
  in neutral contexts and generalized only near hostile or exclusionary cues
  such as `do not belong`, `should leave`, `deport`, `exclude`, `hate`, or
  `worthless`.

## Transformation Style

Use typed placeholders:

```text
[USER]
[EMAIL]
[PHONE]
[URL]
[ALIAS]
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

Optional Presidio, DPMLM, Hugging Face, or LLM-backed methods should be
evaluated as candidate generators or comparison baselines. They should not
replace the auditable deterministic default unless they improve measured
author-risk reduction and preserve HSD utility.
