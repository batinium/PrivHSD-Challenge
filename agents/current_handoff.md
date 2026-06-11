# Current Handoff

Date: 2026-06-11

## Repo State

Repository:

```text
/home/bati/projects/PrivHSD-Challenge
```

Branch:

```text
main
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
privhsd evaluate-author-risk
privhsd hf-model-registry
privhsd evaluate-hf-utility
privhsd rerank-candidates
privhsd dpmlm-spike
privhsd create-submission
privhsd validate-submission
privhsd prepare-dynahate
```

Core `privhsd anonymize` remains dependency-light and does not require
scikit-learn, external LLM APIs, Presidio, or Hugging Face models.
`--style-scrub` is available as an optional deterministic author-style
normalization pass after privacy masking.
Hugging Face utility probes are optional through `privhsd[hf-utility]`.

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
- A17: optional local author-risk evaluator with structured no-author skip JSON.
- A18: deterministic style scrubber for casing, spacing, repeated letters,
  punctuation bursts, emoji/symbol bursts, signatures, self-tags, and idiolect
  markers while preserving target/action cues.
- A24/A25: optional Hugging Face model registry and utility evaluator with
  small-sample defaults, score-drift/agreement metrics, large-drop row IDs, and
  structured skips for missing dependencies or failed model loading.
- A19: row-local candidate reranker for balanced, style-scrubbed, privacy,
  target-generalized, and optional rewrite-column candidates, with audit-only
  per-candidate scores and optional author-risk confidence when available.
- A27: bounded DPMLM spike harness with epsilon sweep, protected-cue manifest,
  runtime/blocker reporting, and no core dependency. Current local environment
  has no supported DPMLM backend installed.
- A28: exact-format submission creator/validator with in-place text-column
  privatization via `--replace-text`, helper-column rejection, row/order/ID
  validation, metadata preservation checks, file hashes, git commit, command,
  mode, and metrics in the manifest.

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
49 passed, 1 skipped
```

Latest optional classifier suite:

```text
.venv/bin/python -m pytest -q
49 passed, 1 skipped
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

1. A08/A22: final pitch/demo and human-rights judging narrative.
2. A14/A21/A29: optional Presidio and specialized local LLM experiments.

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
