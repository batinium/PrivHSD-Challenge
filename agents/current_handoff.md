# Current Handoff

Date: 2026-06-11

## Repo State

Repository:

```text
/home/bati/projects/PrivHSD-Challenge
```

Branch and pushed HEAD:

```text
main
fd3957e Refocus roadmap on authorship risk
```

Untracked files:

```text
Webinar.txt
prompt.md
```

`Webinar.txt` is currently empty. The webinar slide screenshots are outside the
repo at:

```text
/mnt/c/Users/noutr/Downloads/Ss
```

Do not commit downloaded datasets, official challenge data, or generated
`data/outputs/` artifacts.

## Read First

1. `docs/challenge_requirements.md`
2. `docs/roadmap.md`
3. `docs/pipeline_design.md`
4. `agents/task_board.md`
5. `agents/coding_rules.md`

Use `overnight_report.md` for the detailed overnight history and experiment
results. Keep this handoff short.

## Current System

The project is a local text-to-text privatization pipeline for PrivHSD:

```text
CSV text
  -> deterministic privacy detection
  -> typed placeholder privatization
  -> row-preserving CSV with privatized_text
  -> audit JSON and local metrics
  -> optional ablation/classifier reports
```

CLI commands:

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

Core `privhsd anonymize` remains dependency-light and does not require
scikit-learn, external LLM APIs, Presidio, or Hugging Face models.

## Webinar Correction

The challenge is broader than PII masking.

Goal:

```text
minimize author-identifying signal
maximize hate-speech detection signal
```

Important slide takeaways:

- Authorship identification is itself a classification task and should be made
  harder.
- Presidio was shown as an insufficient baseline, not a solution.
- DPMLM-style rewriting can work, but it is complex and parameter-sensitive.
- Generic LLM prompting scored poorly; LLM use must be specialized,
  constrained, and evaluated.
- Winning the website leaderboard does not automatically win the hackathon.
  Judges also evaluate framing, rights impact, feasibility, transparency,
  limitations, and presentation.

## Completed Milestones

- A01: package, CLI, CSV pipeline, metrics, and tests.
- A04: safer target-group preserve/generalize policy.
- A05/A10: optional scikit-learn utility benchmark.
- A06: official score-log template.
- A07: packaging/install instructions.
- A09: research notes and implementation tasks.
- A11: ablation runner.
- A12: richer metrics and warnings.
- A13: synthetic PII stress fixtures and tests.
- A16: optional local classifier train/evaluate/predict workflow.

Recent commits:

```text
f98522a Record Dynahate experiment summaries
75eaf8d Add official score log template
dff8fb2 Improve target group generalization policy
b9254c7 Add local classifier workflows
1e29e3a Add synthetic PII stress fixtures
```

## Verification

Latest base suite:

```text
python -m pytest -q
22 passed, 3 skipped
```

Latest optional classifier suite:

```text
.venv/bin/python -m pytest -q
24 passed, 1 skipped
```

Package smoke passed: built a wheel, installed it in `/tmp/privhsd-install-test`,
and verified root plus classifier CLI help.

## Dynahate Summary

Public Dynahate exists locally at `data/public_dev/dynahate.csv` and is ignored
by git.

Dataset:

- rows: 41,144
- labels: 22,175 `hate`, 18,969 `nothate`
- splits: 32,924 train, 4,100 dev, 4,120 test

Balanced anonymizer result:

- placeholders: 2,315
- residual identifiers: 3
- residual quasi-identifiers: 0
- target cue retention: 0.9994
- character retention: 0.9953

Local classifier original vs privatized:

- original macro-F1: 0.7764
- privatized macro-F1: 0.7756
- macro-F1 delta: -0.0008

Generated outputs are under ignored `data/outputs/`.

## Next Work

Follow `docs/roadmap.md`.

Recommended next sequence:

1. A17: author-attribution privacy evaluator using an `author` column.
2. A18: style-scrubbing transformer for authorship cues.
3. A24/A25: optional Hugging Face model registry and utility evaluator.
4. A19: candidate generation/reranking by privacy and HSD utility.
5. A27: DPMLM protected-cue spike on bounded samples only.
6. A28: exact-format submission validator/creator.
7. A08/A22: final pitch/demo and human-rights judging narrative.
8. A14/A21/A29: optional Presidio and specialized local LLM experiments.

Do not start by training a new attention model. Use pretrained models to
measure HSD utility and generate/rerank candidates, then keep anything that
improves the measured privacy/HSD tradeoff.

## Constraints

- Preserve row count, row order, IDs, labels, and metadata.
- Add `privatized_text` by default.
- Do not expose raw official examples in docs, tests, screenshots, or commits.
- Use `balanced` as the first submission mode unless official scores prove
  otherwise.
- Treat external OSS/LLM/DP tools as optional support, not the core default.
