# Official Submission Checklist

Use this before any leaderboard upload. Keep raw challenge examples out of
commits, markdown, screenshots, and chat.

## Required Checks

- `git status --short` has no unintended source changes.
- `python -m pytest -q` passes.
- `profile-dataset` has been run on the official CSV.
- Text, ID, label, source, split, and author/user columns have been inspected.
- Missing labels, unexpected labels, blank text, duplicate text, and odd columns
  are recorded in an ignored run note.
- The submission CSV was created with `create-submission --replace-text`.
- `validate-submission` passes with no helper columns.
- Row count, column order, ID order, labels, and metadata match the source.
- Manifest exists and records command, git commit, input/output hashes, mode,
  metric depth, provider/model status, validation, and aggregate metrics.
- Exact submission metrics use `--metric-depth fast` unless a separate local
  audit explicitly requests `sampled` or `deep`.
- Generated reports, datasets, model weights, and run notes are under ignored
  `data/outputs/` or `data/official/`.
- No raw official examples or downloaded datasets are staged for commit.

## Evidence To Review

- Local privacy/utility aggregate metrics.
- `source-regression-report` when source/label/split metadata exists.
- HSD cue retention: target, utility, action, negation, and modality.
- Rationale/span preservation when the dataset provides rationale metadata.
- Author-risk report when an author/user column has repeated values.
- Token-policy ensemble report if using it as advisory evidence or candidates.
- Candidate-reranking audit if using reranked output.
- Presidio comparison or filtered Presidio audit if using Presidio augmentation.

LLM and DPMLM reports are optional research evidence. They are not required for
a baseline upload and raw outputs must not be submitted directly.

## Recommended Commands

```bash
python -m privhsd.cli profile-dataset \
  --input INPUT.csv \
  --output data/outputs/INPUT.profile.json

python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output data/outputs/SUBMISSION.auto.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --metric-depth fast \
  --manifest data/outputs/SUBMISSION.auto.manifest.json

python -m privhsd.cli validate-submission \
  --source INPUT.csv \
  --submission data/outputs/SUBMISSION.auto.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/SUBMISSION.auto.validation.json

python -m privhsd.cli source-regression-report \
  --original INPUT.csv \
  --protected data/outputs/SUBMISSION.auto.csv \
  --original-text-col text \
  --protected-text-col text \
  --id-col id \
  --group-col source \
  --group-col label \
  --output data/outputs/SUBMISSION.auto.source_regression.json
```

## Decision Rule

Submit `auto` first unless provider/model status or official feedback proves a
better deterministic fallback. Consider `rerank-candidates --mode auto` if
privacy is weak and cue retention still passes. Use token-policy outputs as
advisory candidates only when exact-format validation and reranking audit both
pass. Never upload raw optional provider/model output directly.
