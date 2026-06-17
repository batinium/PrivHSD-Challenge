# Quickstart

Status: active
Last verified: 2026-06-16

## Install

```bash
python -m pip install -e '.[dev]'
```

Optional local helpers:

```bash
python -m pip install -e '.[presidio,scrubadub]'
```

## Verify

```bash
python -m ruff check contextsafe_hsd tests workbench/backend
python -m pytest -q
python -m contextsafe_hsd.cli --help
python -m contextsafe_hsd.cli protect --help
```

## Protect A CSV

```bash
python -m contextsafe_hsd.cli protect \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --llm-review local-llm \
  --local-llm-endpoint http://100.120.207.64:1234/v1/chat/completions \
  --local-llm-model openai/gpt-oss-20b \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json
```

Use `--llm-review off` when no local OpenAI-compatible server is available.

## Validate

```bash
python -m contextsafe_hsd.cli validate-submission \
  --source INPUT.csv \
  --submission OUTPUT.csv \
  --text-col text \
  --output OUTPUT.validation.json
```

## Profile Incoming Data

```bash
python -m contextsafe_hsd.cli profile-dataset \
  --input INPUT.csv \
  --text-col text \
  --id-col ID \
  --output INPUT.profile.json
```

The profile command reports schema and aggregate counts without printing raw row
text.

## Research: Mini 4B Verifier Ablation

This command is for local research runs only. It does not change the official
exact CSV output path.

```bash
python -m contextsafe_hsd.cli mini-4b-verifier-ablation \
  --endpoint http://100.120.207.64:1234/v1/chat/completions \
  --timeout-seconds 180 \
  --batch-size 10 \
  --progress
```

Current handoff: small-model verifier runs are research-only offline audit
evidence. Do not promote the Qwen verifier path to automatic label changes
without a substantially better precision/recall and latency profile.

## Data Handling

Write generated CSVs, manifests, audits, local run notes, datasets, and model
artifacts under ignored `data/` paths. Do not commit raw sensitive examples.
