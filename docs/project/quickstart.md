# Quickstart

## Verify

```bash
python -m pytest -q
```

The committed synthetic PII stress fixtures live under `tests/fixtures/` and
exercise anonymizer masking, residual-warning metrics, metadata preservation,
and ablation behavior without using official or raw challenge examples.

For strategy and next tasks, read `docs/project/roadmap.md`. The current roadmap
prioritizes authorship-risk evaluation and style scrubbing over adding more
PII-only rules.

## Install As A Package

From the repository root:

```bash
python -m pip install .
contextsafe-hsd --help
```

Build and test a wheel:

```bash
python -m pip wheel . -w dist --no-deps
python -m venv /tmp/contextsafe-hsd-smoke
/tmp/contextsafe-hsd-smoke/bin/python -m pip install dist/contextsafe_hsd-*.whl
/tmp/contextsafe-hsd-smoke/bin/contextsafe-hsd --help
```

## Prepare Public Data

```bash
python -m privhsd.cli prepare-dynahate --download \
  --raw data/public_dev/dynahate_raw.csv \
  --output data/public_dev/dynahate.csv
```

To prepare the broader public evaluation bundle, normalize the recommended
datasets into a shared schema, and write a merged CSV:

```bash
python -m privhsd.cli prepare-recommended-datasets \
  --output-dir data/public_dev \
  --raw-dir data/public_dev/raw \
  --merged-output data/public_dev/recommended_merged.csv
```

The merged schema keeps `id,text,label,source,split,target,type` first, then
adds `platform,source_id,severity,target_categories,rationale_spans,meta`.
Raw downloads stay under ignored `data/public_dev/raw/`.

## Privatize

With the source checkout:

```bash
python -m privhsd.cli anonymize \
  --input data/public_dev/dynahate.csv \
  --output data/outputs/dynahate.privatized.csv \
  --text-col text \
  --id-col id \
  --audit data/outputs/dynahate.audit.json \
  --mode balanced
```

After package install, the same direct CSV input-to-output path is:

```bash
contextsafe-hsd anonymize \
  --input INPUT.csv \
  --output OUTPUT.privatized.csv \
  --text-col text \
  --id-col id \
  --audit OUTPUT.audit.json \
  --mode balanced
```

This appends `privatized_text` and preserves the original columns. For an
exact-format upload file, replace the text column in place and validate shape:

```bash
contextsafe-hsd create-submission \
  --input INPUT.csv \
  --output SUBMISSION.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode balanced \
  --manifest SUBMISSION.manifest.json

contextsafe-hsd validate-submission \
  --source INPUT.csv \
  --submission SUBMISSION.csv \
  --text-col text \
  --id-col id \
  --output SUBMISSION.validation.json
```

Python API equivalent:

```python
from pathlib import Path

import contextsafe_hsd as hsd

hsd.process_csv(
    Path("INPUT.csv"),
    Path("OUTPUT.privatized.csv"),
    text_col="text",
    id_col="id",
    audit_path=Path("OUTPUT.audit.json"),
    mode="balanced",
)
```

For exact-format upload files:

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
    mode="balanced",
)
```

## Evaluate Locally

```bash
python -m privhsd.cli evaluate \
  --input data/outputs/dynahate.privatized.csv \
  --text-col text \
  --privatized-col privatized_text \
  --output data/outputs/dynahate.metrics.json
```

The metrics JSON includes local proxy scores, placeholder density, residual
identifier counts, quasi-identifier flags, target cue retention, and privacy or
over-masking warning counts. These fields are for local comparison and audit,
not official leaderboard scoring.

By default, `balanced` preserves target-group terms for classifier utility.
`privacy` or `--generalize-targets` can generalize target groups, with broad
gender terms preserved in neutral contexts and generalized only near hostile or
exclusionary cues.

## Benchmark Utility

Install the optional local benchmark extra:

```bash
python -m pip install '.[benchmark]'
```

Run the relative utility proxy:

```bash
python -m privhsd.cli benchmark-utility \
  --input data/outputs/dynahate.privatized.csv \
  --text-col text \
  --privatized-col privatized_text \
  --label-col label \
  --id-col id \
  --output data/outputs/dynahate.utility_benchmark.json
```

This trains a lightweight local classifier on original text and reports how much
predictions change on `privatized_text`. It is a proxy for utility loss, not a
production hate-speech detector.

## Train A Local Baseline Classifier

Install the optional classifier extra:

```bash
python -m pip install '.[classifier]'
```

Train a TF-IDF + logistic regression baseline:

```bash
python -m privhsd.cli train-classifier \
  --input data/public_dev/dynahate.csv \
  --text-col text \
  --label-col label \
  --id-col id \
  --model data/outputs/dynahate.classifier.pkl \
  --output data/outputs/dynahate.classifier.train.json
```

Evaluate the saved model:

```bash
python -m privhsd.cli evaluate-classifier \
  --input data/public_dev/dynahate.csv \
  --model data/outputs/dynahate.classifier.pkl \
  --text-col text \
  --label-col label \
  --id-col id \
  --output data/outputs/dynahate.classifier.evaluate.json
```

Predict on privatized text while preserving input rows and metadata:

```bash
python -m privhsd.cli predict-classifier \
  --input data/outputs/dynahate.privatized.csv \
  --model data/outputs/dynahate.classifier.pkl \
  --text-col privatized_text \
  --id-col id \
  --output data/outputs/dynahate.classifier.predictions.csv
```

Classifier metrics are local baseline scores and are not official leaderboard
results.

## Log Official Scores

When submitting to the official leaderboard, copy the structure from
`docs/challenge/score_log_template.md` into a run-specific note and record the commit,
commands, generated artifact paths, local aggregate metrics, official scores,
and audit notes. Do not paste raw challenge examples into the score log.

## Compare Ablations

Run all deterministic variants in one report:

```bash
python -m privhsd.cli ablate \
  --input data/public_dev/dynahate.csv \
  --text-col text \
  --id-col id \
  --label-col label \
  --output data/outputs/dynahate.ablation.json \
  --output-dir data/outputs/dynahate_ablation
```

This compares `identity`, `regex_only`, `balanced`, `privacy`, and
`balanced_with_targets`. It always writes local proxy metrics. If scikit-learn
is installed through `.[benchmark]`, it also adds local utility benchmark
summaries; otherwise the report records `utility_benchmark_skipped` and keeps
the ablation run successful.

## Current Test Status

The baseline implementation should pass:

```text
python -m pytest -q
```
