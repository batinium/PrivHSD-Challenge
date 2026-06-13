# Quickstart

## Verify

```bash
python -m pytest -q
```

The committed tests use synthetic fixtures and regression checks. Raw challenge
or downloaded data should stay under ignored `data/`.

## Install

```bash
python -m pip install .
contextsafe-hsd --help
```

Useful optional extras:

```bash
python -m pip install '.[benchmark]'
python -m pip install '.[presidio]'
python -m pip install '.[token-policy]'
```

Build a wheel smoke test when packaging matters:

```bash
python -m pip wheel . -w dist --no-deps
python -m venv /tmp/contextsafe-hsd-smoke
/tmp/contextsafe-hsd-smoke/bin/python -m pip install dist/contextsafe_hsd-*.whl
/tmp/contextsafe-hsd-smoke/bin/contextsafe-hsd --help
```

## Prepare Public Data

```bash
python -m privhsd.cli prepare-recommended-datasets \
  --output-dir data/public_dev \
  --raw-dir data/public_dev/raw \
  --merged-output data/public_dev/recommended_merged.csv
```

The merged schema keeps `id,text,label,source,split,target,type` first, then
adds `platform,source_id,severity,target_categories,rationale_spans,meta`.
Downloaded raw files stay under ignored `data/public_dev/raw/`.

## Create And Validate An Exact Auto Submission

```bash
python -m privhsd.cli create-submission \
  --input data/public_dev/recommended_merged.csv \
  --output data/outputs/recommended_merged.auto.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --metric-depth fast \
  --manifest data/outputs/recommended_merged.auto.manifest.json

python -m privhsd.cli validate-submission \
  --source data/public_dev/recommended_merged.csv \
  --submission data/outputs/recommended_merged.auto.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/recommended_merged.auto.validation.json
```

Auto mode preserves exact CSV shape when `--replace-text` is used. Optional
Presidio, scrubadub, GLiNER, token-policy, semantic, and advisory components
are discovered locally, loaded at most once when used, and safely skipped when
dependencies or model artifacts are absent. No model downloads happen unless
`--allow-model-download` is passed.

For a package-installed command, replace `python -m privhsd.cli` with
`contextsafe-hsd`.

## Run Local Evidence

Source-aware regression:

```bash
python -m privhsd.cli source-regression-report \
  --original data/public_dev/recommended_merged.csv \
  --protected data/outputs/recommended_merged.auto.csv \
  --original-text-col text \
  --protected-text-col text \
  --id-col id \
  --group-col source \
  --group-col label \
  --group-col split \
  --group-col platform \
  --group-col type \
  --output data/outputs/recommended_merged.auto.source_regression.json
```

Semantic triage for rows needing repair or selective semantic review:

```bash
python -m privhsd.cli semantic-triage-report \
  --input data/public_dev/recommended_merged.csv \
  --protected data/outputs/recommended_merged.auto.csv \
  --text-col text \
  --privatized-col text \
  --id-col id \
  --label-col label \
  --source-col source \
  --sample-size 20000 \
  --sample-strategy source_label_round_robin \
  --privacy-scan changed \
  --output data/outputs/recommended_merged.auto.semantic_triage.json \
  --queue-output data/outputs/recommended_merged.auto.semantic_triage.queue.csv
```

Use `--metric-depth fast` for exact submissions. `sampled` runs deep metrics on
a bounded sample, and `deep` enables expensive target-variant/profanity and
semantic-style audit checks where implemented.

Author-risk check when an author/user column has repeated values:

```bash
python -m privhsd.cli evaluate-author-risk \
  --input INPUT_WITH_PRIVATIZED_TEXT.csv \
  --text-col text \
  --privatized-col privatized_text \
  --author-col author \
  --id-col id \
  --label-col label \
  --output data/outputs/author_risk.json
```

If the author column is absent or every ID is unique, record the structured
skip. Do not treat unique row IDs as author labels.

## Train Token-Policy Models

Install `.[token-policy]` and verify CUDA with the local PyTorch build. Then
train the action-balanced RoBERTa policy:

```bash
python -m privhsd.cli train-token-policy \
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

Train HateBERT with the same recipe and evaluate the ensemble on external data:

```bash
python -m privhsd.cli evaluate-token-policy-ensemble \
  --input data/external_unseen/tweet_eval_hate_offensive_test.csv \
  --text-col text \
  --id-col id \
  --model-dir data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda \
  --model-dir data/outputs/token_policy_hatebert.action_balanced_train30000.cuda \
  --output data/outputs/token_policy_ensemble.roberta_hatebert.tweet_eval_external.evaluate.json
```

## Python API

```python
from pathlib import Path

import contextsafe_hsd as hsd

hsd.create_submission(
    Path("INPUT.csv"),
    Path("SUBMISSION.csv"),
    text_cols=["text"],
    id_col="id",
    manifest_path=Path("SUBMISSION.manifest.json"),
    replace_text=True,
    mode="auto",
)
```

## Run Notes

For official submissions, keep a dated note under ignored `data/outputs/` with
the commit hash, commands, artifact paths, aggregate local metrics, official
scores, and limitations. Do not commit raw examples or generated run logs.
