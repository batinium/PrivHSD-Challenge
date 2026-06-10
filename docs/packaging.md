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
privhsd prepare-dynahate --help
```

## Verified Package Contents

The wheel includes:

- `privhsd.cli`
- `privhsd.csv_pipeline`
- `privhsd.datasets`
- `privhsd.detectors`
- `privhsd.metrics`
- `privhsd.pipeline`

## Release Notes

The package is ready for local pip installation and judge-facing reproducible
setup. Before publishing to a public package index, choose and document a
license, author metadata, and repository URL.

