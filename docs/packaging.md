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

The wheel includes:

- `privhsd.cli`
- `privhsd.ablation`
- `privhsd.classifier`
- `privhsd.csv_pipeline`
- `privhsd.datasets`
- `privhsd.detectors`
- `privhsd.metrics`
- `privhsd.pipeline`
- `privhsd.utility_benchmark`

## Release Notes

The package is ready for local pip installation and judge-facing reproducible
setup. Before publishing to a public package index, choose and document a
license, author metadata, and repository URL.
