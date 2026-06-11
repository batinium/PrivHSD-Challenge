# Packaging

The package is installable with pip and exposes the `privhsd` console command.

## Local Install

```bash
python -m pip install .
privhsd --help
```

## Build A Wheel

```bash
python -m pip wheel . -w dist --no-deps
```

Install the built wheel in a fresh environment:

```bash
python -m venv /tmp/privhsd-smoke
/tmp/privhsd-smoke/bin/python -m pip install dist/privhsd-*.whl
/tmp/privhsd-smoke/bin/privhsd --help
```

The wheel has no required runtime dependencies. Optional extras are only needed
for evaluator or model-backed commands.

## Direct CSV Input To Output

After installation, the console command can privatize an input CSV directly:

```bash
privhsd anonymize \
  --input INPUT.csv \
  --output OUTPUT.privatized.csv \
  --text-col text \
  --id-col id \
  --audit OUTPUT.audit.json \
  --mode balanced
```

This preserves every source row and column, then appends `privatized_text` by
default. For exact-format challenge uploads, replace the text column in place:

```bash
privhsd create-submission \
  --input INPUT.csv \
  --output SUBMISSION.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode balanced \
  --manifest SUBMISSION.manifest.json

privhsd validate-submission \
  --source INPUT.csv \
  --submission SUBMISSION.csv \
  --text-col text \
  --id-col id \
  --output SUBMISSION.validation.json
```

## Python API

Use `privatize_text` for one string:

```python
from privhsd.pipeline import PrivatizerConfig, privatize_text

result = privatize_text(
    "My name is Amy and Muslims should leave.",
    PrivatizerConfig(mode="balanced"),
)
print(result.text)
```

Use `process_csv` for direct CSV-to-CSV processing:

```python
from pathlib import Path

from privhsd.csv_pipeline import process_csv

process_csv(
    Path("INPUT.csv"),
    Path("OUTPUT.privatized.csv"),
    text_col="text",
    id_col="id",
    audit_path=Path("OUTPUT.audit.json"),
    mode="balanced",
)
```

## Console Commands

After install:

```bash
privhsd anonymize --help
privhsd evaluate --help
privhsd benchmark-utility --help
privhsd ablate --help
privhsd train-classifier --help
privhsd evaluate-classifier --help
privhsd predict-classifier --help
privhsd create-submission --help
privhsd validate-submission --help
privhsd rerank-candidates --help
privhsd prepare-dynahate --help
```

## Optional Extras

The base package remains dependency-free. Install the local utility benchmark
extra only when you need the scikit-learn proxy evaluator:

```bash
python -m pip install '.[benchmark]'
privhsd benchmark-utility --help
```

Install the local baseline classifier extra only when you need CSV
train/evaluate/predict classifier workflows:

```bash
python -m pip install '.[classifier]'
privhsd train-classifier --help
```

## Verified Package Contents

The wheel includes the `privhsd` package modules and excludes tests, docs,
agents, local data, and generated outputs. The package smoke test should verify:

- `privhsd --help`
- `privhsd anonymize` on a fixture CSV
- `privhsd create-submission` plus `privhsd validate-submission`
- Python imports for `privhsd.pipeline` and `privhsd.csv_pipeline`

## Release Notes

The package is ready for local pip installation and judge-facing reproducible
setup. Before publishing to a public package index, choose and document a
license, author metadata, and repository URL.
