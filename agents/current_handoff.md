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

Only known untracked file at handoff time:

```text
Webinar.txt
```

It is the noisy webinar transcript and was intentionally not committed.

## What Has Been Built

Python package:

```text
privhsd
```

Main modules:

- `privhsd.cli` - console interface.
- `privhsd.csv_pipeline` - CSV read/write, batch privatization, audit JSON.
- `privhsd.datasets` - Dynahate download/normalization helper.
- `privhsd.detectors` - deterministic regex/context span detectors.
- `privhsd.metrics` - local privacy/utility proxy metrics.
- `privhsd.pipeline` - single-text privatization API.

Console command after install:

```bash
privhsd
```

Available subcommands:

```bash
privhsd anonymize
privhsd evaluate
privhsd prepare-dynahate
```

## Current Documentation

Read in this order:

1. `docs/challenge_requirements.md`
2. `docs/pipeline_design.md`
3. `docs/dataset_plan.md`
4. `docs/quickstart.md`
5. `docs/packaging.md`
6. `agents/README.md`
7. `agents/task_board.md`
8. `agents/coding_rules.md`

## Verified Commands

Tests:

```bash
python -m pytest -q
```

Last verified result:

```text
7 passed
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

## Git Status

Latest pushed commit:

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

## Next Tasks

The task board is `agents/task_board.md`.

Recommended next task:

```text
A09 - Run Consensus/academic search for OSS technologies.
```

Reason:

Before adding heavier evaluation or UI features, decide which OSS technologies
are worth integrating under hackathon constraints.

If research tooling is unavailable, proceed with:

```text
A03 - Build minimal UI around existing privhsd functions.
```

## A09 Research Output Location

Create:

```text
docs/research_oss_tech.md
```

The file should contain:

- ranked OSS shortlist
- academic findings with citation links
- integrate-now / later / avoid recommendations
- testing and ablation plan
- risks and fallback options

After writing it, update:

```text
agents/task_board.md
```

Add concrete implementation tasks from the research findings.

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

The project is a preprocessing layer:

```text
CSV with text
  -> privacy span detection
  -> typed text privatization
  -> CSV with privatized_text
  -> audit JSON
  -> local proxy metrics
```

It is not primarily a classifier or moderation enforcement tool.

