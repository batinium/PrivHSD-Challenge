# PrivHSD Challenge

Privacy-preserving text privatization for hate speech detection datasets.

This repository is a fresh implementation for the PrivHSD hackathon track. The
goal is not to build the main hate speech classifier. The goal is to transform
text so privacy-sensitive details are reduced while hate-speech detection cues
remain useful.

```text
CSV with text
  -> privacy-preserving transformation
  -> CSV with privatized_text
  -> audit JSON and local proxy metrics
```

## Start Here

- [docs/README.md](docs/README.md) - documentation index.
- [docs/challenge_requirements.md](docs/challenge_requirements.md) - what the challenge expects.
- [docs/pipeline_design.md](docs/pipeline_design.md) - active implementation contract.
- [docs/dataset_plan.md](docs/dataset_plan.md) - public and official dataset plan.
- [docs/quickstart.md](docs/quickstart.md) - commands for running the pipeline.
- [agents/README.md](agents/README.md) - instructions for coding agents.
- [agents/task_board.md](agents/task_board.md) - implementation task board.

## Current Implementation

The active package is `privhsd/`.

```text
privhsd/
  cli.py
  csv_pipeline.py
  detectors.py
  metrics.py
  pipeline.py
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

## Modes

- `utility`: conservative privacy masking.
- `balanced`: default; preserve hate-speech utility while masking identifiers.
- `privacy`: more aggressive; can generalize known target-group mentions.

Use `balanced` first for official evaluator submissions.

## Agent Rule

Coding agents should read [agents/README.md](agents/README.md) before changing
code. The sibling `../ContextSafe-HSD` project is reference material only; this
repo is the active challenge implementation.
