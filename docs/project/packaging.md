# Packaging

The distribution package is `ContextSafe-HSD`. It exposes the
`contextsafe-hsd` console command and a `contextsafe_hsd` Python import. The
older `privhsd` command and import remain available for compatibility with
existing experiment scripts.

## Local Install

```bash
python -m pip install .
contextsafe-hsd --help
```

## Build A Wheel

```bash
python -m pip wheel . -w dist --no-deps
```

Install the built wheel in a fresh environment:

```bash
python -m venv /tmp/contextsafe-hsd-smoke
/tmp/contextsafe-hsd-smoke/bin/python -m pip install dist/contextsafe_hsd-*.whl
/tmp/contextsafe-hsd-smoke/bin/contextsafe-hsd --help
```

The wheel has no required runtime dependencies. Optional extras are only needed
for evaluator or model-backed commands.

## Direct CSV Input To Output

After installation, the console command can privatize an input CSV directly:

```bash
contextsafe-hsd anonymize \
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

## Python API

Use the top-level package API for normal cases.

Process a CSV and append `privatized_text`:

```python
from pathlib import Path

import contextsafe_hsd as hsd

summary = hsd.process_csv(
    Path("INPUT.csv"),
    Path("OUTPUT.privatized.csv"),
    text_col="text",
    id_col="id",
    audit_path=Path("OUTPUT.audit.json"),
    mode="balanced",
)
print(summary["metrics"])
```

Create an exact-format challenge upload CSV:

```python
from pathlib import Path

import contextsafe_hsd as hsd

manifest = hsd.create_submission(
    Path("INPUT.csv"),
    Path("SUBMISSION.csv"),
    text_cols=["text"],
    id_col="id",
    manifest_path=Path("SUBMISSION.manifest.json"),
    replace_text=True,
    mode="balanced",
)

validation = hsd.validate_submission(
    Path("INPUT.csv"),
    Path("SUBMISSION.csv"),
    text_cols=["text"],
    id_col="id",
    output_path=Path("SUBMISSION.validation.json"),
)
```

Use `privatize_text` for one string:

```python
from contextsafe_hsd import PrivatizerConfig, privatize_text

result = privatize_text(
    "My name is Amy and Muslims should leave.",
    PrivatizerConfig(mode="balanced"),
)
print(result.text)
```

## Console Commands

After install:

```bash
contextsafe-hsd anonymize --help
contextsafe-hsd evaluate --help
contextsafe-hsd benchmark-utility --help
contextsafe-hsd ablate --help
contextsafe-hsd train-classifier --help
contextsafe-hsd evaluate-classifier --help
contextsafe-hsd predict-classifier --help
contextsafe-hsd create-submission --help
contextsafe-hsd validate-submission --help
contextsafe-hsd rerank-candidates --help
contextsafe-hsd prepare-dynahate --help
```

## Optional Extras

The base package remains dependency-free. Install the local utility benchmark
extra only when you need the scikit-learn proxy evaluator:

```bash
python -m pip install '.[benchmark]'
contextsafe-hsd benchmark-utility --help
```

Install the local baseline classifier extra only when you need CSV
train/evaluate/predict classifier workflows:

```bash
python -m pip install '.[classifier]'
contextsafe-hsd train-classifier --help
```

## Verified Package Contents

The wheel includes the `contextsafe_hsd` public alias and the `privhsd`
implementation modules, and excludes tests, docs, agents, local data, and
generated outputs. The package smoke test should verify:

- `contextsafe-hsd --help`
- `contextsafe-hsd anonymize` on a fixture CSV
- `contextsafe-hsd create-submission` plus `contextsafe-hsd validate-submission`
- Python imports for `contextsafe_hsd.process_csv`,
  `contextsafe_hsd.create_submission`, and `contextsafe_hsd.privatize_text`

## Release Notes

The package is ready for local pip installation and judge-facing reproducible
setup. Before publishing to a public package index, choose and document a
license, author metadata, and repository URL.
