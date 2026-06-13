# Pipeline Design

Date: 2026-06-13

ContextSafe-HSD is built as a layered preprocessing system. The submission path
must be deterministic, reproducible, and auditable; optional model paths provide
evidence, uncertainty, and candidates that can be accepted only after checks.

## Layers

| Layer | Purpose | Main modules | Submission role |
| --- | --- | --- | --- |
| CSV and manifests | Preserve rows, IDs, labels, metadata, hashes, and command provenance. | `csv_pipeline.py`, `submission.py` | Required |
| Auto orchestration | Discover local providers/models once, route risky rows, batch model inference, and select checked candidates. | `privhsd/auto/` | Default exact path |
| Deterministic privacy | Mask direct and quasi identifiers with typed placeholders. | `detectors.py`, `pipeline.py`, `metrics.py` | Required |
| HSD cue protection | Preserve target, hostility, action, negation, modality, counterspeech, and rationale cues. | `cue_checks.py`, `context.py`, `rationale_checks.py` | Required audit |
| Style pressure | Reduce author-style signals without erasing HSD meaning. | `style.py` | Optional candidate |
| Candidate reranking | Choose the best row-local tradeoff among deterministic and optional candidates. | `rerank.py` | Optional alternate |
| Slice regression | Check privacy and utility by source/label/split/platform/type. | `source_report.py` | Required when columns exist |
| Author risk | Measure stylometric author predictability when repeated author IDs exist. | `author_risk.py` | Required when columns exist |
| Transformer token policy | Fine-tune weakly supervised token-action models and ensembles. | `token_policy.py` | Advisory/reranking support |
| External model probes | Bound score drift, Presidio behavior, DPMLM, or local LLM candidates. | `hf_utility.py`, `presidio_compare.py`, `dpmlm_candidates.py`, `local_llm.py` | Evidence only unless reranked |

## Core Submission Path

Create the first exact-format candidate with `auto` mode:

```bash
python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output data/outputs/SUBMISSION.auto.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --metric-depth fast \
  --manifest data/outputs/SUBMISSION.auto.manifest.json
```

Auto mode always runs deterministic balanced masking first. It then computes
cheap row risk features and routes only rows with residual ID risk, quasi-ID
context, provider-worthy ambiguity, style risk, or cue ambiguity to optional
providers/models. Presidio, scrubadub, GLiNER, token-policy, semantic, and HSD
advisory components are discovered from local dependencies/artifacts. Missing
dependencies or artifacts are recorded in the manifest and fall back to the
deterministic candidate. Downloads are disabled unless `--allow-model-download`
is explicitly passed.

Validate exact shape:

```bash
python -m privhsd.cli validate-submission \
  --source INPUT.csv \
  --submission data/outputs/SUBMISSION.auto.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/SUBMISSION.auto.validation.json
```

Run slice regression when metadata columns exist:

```bash
python -m privhsd.cli source-regression-report \
  --original INPUT.csv \
  --protected data/outputs/SUBMISSION.auto.csv \
  --original-text-col text \
  --protected-text-col text \
  --id-col id \
  --group-col source \
  --group-col label \
  --group-col split \
  --output data/outputs/SUBMISSION.auto.source_regression.json
```

## Metric Depth

Exact submissions default to `--metric-depth fast`. Fast metrics keep the
aggregate schema but avoid target-variant, spaced-token, external profanity,
and semantic scans on every row. `--metric-depth sampled` runs deep metrics on a
bounded sample; `--metric-depth deep` is for explicit local audits under
ignored `data/` paths.

## Optional Alternates

Use alternates only after the baseline passes validation.

- `balanced`: deterministic compatibility fallback when auto is not desired.
- `balanced --style-scrub`: more author-style pressure with the same core
  masking policy.
- `anonymize --mode auto`: same row routing as exact submission, writing either
  a helper column or replacing the text column.
- `rerank-candidates --mode auto`: automatic routing and checked candidate
  selection without manual provider flags.
- `rerank-candidates`: row-local choice among `balanced`, `style_scrubbed`,
  `privacy`, `target_generalized`, and supplied candidate columns.
- `rerank-candidates --presidio-augment`: adds filtered Presidio spans for
  likely names, locations, and durable dates while rejecting `NRP`, target, and
  action overlaps.
- `generate-llm-candidates` and `generate-dpmlm-candidates`: candidate-only
  paths. Their raw outputs must feed reranking before any submission.

## Token-Policy Model

The token-policy model is not trained on private identity labels. It is trained
on weak token-action labels produced by the local detectors and cue protectors:

```text
KEEP
MASK_IDENTIFIER
GENERALIZE_CONTEXT
PROTECT_TARGET
PROTECT_HSD
NORMALIZE_STYLE
REVIEW
```

This means `PROTECT_TARGET` is supported by training data: target terms and
target metadata become protected action labels, not text to memorize. External
target-rich datasets can improve this class when they are normalized into the
shared schema and evaluated as unseen data.

Install dependencies:

```bash
python -m pip install '.[token-policy]'
```

Train a CUDA RoBERTa policy:

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

Train grouped K-folds by repeating `--fold-index 0..4`:

```bash
python -m privhsd.cli train-token-policy \
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

Evaluate an equal RoBERTa plus HateBERT ensemble on external TweetEval data:

```bash
python -m privhsd.cli evaluate-token-policy-ensemble \
  --input data/external_unseen/tweet_eval_hate_offensive_test.csv \
  --text-col text \
  --id-col id \
  --model-dir data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda \
  --model-dir data/outputs/token_policy_hatebert.action_balanced_train30000.cuda \
  --output data/outputs/token_policy_ensemble.roberta_hatebert.tweet_eval_external.evaluate.json
```

In auto mode, local token-policy artifacts are loaded once only when routing
needs advisory model evidence, and inference is batched. `MASK_IDENTIFIER` and
`GENERALIZE_CONTEXT` become span evidence for fusion; `PROTECT_TARGET`,
`PROTECT_HSD`, `NORMALIZE_STYLE`, and `REVIEW` remain audit/routing evidence.
Token-policy output never directly overwrites final text.

Use standalone predictions as a candidate helper only when a reranking/audit
path accepts them:

```bash
python -m privhsd.cli predict-token-policy-ensemble \
  --input INPUT.csv \
  --text-col text \
  --id-col id \
  --model-dir data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda \
  --model-dir data/outputs/token_policy_hatebert.action_balanced_train30000.cuda \
  --output data/outputs/INPUT.token_policy_ensemble.predictions.json

python -m privhsd.cli apply-token-policy-candidates \
  --input INPUT.csv \
  --output data/outputs/INPUT.token_policy_candidates.csv \
  --text-col text \
  --id-col id \
  --policy-predictions data/outputs/INPUT.token_policy_ensemble.predictions.json \
  --candidate-col token_policy_candidate \
  --audit data/outputs/INPUT.token_policy_candidates.audit.json
```

## Reporting Policy

Generated reports should not print raw sensitive text. Durable docs should
record aggregate metrics, row IDs, commands, commit hashes, and limitations.
Raw CSVs, generated candidates, model weights, and JSON reports stay under
ignored `data/`.
