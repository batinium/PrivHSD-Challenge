# ContextSafe-HSD

Local privacy-preserving text privatization for hate-speech detection datasets.

The goal is to reduce author-identifying signal while preserving the semantic
cues needed by downstream hate-speech detection. The repository is not trying
to be the final hate-speech classifier.

## Repository Layout

```text
contextsafe_hsd/     Branded public Python package alias
privhsd/              Python package and CLI implementation
tests/                Unit and regression tests
docs/project/         Local project docs and testing workflow
docs/challenge/       Hackathon rules, policy framing, submission notes
docs/research/        Background research and experiment notes
docs/archive/         Historical agent handoffs and run logs
data/                 Ignored local datasets and generated outputs
```

Start with [docs/README.md](docs/README.md), then use
[docs/project/quickstart.md](docs/project/quickstart.md) and
[docs/project/pipeline_design.md](docs/project/pipeline_design.md).

## Core Test Workflow

Run tests:

```bash
.venv/bin/python -m pytest -q
```

Create an exact-format baseline candidate:

```bash
.venv/bin/python -m privhsd.cli create-submission \
  --input data/public_dev/recommended_merged.csv \
  --output data/outputs/recommended_merged.balanced.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode balanced \
  --manifest data/outputs/recommended_merged.balanced.manifest.json
```

Validate upload shape:

```bash
.venv/bin/python -m privhsd.cli validate-submission \
  --source data/public_dev/recommended_merged.csv \
  --submission data/outputs/recommended_merged.balanced.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/recommended_merged.balanced.validation.json
```

Run source-aware regression:

```bash
.venv/bin/python -m privhsd.cli source-regression-report \
  --original data/public_dev/recommended_merged.csv \
  --protected data/outputs/recommended_merged.balanced.csv \
  --original-text-col text \
  --protected-text-col text \
  --id-col id \
  --group-col source \
  --group-col label \
  --group-col split \
  --group-col platform \
  --group-col type \
  --output data/outputs/recommended_merged.balanced.source_regression.json
```

Run semantic triage to decide whether Qwen is needed:

```bash
.venv/bin/python -m privhsd.cli semantic-triage-report \
  --input data/public_dev/recommended_merged.csv \
  --protected data/outputs/recommended_merged.balanced.csv \
  --text-col text \
  --privatized-col text \
  --id-col id \
  --label-col label \
  --source-col source \
  --sample-size 20000 \
  --sample-strategy source_label_round_robin \
  --output data/outputs/recommended_merged.balanced.semantic_triage.json \
  --queue-output data/outputs/recommended_merged.balanced.semantic_triage.queue.csv
```

The triage report routes rows to:

- `repair_before_model_review`
- `qwen_semantic_check`
- `no_review`

Qwen should only be used on the semantic-review queue, not on the whole dataset.

## Python Package API

After `pip install .`, the installed command is `contextsafe-hsd`:

```bash
contextsafe-hsd create-submission --help
contextsafe-hsd validate-submission --help
```

The Python API is available as `contextsafe_hsd`. The older `privhsd` import
remains as a compatibility alias for local experiments.

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
```

For an exact-format challenge upload:

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
```

## Performance Notes

- Deterministic masking, validation, context tags, and cue checks are CPU regex
  workloads. GPU does not help these stages unless the algorithm is rewritten.
- HF transformer probes use `--device auto` and will use CUDA when the Python
  environment has CUDA-enabled PyTorch.
- Qwen should run through LM Studio, which can use the GPU independently of the
  local Python venv.
- This venv currently has CPU-only PyTorch, so Python HF models will not use the
  visible NVIDIA GPU until CUDA-enabled PyTorch is installed.
- Use `semantic-triage-report --sample-size ...` for interactive testing and
  reserve full semantic triage for overnight or a future parallelized run.

## Robustness Policy

- Deterministic masking is the base layer.
- Cue checks catch target/action/negation/modality loss.
- Source regression catches slice-specific regressions.
- Optional trained classifiers provide confidence and margin uncertainty.
- Qwen is a selective semantic checker or candidate source, never the default
  dataset rewriter.

Generated datasets, challenge data, and reports under `data/` are ignored by
git. Keep raw sensitive examples out of markdown, commits, and issue comments.
