# Current Handoff

Archived note: this file is historical. Use [../../README.md](../../README.md)
and [../../project/roadmap.md](../../project/roadmap.md) for current workflow.

Date: 2026-06-12

## Repo State

Repository:

```text
/home/bati/projects/PrivHSD-Challenge
```

Branch:

```text
main
```

The webinar slide screenshots are outside the repo at:

```text
/mnt/c/Users/noutr/Downloads/Ss
```

Do not commit downloaded datasets, official challenge data, or generated
`data/outputs/` artifacts.

`docs/archive/agent_notes/prompt_lm_studio.md` contains the historical
self-contained continuation prompt for the LM Studio testing phase.

## Read First

1. `docs/challenge/challenge_requirements.md`
2. `docs/project/roadmap.md`
3. `docs/project/pipeline_design.md`
4. `docs/project/methodology_justification.md`
5. `docs/archive/agent_notes/task_board.md`
6. `docs/archive/agent_notes/coding_rules.md`

Use `docs/project/experiment_verdict.md`, `docs/project/pipeline_design.md`, and
`docs/project/roadmap.md` for current experiment results and implementation direction.
Keep this handoff short.

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
privhsd train-token-action-tagger
privhsd evaluate-author-risk
privhsd hf-model-registry
privhsd evaluate-hf-utility
privhsd rerank-candidates
privhsd dpmlm-spike
privhsd generate-dpmlm-candidates
privhsd create-submission
privhsd validate-submission
privhsd compare-presidio
privhsd generate-llm-candidates
privhsd benchmark-lm-context
privhsd check-hsd-cues
privhsd semantic-triage-report
privhsd source-regression-report
privhsd check-metadata-leakage
privhsd label-feature-report
privhsd train-token-policy
privhsd evaluate-token-policy
privhsd evaluate-token-policy-ensemble
privhsd predict-token-policy
privhsd predict-token-policy-ensemble
privhsd apply-token-policy-candidates
privhsd prepare-dynahate
privhsd prepare-recommended-datasets
privhsd prepare-tweet-eval-unseen
```

Core `privhsd anonymize` remains dependency-light and does not require
scikit-learn, external LLM APIs, Presidio, or Hugging Face models.
`--style-scrub` is available as an optional deterministic author-style
normalization pass after privacy masking.
Hugging Face utility probes are optional through `privhsd[hf-utility]`.
The local `.venv` now has optional HF, Presidio/spaCy, DPMLM, and
scikit-learn experiment dependencies installed for bounded runs; these remain
outside core runtime requirements.

## Latest Token-Policy Fine-Tuning State

Role-aware token policy was implemented on 2026-06-12 as an optional extension,
not a replacement for the `balanced` submission path. New module:
`privhsd/token_policy.py`.

Merged CSV validation before training:

- `data/public_dev/recommended_merged.csv`: 159,668 rows
- required columns present: `id`, `text`, `label`, `source`
- no blank text/labels/source/IDs
- no duplicate merged IDs
- no invalid source/label pairs across the known nine public sources
- `meta` parsed as JSON for all rows
- optional missing fields are source-specific: `severity`, `target_categories`,
  `rationale_spans`, `target`, `split`, and `type`

Artifacts from smoke checks:

```text
data/outputs/recommended_merged.profile.refresh.json
data/outputs/token_action_tagger.smoke500.json
data/outputs/token_action_tagger.smoke500.pkl
data/outputs/recommended_merged.label_feature_report.smoke500.json
data/outputs/token_policy_roberta_base.smoke120/
data/outputs/token_policy_roberta_base.smoke120.train.json
data/outputs/token_policy_roberta_base.smoke120.predictions.sample40.json
data/outputs/recommended_merged.token_policy_candidates.smoke40.csv
data/outputs/recommended_merged.token_policy_candidates.smoke40.audit.json
```

Smoke results:

- focused token-policy/action tests: `11 passed`
- full repo suite: `131 passed, 1 skipped`
- 500-row label-feature report used source/label round-robin sampling and
  emitted all expected action classes, with feature values hashed
- RoBERTa smoke run used `FacebookAI/roberta-base` revision
  `e2da8e2f811d1448a5b465c236feacd80ffbac7b`, CPU, 120 sampled rows, two
  capped train steps, and saved/reloaded successfully
- sample prediction/candidate handoff preserved all 159,668 rows and changed 6
  candidate cells in the smoke helper output

CUDA correction:

- Initial 30k run used CPU because the venv had `torch 2.12.0+cpu`;
  `torch.version.cuda` was `None` and `torch.cuda.is_available()` was `False`.
- Host GPU was visible through `nvidia-smi`: NVIDIA GeForce RTX 5090 Laptop GPU,
  driver CUDA 13.2.
- Replaced CPU torch with `torch 2.12.0+cu130` from the official PyTorch CUDA
  13.0 index.
- Verified CUDA tensor matmul and a two-step CUDA smoke fine-tune.

Completed bounded CUDA run:

```text
Command: privhsd train-token-policy --sample-size 30000 --sample-strategy source_label_round_robin --max-length 192 --epochs 1 --batch-size 32 --device cuda
Output dir: data/outputs/token_policy_roberta_base.train30000.cuda
Report: data/outputs/token_policy_roberta_base.train30000.cuda.train.json
Log: data/outputs/logs/token_policy_roberta_base.train30000.cuda.log
```

Result:

```text
runtime_seconds: 160.8453
device: cuda
train_steps: 797
train_loss: 0.1188
dev_accuracy: 0.9831
dev_macro_f1: 0.7875
```

Per-action dev F1:

```text
KEEP: 0.9902
MASK_IDENTIFIER: 0.9870
GENERALIZE_CONTEXT: 0.7333
PROTECT_TARGET: 0.9704
PROTECT_HSD: 0.8556
NORMALIZE_STYLE: 0.9759
REVIEW: 0.0 on 14 dev tokens
```

Post-CUDA-install full test suite: `131 passed, 1 skipped`.

## Improved Token-Policy Replication Recipe

To reduce overfitting and improve rare-action learning, use action/source-aware
sampling instead of plain source/label round-robin:

```bash
.venv/bin/python -m privhsd.cli train-token-policy \
  --input data/public_dev/recommended_merged.csv \
  --text-col text \
  --id-col id \
  --source-col source \
  --label-col label \
  --target-col target \
  --target-categories-col target_categories \
  --rationale-col rationale_spans \
  --model-name FacebookAI/roberta-base \
  --sample-size 30000 \
  --sample-strategy action_source_balanced \
  --split-strategy grouped_text \
  --class-weighting capped_inverse_sqrt \
  --max-class-weight 6 \
  --max-length 192 \
  --epochs 1 \
  --batch-size 32 \
  --device cuda \
  --output-dir data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda \
  --report data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda.train.json \
  --log-steps 50
```

Why these settings:

- `action_source_balanced`: profiles the merged CSV and selects rows that cover
  rare token actions such as `REVIEW`, `GENERALIZE_CONTEXT`, `MASK_IDENTIFIER`,
  `PROTECT_TARGET`, `PROTECT_HSD`, and `NORMALIZE_STYLE`, while preserving
  source/label coverage.
- `grouped_text`: keeps normalized duplicate text groups on only one side of
  train/dev to reduce leakage and inflated validation metrics.
- `capped_inverse_sqrt`: upweights rare action labels without making rare-label
  gradients unstable.
- `max-class-weight 6`: caps rare-action weights.

Smoke artifact proving sampler behavior:

```text
data/outputs/token_policy_roberta_base.action_balanced_smoke800.train.json
```

The smoke profiled all 159,668 rows, selected 800 rows, included 115 rows with
`REVIEW`, and produced zero grouped-text duplicate overlap between train/dev.

Completed improved CUDA run:

```text
Report: data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda.train.json
Model dir: data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda
Log: data/outputs/logs/token_policy_roberta_base.action_balanced_train30000.cuda.log
runtime_seconds: 160.511
device: cuda
train_steps: 797
train_loss: 0.1829
dev_accuracy: 0.9739
dev_macro_f1: 0.9061
```

Per-action dev F1:

```text
KEEP: 0.9847
MASK_IDENTIFIER: 0.9818
GENERALIZE_CONTEXT: 0.8173
PROTECT_TARGET: 0.8665
PROTECT_HSD: 0.8425
NORMALIZE_STYLE: 0.9680
REVIEW: 0.8818 on 103 dev tokens
```

Selection report highlights:

```text
profiled_rows: 159,668
selected_rows: 30,000
selected REVIEW rows: 623
selected MASK_IDENTIFIER rows: 5,281
selected GENERALIZE_CONTEXT rows: 2,960
selected PROTECT_TARGET rows: 10,043
selected PROTECT_HSD rows: 14,432
selected NORMALIZE_STYLE rows: 6,117
grouped_text duplicate_group_overlap_count: 0
```

Internal unseen holdout from rows not selected by the action-balanced 30k run:

```text
Heldout CSV: data/outputs/recommended_merged.unseen_action_balanced5000.csv
Selection manifest: data/outputs/recommended_merged.unseen_action_balanced5000.selection.json
Evaluation: data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda.unseen5000.evaluate.json
heldout_rows: 5,000
overlap_with_training_indices: 0
device: cuda
accuracy: 0.9739
macro_f1: 0.7767
```

Per-action heldout F1:

```text
KEEP: 0.9851
MASK_IDENTIFIER: 0.9771
GENERALIZE_CONTEXT: 0.8161
PROTECT_TARGET: 0.8481
PROTECT_HSD: 0.8464
NORMALIZE_STYLE: 0.9638
REVIEW: 0.0, support 0
```

The lower heldout macro-F1 is mostly an artifact of no `REVIEW` support in the
remaining 5,000-row slice; the action-balanced 30k selection intentionally
consumed all available rare-review rows.

Grouped K-fold support was added to `train-token-policy` with
`--fold-count` and `--fold-index`. Use grouped K-fold for robustness evidence,
not for a final ensemble unless official scoring shows that multiple saved
policies are worth the complexity.

Replication command used for five folds:

```bash
for fold in 0 1 2 3 4; do
  .venv/bin/python -m privhsd.cli train-token-policy \
    --input data/public_dev/recommended_merged.csv \
    --text-col text --id-col id \
    --source-col source --label-col label \
    --target-col target --target-categories-col target_categories \
    --rationale-col rationale_spans \
    --model-name FacebookAI/roberta-base \
    --sample-size 30000 \
    --sample-strategy action_source_balanced \
    --split-strategy grouped_text \
    --fold-count 5 \
    --fold-index "$fold" \
    --class-weighting capped_inverse_sqrt \
    --max-class-weight 6 \
    --max-length 192 \
    --epochs 1 \
    --batch-size 32 \
    --device cuda \
    --output-dir "data/outputs/token_policy_roberta_base.action_balanced_kfold5_fold${fold}.cuda" \
    --report "data/outputs/token_policy_roberta_base.action_balanced_kfold5_fold${fold}.cuda.train.json" \
    --log-steps 100
done
```

K-fold artifacts:

```text
data/outputs/token_policy_roberta_base.action_balanced_kfold5_fold0.cuda.train.json
data/outputs/token_policy_roberta_base.action_balanced_kfold5_fold1.cuda.train.json
data/outputs/token_policy_roberta_base.action_balanced_kfold5_fold2.cuda.train.json
data/outputs/token_policy_roberta_base.action_balanced_kfold5_fold3.cuda.train.json
data/outputs/token_policy_roberta_base.action_balanced_kfold5_fold4.cuda.train.json
data/outputs/token_policy_roberta_base.action_balanced_kfold5.summary.json
```

K-fold aggregate:

```text
dev_accuracy mean/std/min/max: 0.9733 / 0.0049 / 0.9656 / 0.9804
dev_macro_f1 mean/std/min/max: 0.8977 / 0.0152 / 0.8809 / 0.9194
train_loss mean/std: 0.1904 / 0.0008
dev_loss mean/std: 0.0764 / 0.0132
runtime_seconds mean/std: 155.0087 / 0.2195 per fold
duplicate_group_overlap_total: 0
```

K-fold per-action F1 mean/std:

```text
KEEP: 0.9844 / 0.0029
MASK_IDENTIFIER: 0.9768 / 0.0139
GENERALIZE_CONTEXT: 0.8224 / 0.0526
PROTECT_TARGET: 0.9087 / 0.0170
PROTECT_HSD: 0.8226 / 0.0291
NORMALIZE_STYLE: 0.9617 / 0.0090
REVIEW: 0.8071 / 0.0682
```

External unseen dataset support was added through `prepare-tweet-eval-unseen`,
which fetches fixed Hugging Face Dataset Viewer splits from
`cardiffnlp/tweet_eval` and normalizes them to the common CSV schema. Current
artifact:

```text
CSV: data/external_unseen/tweet_eval_hate_offensive_test.csv
Manifest: data/external_unseen/tweet_eval_hate_offensive_test.manifest.json
Rows: 3,830
Sources: tweet_eval_hate 2,970; tweet_eval_offensive 860
Labels: tweet_eval_hate hate 1,252 / not_hate 1,718; tweet_eval_offensive offensive 240 / not_hate 620
```

Important label note: initial normalization mapped TweetEval `non-hate` to
`non_hate`; this was corrected to `not_hate`, covered by a regression test, and
the current manifest records the local repair because HF returned a 429 during
the immediate refetch.

External evaluation command:

```bash
.venv/bin/python -m privhsd.cli evaluate-token-policy \
  --input data/external_unseen/tweet_eval_hate_offensive_test.csv \
  --model-dir data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda \
  --text-col text --id-col id \
  --source-col source --label-col label \
  --target-col target --target-categories-col target_categories \
  --rationale-col rationale_spans \
  --batch-size 64 \
  --output data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda.tweet_eval_external.evaluate.json
```

External TweetEval result:

```text
accuracy: 0.9844
macro_f1: 0.8581
KEEP F1: 0.9893
MASK_IDENTIFIER F1: 0.9710
GENERALIZE_CONTEXT F1: 0.7699
PROTECT_TARGET F1: 0.6672
PROTECT_HSD F1: 0.9526
NORMALIZE_STYLE F1: 0.9897
REVIEW F1: 0.6667 on 2 support tokens
```

Interpretation: external transfer is strong for identifiers, HSD cues, and
style markers. `PROTECT_TARGET` drops because TweetEval lacks the rich target
metadata available in the merged public bundle, so target spans must come mostly
from dictionaries.

HateBERT backbone comparison added after the RoBERTa run:

```text
Model: GroNLP/hateBERT
HF revision: ab7a2d40f6c973cb57e63f23bfa2b51d981d028c
License tag: apache-2.0
Task setup: same 30k action-balanced token-policy fine-tune, CUDA, one epoch
Report: data/outputs/token_policy_hatebert.action_balanced_train30000.cuda.train.json
Model dir: data/outputs/token_policy_hatebert.action_balanced_train30000.cuda
Log: data/outputs/logs/token_policy_hatebert.action_balanced_train30000.cuda.log
External eval: data/outputs/token_policy_hatebert.action_balanced_train30000.cuda.tweet_eval_external.evaluate.json
```

Internal dev result:

```text
runtime_seconds: 159.1268
train_loss: 0.1965
accuracy: 0.9689
macro_f1: 0.8908
KEEP F1: 0.9814
MASK_IDENTIFIER F1: 0.9666
GENERALIZE_CONTEXT F1: 0.7071
PROTECT_TARGET F1: 0.9209
PROTECT_HSD F1: 0.8161
NORMALIZE_STYLE F1: 0.9709
REVIEW F1: 0.8727
```

External TweetEval result for HateBERT:

```text
accuracy: 0.9767
macro_f1: 0.8254
KEEP F1: 0.9825
MASK_IDENTIFIER F1: 0.9173
GENERALIZE_CONTEXT F1: 0.6122
PROTECT_TARGET F1: 0.7964
PROTECT_HSD F1: 0.9815
NORMALIZE_STYLE F1: 0.9877
REVIEW F1: 0.5000 on 2 support tokens
```

Comparison against the prior RoBERTa action-balanced single run:

```text
Internal macro-F1: HateBERT 0.8908 vs RoBERTa 0.9061
Internal PROTECT_TARGET F1: HateBERT 0.9209 vs RoBERTa 0.8665
External macro-F1: HateBERT 0.8254 vs RoBERTa 0.8581
External PROTECT_TARGET F1: HateBERT 0.7964 vs RoBERTa 0.6672
External PROTECT_HSD F1: HateBERT 0.9815 vs RoBERTa 0.9526
External MASK_IDENTIFIER F1: HateBERT 0.9173 vs RoBERTa 0.9710
```

Verdict: HateBERT is a strong candidate when optimizing target/HSD protection,
especially on external transfer. RoBERTa remains stronger overall and for
identifier/generalization behavior. The next experiment should either train
with target-rich external rows or combine backbones as reranker features rather
than replacing the deterministic anonymizer.

RoBERTa+HateBERT ensemble support was added after the backbone comparison:

```text
Commands:
  evaluate-token-policy-ensemble
  predict-token-policy-ensemble
Mode used: mean_prob
Members:
  data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda
  data/outputs/token_policy_hatebert.action_balanced_train30000.cuda
```

The ensemble aligns each model's subword probabilities back to original
regex-token spans, then combines probabilities. This avoids invalid logit
averaging across different tokenizers.

External TweetEval equal-weight ensemble:

```text
Report: data/outputs/token_policy_ensemble.roberta_hatebert.tweet_eval_external.evaluate.json
runtime_seconds: 78.6174
accuracy: 0.9879
macro_f1: 0.8837
KEEP F1: 0.9931
MASK_IDENTIFIER F1: 0.9638
GENERALIZE_CONTEXT F1: 0.7903
PROTECT_TARGET F1: 0.8143
PROTECT_HSD F1: 0.9808
NORMALIZE_STYLE F1: 0.9768
REVIEW F1: 0.6667 on 2 support tokens
```

External TweetEval weighted ensemble with RoBERTa 1.0 and HateBERT 1.2:

```text
Report: data/outputs/token_policy_ensemble.roberta1_hatebert1p2.tweet_eval_external.evaluate.json
runtime_seconds: 72.9744
accuracy: 0.9843
macro_f1: 0.8734
PROTECT_TARGET F1: 0.8131
```

Verdict: use equal weights for now. It preserved most of RoBERTa's identifier
strength while gaining target/HSD behavior from HateBERT.

Post-change full test suite: `141 passed, 1 skipped`.

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
  runtime/blocker reporting, backend import details, and no core dependency.
- A32/A20: protected-token DPMLM candidate generator with
  `FacebookAI/roberta-base`, frozen HSD/privacy/style-risk tokens, per-row
  seeding, validation, and reranking-only output. Current bounded reranking
  selected 0 DPMLM candidates.
- A28: exact-format submission creator/validator with in-place text-column
  privatization via `--replace-text`, helper-column rejection, row/order/ID
  validation, metadata preservation checks, file hashes, git commit, command,
  mode, and metrics in the manifest.
- A08/A22: final pitch/demo outline and human-rights judging narrative in
  `docs/challenge/final_pitch_outline.md`.
- A14: optional Presidio comparison baseline with overlap, detector-only counts,
  false-positive risk on HSD cues, runtime, and structured dependency skips.
- A15: optional neural utility evaluator path via the Hugging Face registry and
  `evaluate-hf-utility` command.
- A20: DPMLM spike completed; the adapter works but current real-model
  candidates do not beat deterministic reranking.
- A21/A29: optional local LLM candidate generator for LM Studio/llama.cpp
  OpenAI-compatible endpoints with JSON schema prompting, cue/length checks, and
  reranking-only output. Current local sample run skipped because no endpoint is
  running.
- A26: conservative HSD cue retention checker for target terms, utility cues,
  action terms, and negation/modality terms by row ID.
- Metadata leakage checker: `check-metadata-leakage` scans values such as `id`
  and `author` against text columns with exact and normalized matching.
- A23: official submission checklist in
  `docs/challenge/official_submission_checklist.md`.
- A30: bounded Hugging Face utility evaluator runs on
  `data/outputs/dynahate.reranked.csv`; default probes passed sample 25 and
  sample 100, Toxic-BERT passed sample 25, and HateXplain variants produced
  structured inference skips.
- A31: bounded Presidio/spaCy detector comparison on the first 100 and 500
  Dynahate rows; comparison passed but documented false-positive risk and
  dependency cost.
- A32: `dpmlm` 1.1.2 installed/imported after NLTK resources; raw direct
  rewriting is unsafe, protected-token candidate generation is implemented,
  and `FacebookAI/roberta-base` bounded reranking selected no DPMLM candidates.
- A33: bounded local LLM candidate generation and reranking against LM Studio
  at `http://100.120.207.64:1234`; implementation hardened for JSON-schema
  response format/fallback and wrapped JSON parsing. Accepted LLM candidates
  did not beat deterministic reranking.
- A36: optional weak token-action tagger training experiment with
  `train-token-action-tagger`, scikit-learn extra, tests, and a sample-5,000
  Dynahate report.
- A37: filtered Presidio augmentation on `anonymize`, `rerank-candidates`, and
  `create-submission` via `--presidio-augment`; full Dynahate reranking selected
  `presidio_augmented` for 6,085 rows.
- A41/A42: source-aware regression reporting, deterministic context tags, and
  source-aware rationale/span preservation checks. Full
  `recommended_merged.csv` vs `balanced` report was written to
  `data/outputs/recommended_merged.balanced.source_regression.json`.
- A43: `benchmark-lm-context` for LM Studio context-labeler stress tests with
  JSON, tagged, word-list, and binary-tag parsing. The early 2026-06-12 run
  wrote structured blocker reports because localhost refused the connection and
  the Tailscale endpoint timed out. Later the user provided the reachable
  endpoint `http://169.254.83.107:1234`; during the later WSL run that
  link-local endpoint stopped accepting TCP, and the working WSL endpoint was
  `http://172.21.96.1:1234`.
- A44: source/label-aware Qwen candidate generation. `generate-llm-candidates`
  now accepts `--source-col` and `--label-col`, samples by source/label
  round-robin, sends metadata as cue-preservation context, and rejects rewrite
  candidates that lose action or negation/modality cues. `qwen/qwen3-4b-2507`
  accepted 43/80 source/label-stratified candidates, but reranking selected
  Qwen for only 1/80 rows, so it remains optional candidate evidence rather
  than a baseline replacement.
- A45: semantic triage fallback layer. `semantic-triage-report` ranks
  already-privatized rows into `repair_before_model_review`,
  `qwen_semantic_check`, and `no_review` using deterministic context tags,
  conservative cue checks, source labels, and optional trained local classifier
  confidence/margin. The Qwen stratified 80-row fallback run selected 21 rows
  for review: 2 hard repair rows and 19 Qwen semantic-check rows.

Latest merged public artifacts:

```text
data/outputs/recommended_merged.profile.json
data/outputs/recommended_merged.balanced.csv
data/outputs/recommended_merged.balanced.manifest.json
data/outputs/recommended_merged.balanced.validation.json
data/outputs/recommended_merged.balanced.source_regression.json
data/outputs/lm_context_benchmark.summary.json
data/outputs/lm_context_benchmark.tailscale.blocked.json
data/outputs/lm_context_benchmark.liquid-lfm2-1.2b.sample20.gateway.json
data/outputs/lm_context_benchmark.mistralai-ministral-3-3b.sample100.gateway.json
data/outputs/lm_context_benchmark.nvidia-nemotron-3-nano-4b.sample20.gateway.json
data/outputs/lm_context_benchmark.qwen-qwen3-4b-2507.sample20.gateway.json
data/outputs/lm_context_benchmark.qwen-qwen3-4b-2507.sample100.labelaware.json
data/outputs/recommended_merged.qwen_stratified80.qwen_experiment_summary.json
data/outputs/recommended_merged.qwen_stratified80.semantic_triage.json
```

Latest verification:

```text
.venv/bin/python -m pytest -q -> 118 passed, 1 skipped in 4.34s
```

Latest source-aware merged report summary:

- rows: 159,668
- identifiers: 40,304 -> 5
- direct identifiers: 33,032 -> 4
- quasi identifiers: 7,272 -> 1
- target cue retention: 0.9999
- utility cue retention: 0.9999
- action cue retention: 0.9991
- negation/modality retention: 0.9989
- rationale span retention: 0.9998, with 47,729/47,740 spans preserved

LM Studio endpoint findings:

```text
http://169.254.83.107:1234  initially reachable, later timed out from WSL
http://172.21.96.1:1234     reachable from WSL for /v1/models and chat
http://127.0.0.1:1234       connection refused from WSL
```

Confirmed `/v1/models` IDs:

```text
google/gemma-4-e2b
qwen3-0.6b
google/gemma-3n-e4b
microsoft/phi-4-mini-reasoning
qwen/qwen3-4b
qwen/qwen3-1.7b
nvidia/nemotron-3-nano-4b
liquid/lfm2-1.2b
liquid/lfm2.5-1.2b
qwen/qwen3.6-27b
google/gemma-4-e4b
mistralai/ministral-3-3b
qwen/qwen3-4b-2507
google/gemma-4-26b-a4b-qat
google/gemma-4-12b
google/gemma-4-12b-qat
gpt-oss-safeguard-20b
text-embedding-bge-m3
zai-org/glm-4.7-flash
gemma-4-26b-a4b-it
text-embedding-nomic-embed-text-v1.5
openai/gpt-oss-20b
```

LM context benchmark conclusion:

- Parser was hardened for fenced JSON, JSON arrays, alias keys, boolean tag
  fields, and explicit empty structured outputs.
- Smoke/sample20/sample100 reports are aggregated in
  `data/outputs/lm_context_benchmark.summary.json`.
- Best parse/speed candidates still failed the utility/safety bar:
  - `liquid/lfm2-1.2b` sample20: parse-valid 1.0, p50 0.3051s, rows/sec
    2.2848, agreement 0.0625, 3 maskable cue violations.
  - `mistralai/ministral-3-3b` sample100: parse-valid 1.0, p50 1.1017s,
    rows/sec 0.9268, agreement 0.1525, 9 maskable cue violations.
  - `qwen/qwen3-4b-2507` sample20: parse-valid 1.0, p50 0.8756s, rows/sec
    0.8739, agreement 0.1663, 3 maskable cue violations.
  - `nvidia/nemotron-3-nano-4b` sample20: parse-valid 0.25, agreement 0.4133
    on only five parsed rows.
- Decision: do not integrate LM Studio context labels into deterministic rules
  or reranking yet. Keep deterministic context/rationale/cue checks as the
  trusted signal and treat local LMs as optional exploratory diagnostics.

Recent commits:

```text
9d69910 Add continuation prompt for model experiments
f6198f6 Add official submission checklist
9625803 Add HSD cue retention checks
9fb1d41 Add local LLM candidate harness
8412b81 Add Presidio comparison baseline
```

## Verification

Latest base suite:

```text
.venv/bin/python -m pytest -q
116 passed, 1 skipped
```

Latest optional classifier suite:

```text
.venv/bin/python -m pytest -q
116 passed, 1 skipped
```

Latest overnight focused suite:

```text
.venv/bin/python -m pytest -q tests/test_context.py tests/test_rationale_checks.py tests/test_source_report.py tests/test_lm_context_benchmark.py tests/test_cue_checks.py
18 passed
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

Latest aggregate experiment results:

| Variant | Residual IDs | Residual quasi IDs | Target retention | Character retention | Local macro-F1 delta | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `balanced` | 3 | 0 | 0.9994 | 0.9953 | -0.0008 | Prior full Dynahate run. |
| `balanced --style-scrub` | 3 | 0 | 0.9994 | 0.9434 | +0.0017 | Stronger style normalization; 77 changed local predictions. |
| `rerank-candidates` | 3 | 0 | 0.9997 | 0.9868 | +0.0019 | Chose `balanced` for 37,506 rows, `style_scrubbed` for 3,615, `privacy` for 23. |
| `rerank-candidates --presidio-augment` | 3 | 0 | 0.9997 | 0.9755 | +0.0048 | Chose `presidio_augmented` for 6,085 rows, `balanced` for 31,821, `style_scrubbed` for 3,219, `privacy` for 19. |
| `create-submission --replace-text --mode balanced` | 3 | 0 | 0.9994 | 0.9953 | n/a | Exact-format validation passed: 41,144 rows, same columns/order, no helper columns. |

Reranked cue check:

- rows with any conservative cue loss: 59
- target-term retention mean: 0.9971
- utility-cue retention mean: 1.0
- action-term retention mean: 0.9995
- negation/modality retention mean: 1.0001

HF utility on `data/outputs/dynahate.reranked.csv`:

- `.venv` environment: `torch` 2.12.0+cpu, `transformers` 5.11.0, CUDA not
  available.
- sample 100 default probes:
  - `facebook/roberta-hate-speech-dynabench-r4-target`: revision
    `391c99ab8b3f65beb77746a2cf6ddf1ddf9817e6`, CPU runtime 36.637s,
    mean delta -0.0005, mean absolute drift 0.0005, agreement 1.0, no large
    utility-drop rows.
  - `cardiffnlp/twitter-roberta-base-hate-latest`: revision
    `cc56585908cbda6d04ba2e1234d911fd1578c9ab`, CPU runtime 41.2954s,
    mean delta -0.0016, mean absolute drift 0.0019, agreement 1.0, no large
    utility-drop rows.
- sample 25 toxicity proxy:
  - `unitary/toxic-bert`: revision
    `4d6c22e74ba2fdd26bc4f7238f50766b045a0d94`, CPU runtime 20.6408s,
    mean delta -0.0, agreement 1.0, no large utility-drop rows.
- HateXplain classifier variants loaded but skipped during inference with
  `tuple index out of range`; rely on `check-hsd-cues` as the local cue
  fallback.

Presidio comparison on `data/public_dev/dynahate.csv` sample 100:

- status: ok
- runtime after setup: 0.4389s
- aggregate: PrivHSD spans 1, Presidio spans 27, overlap 1, Presidio-only 26,
  PrivHSD-only 0, false-positive-risk count 9
- dependency note: Presidio default initialization downloaded
  `en_core_web_lg` 3.8.0, a 400.7 MB spaCy model, after `en_core_web_sm` was
  installed.

Presidio comparison on `data/public_dev/dynahate.csv` sample 500:

- status: ok
- runtime after setup: 1.4907s
- aggregate: PrivHSD spans 8, Presidio spans 174, overlap 6,
  Presidio-only 168, PrivHSD-only 2, false-positive-risk count 52
- verdict: useful detector baseline, too much HSD-cue/target overmasking risk
  for core use.

Filtered Presidio augmentation full Dynahate run:

- commands:
  - `anonymize --presidio-augment`
  - `rerank-candidates --presidio-augment`
- outputs:
  - `data/outputs/dynahate.presidio_augmented.full.csv`
  - `data/outputs/dynahate.presidio_augmented.full.audit.json`
  - `data/outputs/dynahate.reranked_presidio.full.csv`
  - `data/outputs/dynahate.reranked_presidio.full.audit.json`
  - `data/outputs/dynahate.reranked_presidio.full.utility_benchmark.json`
  - `data/outputs/dynahate.reranked_presidio.full.cue_checks.json`
- accepted filtered Presidio spans in direct augmented run: DATE 1,400,
  LOCATION 5,185, PERSON 3,834
- rejected raw Presidio spans: NRP preserved 14,021, transient date 2,315,
  location shape 935, person shape 611, protected cue overlap 148,
  unsupported type 705
- rerank chosen counts: balanced 31,821, presidio_augmented 6,085,
  style_scrubbed 3,219, privacy 19
- local utility benchmark: macro-F1 delta +0.0048, accuracy delta +0.0046,
  prediction agreement 0.9838
- cue check: rows with loss 58, target-term retention 0.9974,
  utility-cue retention 1.0, action-term retention 0.9995,
  negation/modality retention 1.0
- concrete behavior: masks `Amy`, `Steven`, `Mustafa`, `Britain`,
  `Caribbean`, and `the 1950s`; preserves target terms like `Muslims` and
  `Hindus`; rejects false positives like `ngl` and `sl33p`.
- verdict: strongest experimental alternate after `balanced`; still optional
  because Presidio/spaCy is a heavy dependency.

Weak token-action training on `data/public_dev/dynahate.csv` sample 5,000:

- command: `train-token-action-tagger`
- outputs:
  `data/outputs/dynahate.token_action_tagger.sample5000.json` and `.pkl`
- tokens: 67,415
- dev accuracy: 0.9888
- dev macro-F1: 0.8556
- per-action highlights: `PROTECT_HSD` F1 0.9890, `PROTECT_TARGET` F1 0.7810,
  `MASK_IDENTIFIER` F1 0.8000 on two dev examples,
  `GENERALIZE_CONTEXT` F1 0.5823
- verdict: useful as a future detector/reranker feature, not supervised privacy
  truth.

DPMLM bounded evidence:

- installed `dpmlm` 1.1.2 in `.venv`; downloaded NLTK resources to
  `/home/bati/nltk_data`
- `dpmlm-spike` remains the backend/blocker report; raw direct tiny-model probe
  changed protected cues, so raw DPMLM sentence rewrite is unsafe
- new command: `generate-dpmlm-candidates`
- adapter policy: low-level token API, `FacebookAI/roberta-base` by default,
  per-row seeding, frozen target/utility/action/negation cues, stopwords,
  capitalized tokens, repeated-letter tokens, placeholders, and punctuation
- safe-default run:
  `data/outputs/dynahate.dpmlm_candidates.roberta.sample8.eps100.safe2.report.json`
  accepted 0/8 candidates in 3.9847s because no safe rewrite targets remained
- looser min-score-4 run:
  `data/outputs/dynahate.dpmlm_candidates.roberta.min4.sample12.eps100.final.report.json`
  accepted 11/12 candidates in 4.9143s and rejected one no-token-change row
- final rerank:
  `data/outputs/dynahate.dpmlm_reranked.roberta.min4.sample12.eps100.final.audit.json`
  selected `balanced` for 10 rows, `style_scrubbed` for 2 rows, and 0 DPMLM
  candidates
- verdict: adapter works as an optional candidate source, but current evidence
  says not to submit or scale DPMLM.

Metadata/author leakage evidence:

- `evaluate-author-risk --author-col id` on Dynahate skips with
  `insufficient_author_rows` because each `id` occurs once; this is expected and
  means `id` is not a valid author surrogate.
- `evaluate-author-risk --author-col source` skips with
  `insufficient_author_labels` because `source` is always `dynahate`.
- `check-metadata-leakage` found 0 exact/normalized `id` leaks in
  `data/public_dev/dynahate.csv` `text`.
- `check-metadata-leakage` found 0 exact/normalized `id` leaks in
  `data/outputs/dynahate.reranked_presidio.full.csv` for both `text` and
  `privatized_text`.
- If official files have `id,author,text,HS`, run direct leakage checks on
  `id` and `author`, then run `evaluate-author-risk --author-col author` if
  each author has at least two rows and enough train/dev support.

Local LLM bounded evidence:

- Endpoint: `http://100.120.207.64:1234/v1/chat/completions`
- Available model smoke tests:
  - `openai/gpt-oss-20b`: real sample path works.
  - `mistralai/ministral-3-3b`: synthetic JSON passed, but real sample 3
    accepted 0/3 under conservative checks.
  - `qwen/qwen3-4b-2507`: synthetic JSON passed, but real sample 3 accepted
    0/3 because of length drift or target cue loss.
  - `google/gemma-4-e4b`: synthetic JSON passed, but real sample 3 accepted
    0/3 because of length drift or target cue loss.
  - `zai-org/glm-4.7-flash`: synthetic structured request returned empty
    content.
- `openai/gpt-oss-20b` sample 10 with `--max-length-drift 0.75`: accepted 3,
  rejected 7, runtime 18.2567s.
- Full preserved-shape rerank with `--candidate-col llm_candidate` selected no
  LLM candidates. Chosen counts stayed `balanced` 37,506, `style_scrubbed`
  3,615, `privacy` 23.
- LLM-reranked metrics match deterministic reranked metrics: residual IDs 3,
  residual quasi IDs 0, target-cue retention mean 0.9997, character retention
  0.9868, local macro-F1 delta +0.0019.
- Verdict: local LLM harness is functional, but current model outputs are
  low-yield and should not be scaled or submitted directly.

Generated outputs are under ignored `data/outputs/`. Current baseline,
reranked, Presidio-reranked, and submission artifacts stay at the top level.
Older LLM, DPMLM, HF, classifier, ablation, and comparison runs were moved to
`data/outputs/archive/2026-06-11-experiment-runs/`.

## Next Work

Follow `docs/project/roadmap.md`.

Recommended next sequence while official files are unavailable:

1. Review `docs/project/experiment_verdict.md` for the compact decision table.
2. Use `rerank-candidates --presidio-augment` as the strongest alternate after
   the first `balanced` official submission.
3. A36 follow-up: use the weak token-action tagger as a reranker/scorer feature
   or uncertainty detector, not as a direct anonymizer.
4. Optional A30 extension: run sample 500 HF utility only if CPU runtime,
   model-card review, and cache size are acceptable.
5. DPMLM follow-up: keep it candidate-only; scale only if a better policy or
   official metrics show protected-token DPMLM beating deterministic/reranked
   outputs.
6. A34/A35: run transformer fine-tuning or attention experiments only as
   optional evaluators/rerankers/candidate scorers, then document whether they
   improve measured privacy/HSD tradeoff enough to justify complexity.
7. When official files arrive, return to `create-submission`,
   `validate-submission`, upload, and leaderboard-driven iteration.

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
