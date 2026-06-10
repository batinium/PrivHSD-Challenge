# Current Handoff

Date: 2026-06-10

## Current Repo State

The active repository is:

```text
/home/bati/projects/PrivHSD-Challenge
```

The sibling project `../ContextSafe-HSD` is reference material only. Do not
continue that older product shape unless explicitly asked. This repo is now a
fresh PrivHSD-specific implementation.

Known untracked files at handoff time:

```text
Webinar.txt
prompt.md
```

`Webinar.txt` is the noisy webinar transcript and was intentionally not
committed. `prompt.md` is the current overnight-agent instruction file and was
also left uncommitted.

## What Has Been Built

Python package:

```text
privhsd
```

Main modules:

- `privhsd.ablation` - multi-mode local ablation report runner.
- `privhsd.classifier` - optional scikit-learn baseline classifier train/evaluate/predict workflows.
- `privhsd.cli` - console interface.
- `privhsd.csv_pipeline` - CSV read/write, batch privatization, audit JSON.
- `privhsd.datasets` - Dynahate download/normalization helper.
- `privhsd.detectors` - deterministic regex/context span detectors.
- `privhsd.metrics` - local privacy/utility proxy metrics.
- `privhsd.pipeline` - single-text privatization API.
- `privhsd.utility_benchmark` - optional scikit-learn utility-delta benchmark.

Committed synthetic fixtures:

- `tests/fixtures/synthetic_pii_stress.csv`
- `tests/fixtures/synthetic_pii_residual_metrics.csv`

These fixtures are synthetic only and cover noisy handles, emails, phone
numbers, URLs, IP addresses, dates, names, locations, schools/organizations,
IDs, aliases, and direct-plus-quasi identifier combinations.

Console command after install:

```bash
privhsd
```

Available subcommands:

```bash
privhsd anonymize
privhsd evaluate
privhsd benchmark-utility
privhsd ablate
privhsd train-classifier
privhsd evaluate-classifier
privhsd predict-classifier
privhsd prepare-dynahate
```

## Current Documentation

Read in this order:

1. `docs/challenge_requirements.md`
2. `docs/pipeline_design.md`
3. `docs/dataset_plan.md`
4. `docs/quickstart.md`
5. `docs/packaging.md`
6. `docs/research_oss_tech.md`
7. `agents/README.md`
8. `agents/task_board.md`
9. `agents/coding_rules.md`

## Verified Commands

Tests:

```bash
python -m pytest -q
```

Last verified result:

```text
20 passed, 3 skipped
```

Optional classifier environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[classifier]'
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
```

Last optional-environment result:

```text
22 passed, 1 skipped
```

Last verified date:

```text
2026-06-10
```

Build wheel:

```bash
python -m pip wheel . -w /tmp/privhsd-wheelhouse --no-deps --no-cache-dir
```

Install-test wheel:

```bash
python -m venv /tmp/privhsd-install-test
/tmp/privhsd-install-test/bin/pip install --no-index --find-links /tmp/privhsd-wheelhouse privhsd
/tmp/privhsd-install-test/bin/privhsd --help
/tmp/privhsd-install-test/bin/privhsd prepare-dynahate --help
```

Dataset prep:

```bash
privhsd prepare-dynahate --download \
  --raw data/public_dev/dynahate_raw.csv \
  --output data/public_dev/dynahate.csv
```

Downloaded/normalized dataset at handoff time:

```text
data/public_dev/dynahate_raw.csv
data/public_dev/dynahate.csv
```

Normalized row count:

```text
41,144
```

Dataset folders are ignored by git.

Classifier synthetic smoke:

```bash
.venv/bin/python -m privhsd.cli train-classifier \
  --input tests/fixtures/synthetic_pii_stress.csv \
  --text-col text \
  --label-col label \
  --id-col id \
  --model data/outputs/synthetic_pii.classifier.pkl \
  --output data/outputs/synthetic_pii.classifier.train.json \
  --test-size 0.25 \
  --random-state 7

.venv/bin/python -m privhsd.cli evaluate-classifier \
  --input tests/fixtures/synthetic_pii_stress.csv \
  --model data/outputs/synthetic_pii.classifier.pkl \
  --text-col text \
  --label-col label \
  --id-col id \
  --output data/outputs/synthetic_pii.classifier.evaluate.json

.venv/bin/python -m privhsd.cli predict-classifier \
  --input tests/fixtures/synthetic_pii_stress.csv \
  --model data/outputs/synthetic_pii.classifier.pkl \
  --text-col text \
  --id-col id \
  --label-col label \
  --output data/outputs/synthetic_pii.classifier.predictions.csv
```

Synthetic smoke summary: train split used 6 train rows and 2 dev rows; evaluate
and predict ran on all 8 synthetic rows; prediction counts were 4 `hate` and 4
`nothate`; evaluate macro-F1 was 0.873. Generated files are under ignored
`data/outputs/`.

## Git Status

Previous pushed commit before A09/A10:

```text
26ede61 Harden pip package setup
```

Previous relevant commits:

```text
d6b1201 Build initial PrivHSD privatization pipeline
2176711 Handle lowercase Dynahate CSV headers
```

Remote:

```text
origin https://github.com/batinium/PrivHSD-Challenge.git
```

Branch:

```text
main
```

Files changed by A09/A10/A11/A12:

```text
agents/current_handoff.md
agents/task_board.md
docs/README.md
docs/packaging.md
docs/pipeline_design.md
docs/quickstart.md
docs/research_oss_tech.md
privhsd/ablation.py
privhsd/cli.py
privhsd/metrics.py
privhsd/utility_benchmark.py
pyproject.toml
readme.md
tests/test_ablation.py
tests/test_metrics.py
tests/test_utility_benchmark.py
```

`Webinar.txt` is still the intentionally untracked noisy webinar transcript.
The temporary repo-local micromamba env `./.venv` was removed after creation.
The existing `contextsafe-hsd` micromamba env is present, but did not contain
`pytest` or `scikit-learn` when checked with `PYTHONNOUSERSITE=1`.

## Next Tasks

The task board is `agents/task_board.md`.

Completed today:

```text
A13 - Added synthetic PII stress fixtures and tests.
A16 - Added optional local baseline classifier train/evaluate/predict workflows.
```

Recommended next task:

```text
A04 - Improve target-group handling with a safe preserve/generalize policy.
```

Reason:

A13 now validates anonymizer fixture coverage, residual-warning metrics, row
order/metadata preservation, and ablation behavior on committed synthetic data.
A16 now provides optional classifier workflows and local JSON metrics. A04 and
A06 are next before GUI work.

## A09 Research Output

A09 is complete. Created:

```text
docs/research_oss_tech.md
```

The file contains:

- ranked OSS shortlist
- academic findings with citation links
- integrate-now / later / avoid recommendations
- testing and ablation plan
- risks and fallback options

Updated:

```text
agents/task_board.md
```

New implementation tasks from the research findings:

- A10: scikit-learn utility benchmark. Done.
- A11: ablation runner. Done.
- A12: TAB-inspired metrics and over-masking warnings. Done.
- A13: synthetic PII stress fixtures and tests.
- A14: optional Presidio/spaCy detector comparison.
- A15: optional local neural utility evaluators after license checks.
- A16: local baseline hate-speech classifier pipeline.

## Important Constraints

- Core pipeline must remain runnable without external LLM API calls.
- Preserve CSV row count and row order.
- Preserve labels, IDs, and metadata.
- Add `privatized_text` by default.
- Keep audit JSON machine-readable.
- Use `balanced` mode first for official evaluator submissions.
- Do not commit downloaded datasets or official challenge data.
- Do not expose raw official examples in docs/screenshots.

## Current Product Shape

The current code is a preprocessing layer:

```text
CSV with text
  -> privacy span detection
  -> typed text privatization
  -> CSV with privatized_text
  -> audit JSON
  -> local proxy metrics and warning rollups
```

A baseline local classifier is a planned first-class pipeline task, but the
anonymizer should remain runnable without classifier dependencies or external
LLM APIs.
