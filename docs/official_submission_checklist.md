# Official Submission Checklist

Use this before any leaderboard upload. Keep raw challenge examples out of this
file, commit messages, screenshots, and issue comments.

## Required Checks

- `profile-dataset` has been run on the official CSV and the selected
  text/ID/label columns are recorded.
- `git status --short` has no unintended source changes.
- `python -m pytest -q` passes.
- The submission CSV was created with `create-submission --replace-text`.
- `validate-submission` passes with no helper columns.
- Optional Presidio output, if used, came through `rerank-candidates
  --replace-text --presidio-augment`, not raw Presidio or direct entity
  replacement.
- Row count matches the source dataset.
- Column set and column order match the source dataset.
- ID order matches the source dataset when an ID column is available.
- Label and metadata columns are unchanged.
- Text columns are privatized in place.
- Manifest exists and records command, git commit, input/output hashes, mode,
  validation, and aggregate metrics.
- Generated reports are under ignored `data/outputs/`.
- No downloaded datasets, model weights, Hugging Face caches, or raw official
  examples are staged for commit.

## Evidence To Review

- Local privacy/utility metrics.
- Local utility benchmark if labels are available.
- Author-risk report when an author column exists.
- HSD cue retention report.
- HF utility report or structured skip.
- DPMLM spike report or structured blocker.
- Presidio comparison report or structured skip.
- Candidate-reranking audit when using reranked outputs.

## Recommended Commands

```bash
python -m privhsd.cli profile-dataset \
  --input INPUT.csv \
  --output data/outputs/INPUT.profile.json

python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output data/outputs/SUBMISSION.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode balanced \
  --manifest data/outputs/SUBMISSION.manifest.json

python -m privhsd.cli validate-submission \
  --source INPUT.csv \
  --submission data/outputs/SUBMISSION.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/SUBMISSION.validation.json
```

## Decision Rule

Submit `balanced` first unless official feedback shows a better tradeoff.
Consider `rerank-candidates` when author-style risk needs more pressure and the
exact-format validation plus utility/cue reports still pass. Treat
`rerank-candidates --presidio-augment` as the current strongest alternate, but
only after audit review confirms no target/action cue loss and
`validate-submission` passes on the exact-format file.
