# PrivHSD Challenge

Privacy-preserving text privatization for hate speech detection datasets.

This repository is a fresh implementation for the PrivHSD hackathon track. The
goal is not to build the main hate speech classifier. The goal is to transform
text so privacy-sensitive details are reduced while hate-speech detection cues
remain useful.

The webinar framing is stricter than simple PII removal: reduce
author-identifying signals while preserving hate-speech detection signal.

```text
CSV with text
  -> privacy-preserving transformation
  -> CSV with privatized_text
  -> audit JSON and local proxy metrics
```

## Start Here

- [docs/README.md](docs/README.md) - documentation index.
- [docs/challenge_requirements.md](docs/challenge_requirements.md) - what the challenge expects.
- [docs/roadmap.md](docs/roadmap.md) - current strategy and next technical bets.
- [docs/pipeline_design.md](docs/pipeline_design.md) - active implementation contract.
- [docs/dataset_plan.md](docs/dataset_plan.md) - public and official dataset plan.
- [docs/quickstart.md](docs/quickstart.md) - commands for running the pipeline.
- [docs/score_log_template.md](docs/score_log_template.md) - official submission score log template.
- [agents/README.md](agents/README.md) - instructions for coding agents.
- [agents/task_board.md](agents/task_board.md) - implementation task board.

## Current Implementation

The active package is `privhsd/`.

```text
privhsd/
  ablation.py
  classifier.py
  cli.py
  csv_pipeline.py
  detectors.py
  metrics.py
  pipeline.py
  utility_benchmark.py
```

The default path is deterministic and does not require LLM calls.

## Quick Run

Run tests:

```bash
python -m pytest -q
```

Prepare the recommended public test dataset:

```bash
python -m privhsd.cli prepare-dynahate --download \
  --raw data/public_dev/dynahate_raw.csv \
  --output data/public_dev/dynahate.csv
```

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

Evaluate local proxy metrics:

```bash
python -m privhsd.cli evaluate \
  --input data/outputs/dynahate.privatized.csv \
  --text-col text \
  --privatized-col privatized_text \
  --output data/outputs/dynahate.metrics.json
```

The metrics report includes privacy/utility proxy scores, placeholder density,
residual identifier counts, quasi-identifier flags, target cue retention, and
privacy or over-masking warnings.

Committed synthetic PII stress fixtures under `tests/fixtures/` cover handles,
emails, phone numbers, URLs, IP addresses, dates, names, locations,
schools/organizations, IDs, aliases, and direct-plus-quasi identifier
combinations without using official challenge examples.

Optionally benchmark downstream utility loss with a local classifier:

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

The utility benchmark is a relative proxy for privatization impact. It is not
the project’s core classifier and does not replace the official evaluator.

Optionally train a local baseline classifier:

```bash
python -m pip install '.[classifier]'
python -m privhsd.cli train-classifier \
  --input data/public_dev/dynahate.csv \
  --text-col text \
  --label-col label \
  --id-col id \
  --model data/outputs/dynahate.classifier.pkl \
  --output data/outputs/dynahate.classifier.train.json
python -m privhsd.cli evaluate-classifier \
  --input data/public_dev/dynahate.csv \
  --model data/outputs/dynahate.classifier.pkl \
  --text-col text \
  --label-col label \
  --id-col id \
  --output data/outputs/dynahate.classifier.evaluate.json
python -m privhsd.cli predict-classifier \
  --input data/outputs/dynahate.privatized.csv \
  --model data/outputs/dynahate.classifier.pkl \
  --text-col privatized_text \
  --id-col id \
  --output data/outputs/dynahate.classifier.predictions.csv
```

The classifier commands are local scikit-learn baselines. Prediction CSVs
preserve input rows and metadata, then add `predicted_label` and
`predicted_confidence`.

Compare all built-in privatization variants:

```bash
python -m privhsd.cli ablate \
  --input data/public_dev/dynahate.csv \
  --text-col text \
  --id-col id \
  --label-col label \
  --output data/outputs/dynahate.ablation.json \
  --output-dir data/outputs/dynahate_ablation
```

The ablation report compares `identity`, `regex_only`, `balanced`, `privacy`,
and `balanced_with_targets`. It includes local proxy metrics for every variant
and records `utility_benchmark_skipped` when the optional benchmark dependency
is unavailable.

## Modes

- `utility`: conservative privacy masking.
- `balanced`: default; preserve hate-speech utility while masking identifiers.
- `privacy`: more aggressive; can generalize known target-group mentions.

Use `balanced` first for official evaluator submissions.

## Current Roadmap

Next work should focus on authorship-risk evaluation and style scrubbing:

- train an author classifier when official data includes an author column
- normalize style cues such as casing, punctuation, repeated characters,
  emojis, spacing, and signatures
- rerank candidate privatizations by author-risk reduction and HSD utility
- treat Presidio, DPMLM, and specialized LLM rewriting as optional experiments
  rather than default dependencies

## Agent Rule

Coding agents should read [agents/README.md](agents/README.md) before changing
code. The sibling `../ContextSafe-HSD` project is reference material only; this
repo is the active challenge implementation.
