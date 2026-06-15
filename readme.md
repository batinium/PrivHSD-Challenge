# ContextSafe-HSD

ContextSafe-HSD is a local, auditable preprocessing pipeline for hate-speech
detection datasets. It rewrites CSV text to reduce personal and
re-identifying details while preserving the target, hostility, negation,
modality, quotation, counterspeech, and reporting cues that downstream review
may need.

It is not a production hate-speech classifier, moderation system, legal
decision system, or promise that every identifier has been removed. The goal is
to reduce, check, and report residual privacy risk while keeping the cleaned
CSV usable.

## Public Pipeline

```text
Input CSV
  -> Privacy Detection
  -> Meaning Protection
  -> Verification
  -> exact cleaned CSV + manifest
```

The default human-facing command is `protect`. It uses the current exact
`auto` path internally, preserves the input CSV schema, writes cleaned text
back to the text column, and records an audit manifest when requested.

```bash
contextsafe-hsd protect \
  --input INPUT.csv \
  --output data/outputs/INPUT.protected.csv \
  --text-col text \
  --manifest data/outputs/INPUT.protected.manifest.json
```

Default behavior is `--preset exact`: the output has the same columns, order,
row count, and non-text values as the source CSV. If you need a stable row key
for review, pass a privacy-safe fingerprint such as `--id-col case_fingerprint`
rather than a raw author/user identifier. HSD advisory checks, if
available, are verification checks only; exact output does not append HSD
prediction columns.

## Presets

| Preset | Output | Use |
| --- | --- | --- |
| `exact` | Cleaned CSV in the original schema plus manifest | Default upload-style path. |
| `analysis` | Local enriched CSV with advisory HSD columns | Review and triage only; not exact-format. |
| `audit` | Exact cleaned CSV plus deeper sidecar/audit reporting when supported | Local audit before sharing or submission. |

The deterministic privacy baseline always runs. Optional local PII Assist
components may add evidence when installed and configured, but downloads are
not part of sensitive-data processing by default.

Older commands such as `create-submission`, `sanitize-classify`, and
`anonymize` remain available for compatibility, research, and debugging. The
recommended public workflow is `protect`.

## Install And Verify

Use the named micromamba environment from `environment.yml`. If the environment
already exists, update it:

```bash
micromamba env update -n contextsafe-hsd -f environment.yml
```

For a new machine or checkout:

```bash
micromamba env create -f environment.yml
```

Then verify through the named environment from any directory:

```bash
micromamba run -n contextsafe-hsd -e PYTHONNOUSERSITE=1 python -m pytest -q
micromamba run -n contextsafe-hsd -e PYTHONNOUSERSITE=1 contextsafe-hsd protect --help
```

For manual shell use, activate the environment from the repository root:

```bash
micromamba activate contextsafe-hsd
```

This repository also includes `.envrc` for optional automatic activation when
entering the directory with `direnv`. After installing and enabling `direnv`,
run this once from the repository root:

```bash
direnv allow
```

For package-installed usage, `contextsafe-hsd` dispatches to the same CLI as
`python -m contextsafe_hsd.cli`.

`requirements-venv.lock` preserves the dependency snapshot from the previous
`.venv` before removal; `environment.yml` is the portable setup source.
The `PYTHONNOUSERSITE=1` run option keeps user-level Python packages from
masking packages installed inside the micromamba environment.

## Validate Exact Output

```bash
contextsafe-hsd validate-submission \
  --source INPUT.csv \
  --submission data/outputs/INPUT.protected.csv \
  --text-col text \
  --output data/outputs/INPUT.validation.json
```

Add `--id-col case_fingerprint` only when both files contain the same
privacy-safe stable key.

The manifest and validation report are sidecars. They should not contain raw
row text and should be stored under ignored `data/` paths with generated CSVs,
model weights, and run notes.

## Repository Map

```text
contextsafe_hsd/     Public Python package and implementation
tests/               Synthetic and regression tests
docs/runbooks/       Operational workflows and commands
docs/reference/      Stable contracts and architecture
docs/planning/       Current evidence, risks, decisions, and roadmap
docs/research/       Methodology and governance rationale
docs/challenge/      Rules, rights framing, checklist, and pitch material
workbench/           Decoupled FastAPI + React demo app
data/                Ignored local datasets, models, and reports
```

Start with [docs/runbooks/quickstart.md](docs/runbooks/quickstart.md). For the
architecture, read [docs/reference/pipeline.md](docs/reference/pipeline.md) and
[docs/reference/providers_and_models.md](docs/reference/providers_and_models.md).
Current readiness and caveats live in
[docs/planning/current_status.md](docs/planning/current_status.md).

## Python API

The public CLI wraps the exact `auto` path. Python callers can use the same
path through `create_submission`:

```python
from pathlib import Path

import contextsafe_hsd as hsd

hsd.create_submission(
    Path("INPUT.csv"),
    Path("SUBMISSION.csv"),
    text_cols=["text"],
    id_col="case_fingerprint",
    manifest_path=Path("SUBMISSION.manifest.json"),
    replace_text=True,
    mode="auto",
)
```

## Data Policy

Downloaded datasets, generated CSVs, model weights, manifests, reports, and
run notes belong under ignored `data/` paths. Keep raw sensitive examples out
of markdown, commits, issues, screenshots, and presentation material.
