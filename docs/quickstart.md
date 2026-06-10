# Quickstart

## Verify

```bash
python -m pytest -q
```

## Prepare Public Data

```bash
python -m privhsd.cli prepare-dynahate --download \
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

## Current Test Status

The baseline implementation should pass:

```text
python -m pytest -q
```
