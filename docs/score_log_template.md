# Official Score Log Template

Use this template for every official PrivHSD leaderboard submission. Keep raw
challenge examples out of this file. Record paths, commands, aggregate metrics,
and links to generated artifacts instead.

## Submission Summary

| Field | Value |
| --- | --- |
| Submission name |  |
| Date/time |  |
| Operator |  |
| Git commit |  |
| Branch |  |
| Challenge split |  |
| Input CSV path |  |
| Submitted CSV path |  |
| Output text column | `privatized_text` |
| ID column |  |
| Label column, if available |  |
| Mode | `balanced` |
| Target policy | preserve targets / generalize targets / privacy mode |
| Notes |  |

## Reproducible Commands

```bash
# Environment and commit
git rev-parse HEAD
python -m pytest -q

# Privatize
python -m privhsd.cli anonymize \
  --input INPUT.csv \
  --output data/outputs/SUBMISSION.privatized.csv \
  --text-col text \
  --id-col id \
  --audit data/outputs/SUBMISSION.audit.json \
  --mode balanced

# Local metrics
python -m privhsd.cli evaluate \
  --input data/outputs/SUBMISSION.privatized.csv \
  --text-col text \
  --privatized-col privatized_text \
  --output data/outputs/SUBMISSION.metrics.json

# Optional ablation
python -m privhsd.cli ablate \
  --input INPUT.csv \
  --text-col text \
  --id-col id \
  --label-col label \
  --output data/outputs/SUBMISSION.ablation.json \
  --output-dir data/outputs/SUBMISSION_ablation

# Optional local classifier
python -m privhsd.cli train-classifier \
  --input TRAIN.csv \
  --text-col text \
  --label-col label \
  --id-col id \
  --model data/outputs/SUBMISSION.classifier.pkl \
  --output data/outputs/SUBMISSION.classifier.train.json

python -m privhsd.cli predict-classifier \
  --input data/outputs/SUBMISSION.privatized.csv \
  --model data/outputs/SUBMISSION.classifier.pkl \
  --text-col privatized_text \
  --id-col id \
  --output data/outputs/SUBMISSION.classifier.predictions.csv
```

## Local Metric Summary

| Metric | Value | Source artifact |
| --- | --- | --- |
| Row count |  |  |
| Changed row count |  |  |
| Privacy gain mean |  |  |
| Residual identifier count |  |  |
| Residual direct identifier count |  |  |
| Residual quasi-identifier count |  |  |
| Placeholder count total |  |  |
| Mask density mean |  |  |
| Target cue retention mean |  |  |
| Character utility retention mean |  |  |
| Proxy tradeoff mean |  |  |
| Rows with privacy warnings |  |  |
| Rows with over-masking warnings |  |  |

## Optional Local Classifier Summary

| Metric | Original text | Privatized text | Source artifact |
| --- | --- | --- | --- |
| Accuracy |  |  |  |
| Macro-F1 |  |  |  |
| Prediction agreement |  |  |  |
| Changed prediction count |  |  |  |
| Prediction counts |  |  |  |
| Label counts |  |  |  |

## Official Leaderboard Result

| Field | Value |
| --- | --- |
| Submission timestamp |  |
| Leaderboard run ID |  |
| Official privacy score |  |
| Official utility score |  |
| Official combined score |  |
| Rank at submission time |  |
| Evaluator warnings/errors |  |
| Link or screenshot path |  |

## Audit Notes

- Confirm row count and row order match the input.
- Confirm ID, label, and metadata columns are preserved.
- Confirm no official/raw examples are copied into docs, screenshots, issues, or
  commit messages.
- List any residual warning categories and whether they were accepted for this
  submission.
- List any known over-masking concerns and expected utility impact.
- Record whether target groups were preserved or generalized and why.

## Follow-Up

| Item | Owner | Status |
| --- | --- | --- |
|  |  |  |
