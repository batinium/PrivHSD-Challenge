# Pipeline Design

## Current Package

The active implementation is in `privhsd/`.

```text
privhsd/
  cli.py           command-line interface
  csv_pipeline.py  CSV read/write, audit, and batch processing
  detectors.py     deterministic span detectors
  metrics.py       local privacy/utility proxy metrics
  pipeline.py      single-text privatization API
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

