# Quickstart

## Verify

```bash
python -m pytest -q
```

## Prepare Public Data

```bash
python scripts/prepare_dynahate.py --download \
  --raw data/public_dev/dynahate_raw.csv \
  --output data/public_dev/dynahate.csv
```

## Privatize

```bash
python -m privhsd.cli anonymize \
  --input data/public_dev/dynahate.csv \
  --output data/outputs/dynahate.privatized.csv \
  --text-col text \
  --id-col id \
  --audit data/outputs/dynahate.audit.json \
  --mode balanced
```

## Evaluate Locally

```bash
python -m privhsd.cli evaluate \
  --input data/outputs/dynahate.privatized.csv \
  --text-col text \
  --privatized-col privatized_text \
  --output data/outputs/dynahate.metrics.json
```

## Current Test Status

The baseline implementation should pass:

```text
6 passed
```

