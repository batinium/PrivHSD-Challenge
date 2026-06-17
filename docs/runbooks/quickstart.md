# Quickstart

Status: active
Last verified: 2026-06-17

## Install

```bash
python -m pip install -e '.[dev]'
```

Optional local helpers:

```bash
python -m pip install -e '.[presidio,scrubadub,hf]'
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
  --hsd-classifier off \
  --llm-verifier off \
  --no-style-simplify-language \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json
```

This is the frozen MVP upload path. It keeps deterministic PII masking,
Presidio/scrubadub PII Assist, strict residual cleanup, cue-safe style
scrubbing, and author-group detector-backed residual masking. It disables
language simplification because the no-simplify run was the best fast
leaderboard baseline.

Use the fine-tuned HF sidecar classifier only when you want local audit evidence:

```bash
--hsd-classifier hf \
--hf-hsd-model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
--hf-hsd-threshold 0.850469
```

GPT/local LLM sidecars are optional backup/audit extensions; enable them
explicitly only when you want second-pass evidence, not for the default
submission path.

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

## Research: Mini Verifier Evaluation

This command is for local verifier comparison runs. It does not change the
official exact CSV output path.

```bash
python -m contextsafe_hsd.cli mini-verifier-eval \
  --endpoint http://100.120.207.64:1234/v1/chat/completions \
  --timeout-seconds 180 \
  --batch-size 10 \
  --progress
```

Current handoff: the runtime verifier is opt-in sidecar audit evidence for
selected sidecar classifier runs. Do not promote any verifier path to automatic
label changes without a substantially better precision/recall and latency
profile.

## Data Handling

Write generated CSVs, manifests, audits, local run notes, datasets, and model
artifacts under ignored `data/` paths. Do not commit raw sensitive examples.
