# Token-Policy Training Runbook

Status: active
Owner area: token-policy training and runtime
Last verified: 2026-06-14
Primary code: `contextsafe_hsd/token_policy.py`, `contextsafe_hsd/token_actions.py`,
`contextsafe_hsd/models/token_policy_runtime.py`

The token-policy model learns weak token-action labels. It is optional advisory
evidence for auto routing, fusion, and reranking; it is not a direct text
replacement path and is not required for the deterministic exact-format
baseline.

## Install

```bash
python -m pip install '.[token-policy]'
```

Verify CUDA with the local PyTorch build before using `--device cuda`.

## Train RoBERTa

```bash
contextsafe-hsd train-token-policy \
  --input data/public_dev/recommended_merged.csv \
  --text-col text \
  --id-col id \
  --sample-size 30000 \
  --sample-strategy action_source_balanced \
  --model-name FacebookAI/roberta-base \
  --output-dir data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda \
  --report data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda.train.json \
  --max-length 192 \
  --epochs 1 \
  --batch-size 32 \
  --device cuda
```

## Train Grouped K-Folds

Repeat with `--fold-index 0..4`:

```bash
contextsafe-hsd train-token-policy \
  --input data/public_dev/recommended_merged.csv \
  --text-col text \
  --id-col id \
  --sample-size 30000 \
  --sample-strategy action_source_balanced \
  --model-name FacebookAI/roberta-base \
  --fold-count 5 \
  --fold-index 0 \
  --output-dir data/outputs/token_policy_roberta_base.action_balanced_kfold5_fold0.cuda \
  --report data/outputs/token_policy_roberta_base.action_balanced_kfold5_fold0.cuda.train.json \
  --max-length 192 \
  --epochs 1 \
  --batch-size 32 \
  --device cuda
```

## Evaluate Ensemble

```bash
contextsafe-hsd evaluate-token-policy-ensemble \
  --input data/external_unseen/tweet_eval_hate_offensive_test.csv \
  --text-col text \
  --id-col id \
  --model-dir data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda \
  --model-dir data/outputs/token_policy_hatebert.action_balanced_train30000.cuda \
  --output data/outputs/token_policy_ensemble.roberta_hatebert.tweet_eval_external.evaluate.json
```

## Candidate Helper Path

The token-policy ensemble is not part of the default public auto/protect path.
Enable it only for explicit research or audit ablations where its behavior is
being measured.

Use standalone predictions only as candidate support:

```bash
contextsafe-hsd predict-token-policy-ensemble \
  --input INPUT.csv \
  --text-col text \
  --id-col id \
  --model-dir data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda \
  --model-dir data/outputs/token_policy_hatebert.action_balanced_train30000.cuda \
  --output data/outputs/INPUT.token_policy_ensemble.predictions.json

contextsafe-hsd apply-token-policy-candidates \
  --input INPUT.csv \
  --output data/outputs/INPUT.token_policy_candidates.csv \
  --text-col text \
  --id-col id \
  --policy-predictions data/outputs/INPUT.token_policy_ensemble.predictions.json \
  --candidate-col token_policy_candidate \
  --audit data/outputs/INPUT.token_policy_candidates.audit.json
```

Candidate outputs still require reranking, cue checks, and exact-format
validation before they can affect a submission. Do not upload
`token_policy_candidate` helper columns directly.
