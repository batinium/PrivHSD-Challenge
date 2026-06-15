# Current Status

Status: active
Owner area: planning and evidence snapshot
Last verified: 2026-06-15
Primary code: all workstreams

This file records durable conclusions. Raw outputs, model weights, and row-level
reports remain under ignored `data/outputs/`.

## Readiness

Current readiness: simplified public pipeline ready for local verification with
caveats.

`protect` is now the short public command. Its default exact preset calls the
existing exact `auto` path, preserves schema, writes cleaned text only, and
records a stage-first manifest. The public story is:

```text
Input CSV -> Privacy Detection -> Meaning Protection -> Verification
```

It is not a guarantee that every identifier is removed; residual risk is
reduced, checked, and reported.

The enriched `sanitize-classify` workflow is available for local unseen-data
triage. It preserves original rows and metadata, replaces the selected text
column with sanitized text, appends HSD prediction columns, and records
original-vs-sanitized advisory score drift without row text. It is not an
exact-format upload path.

## Current CLI Contract

- `protect` is the public default. `--preset exact` preserves schema and
  writes cleaned text only; `--preset analysis` appends advisory HSD columns
  for local review; `--preset audit` preserves exact output and requests deeper
  sidecar/audit reporting.
- `create-submission` remains the legacy exact-format path. It requires
  `--replace-text`, preserves row count/order/columns, and rejects helper
  columns during validation.
- `anonymize` is the general CSV path. It defaults to `mode=balanced`,
  `output_col=privatized_text`, and `metric-depth=fast`; `--mode auto`
  enables routed optional providers/models.
- `sanitize-classify` always uses auto orchestration, replaces the selected
  text column, and appends advisory HSD columns. If a gold
  `is_hate_speech` column exists, predictions are written to
  `predicted_is_hate_speech` unless `--overwrite-hate-columns` is passed.
- Optional Presidio and scrubadub are presented publicly as internal PII
  Assist. Deterministic rules always run. GLiNER is no longer part of the
  default public auto path after a no-gain ablation; it remains available only
  for explicit local research/debug runs with configured artifacts.
- Token-policy and HSD advisory outputs remain internal advisory evidence
  behind routing, fusion, candidate scoring, verification, and fallback.
- Exact and auto CSV paths default to `metric-depth=fast`; sampled/deep metrics
  are opt-in local audits.

## Latest Verification Snapshot

Travel handoff on 2026-06-15:

- No pipeline or LLM experiment process is intentionally left running.
- The main deterministic pipeline is intact. Use `protect --preset exact` or
  `create-submission --replace-text` for an upload-shaped CSV that keeps the
  original columns and replaces `text` 1:1. Use `sanitize-classify` only for
  local analysis because it appends HSD helper columns.
- Local LLM classification is functional through the OpenAI-compatible endpoint
  `http://100.120.207.64:1234/v1/chat/completions` with model
  `openai/gpt-oss-20b`.
- The old HF HSD advisory classifier is disabled when
  `--hsd-classification-backend local-llm` is selected.
- Optional author-group masking is implemented for `protect`,
  `create-submission`, and `sanitize-classify`. It treats numeric `author`
  values as grouping keys only and masks only repeated detector-backed factual
  spans, not style.

Real train split full sweep:

```bash
python -m contextsafe_hsd.cli sanitize-classify \
  --input data/train/train_split.csv \
  --output data/outputs/real_train_split/train_split.local_llm_gpt_oss.author_group.csv \
  --text-col text \
  --hsd-classification-backend local-llm \
  --local-llm-endpoint http://100.120.207.64:1234/v1/chat/completions \
  --local-llm-model openai/gpt-oss-20b \
  --local-llm-batch-size 10 \
  --require-hate-classification \
  --metric-depth fast \
  --enable-author-group-masking \
  --author-group-col author \
  --progress \
  --manifest data/outputs/real_train_split/train_split.local_llm_gpt_oss.author_group.manifest.json \
  --audit data/outputs/real_train_split/train_split.local_llm_gpt_oss.author_group.audit.json
```

Observed result:

- Validation passed; input and output both had 1,154 rows.
- `text` changed on 312 rows.
- Identifier detections: 434 before -> 3 after.
- Direct identifiers: 215 before -> 0 after.
- Remaining residuals: 3 quasi-identifier `LOCATION` detections.
- Target cue retention mean 0.9982; utility cue retention mean 0.9991;
  character utility retention mean 0.9469.
- Local LLM classification parsed all 1,154 rows, made 176 requests, and had
  60 fallback rows; classification elapsed time was 361.431 seconds.
- Local LLM prediction counts were 685 non-HSD and 469 HSD.
- Against the available `hs` column, local LLM classification metrics were:
  accuracy 0.7764, balanced accuracy 0.7798, precision 0.6141, recall 0.7890,
  F1 0.6906, confusion matrix TN 608 / FP 181 / FN 77 / TP 288.
- Author-group masking found 25 authors, considered all 25, found only 3
  candidate residual values, found 0 repeated values, and changed 0 rows.
- The author-group run was text- and label-identical to the previous local LLM
  run without author-group masking.

Performance notes:

- The slow parts before LLM were Presidio provider preprocessing and final
  metric/selection verification. The LLM endpoint was not contacted until those
  stages completed.
- The direct batch-size-20 LLM-only experiment was started on the already
  sanitized output to test request reduction, then stopped at user request
  before it produced a result. There is no valid batch-size-20 conclusion yet.
- Before retrying LLM-call reduction, add a cached/classify-only command or a
  progress hook around `LocalLlmHsdReviewRuntime.review_texts`; otherwise it is
  hard to tell whether a large batch is slow or stalled.

Cleanup follow-up:

- Plan a large dead-code cleanup separately. Highest-value targets are legacy
  abandoned candidate/model paths, duplicated CSV command surfaces, slow metric
  recomputation, stale workbench paths, and disabled advisory/model branches.
- Do not remove the intact MVP path: exact CSV protection/submission,
  deterministic masking, PII Assist, local LLM classification metadata, author
  group masking, validation, and manifest/audit generation.
- Final cleanup handoff for the next unattended agent:
  `docs/planning/final_pipeline_simplification/prompt.md`.

Simplification implementation verification:

- `git diff --check`: passed.
- `python -m privhsd.cli protect --help`: passed.
- `python -m privhsd.cli create-submission --help`: passed.
- `python -m privhsd.cli sanitize-classify --help`: passed.
- `python -m pytest tests/test_pipeline.py tests/test_metrics.py tests/test_auto_pipeline.py tests/test_submission.py tests/test_simple_pipeline.py -q`: 61 passed.
- `python -m pytest tests/test_pipeline.py tests/test_metrics.py -q`: 38 passed.
- `python -m pytest tests/test_submission.py tests/test_auto_pipeline.py tests/test_simple_pipeline.py -q`: 23 passed.
- `python -m pytest tests/test_metadata_leakage.py tests/test_workbench_csv.py -q`: 6 passed, 9 dependency deprecation warnings.
- `python -m pytest tests/test_synthetic_pii_stress.py -q`: 3 passed.
- `python -m pytest -q`: 200 passed, 1 skipped, 9 dependency deprecation warnings.
- Tiny `protect --preset exact` smoke preserved schema, masked lower-case
  address/place examples, kept `Muslims should leave`, and wrote a
  `privacy_detection` / `meaning_protection` / `verification` manifest.

Most recent local configuration search and final enriched CSV run:

- Matrix input: `data/external_unseen/tweet_eval_hate_offensive_test.csv`
  with 3,830 rows.
- Matrix output: `data/outputs/config_search_tweet_eval_20260614_patch1/`.
- Selected command:

```bash
python -m privhsd.cli sanitize-classify \
  --input data/external_unseen/tweet_eval_hate_offensive_test.csv \
  --output data/outputs/tweet_eval_hate_offensive_test.trusted_sanitize_classify_final.csv \
  --text-col text \
  --id-col id \
  --manifest data/outputs/tweet_eval_hate_offensive_test.trusted_sanitize_classify_final.manifest.json \
  --require-hate-classification \
  --max-model-batch-size 32
```

Final aggregate result:

- validation passed, 3,830 rows in and 3,830 rows out;
- `text` replaced in place and `is_hate_speech`, `hate_speech_score`,
  `hate_speech_model_count` appended;
- chosen candidates: balanced 1,662, provider fusion 124, style scrubbed
  1,099, token policy 945;
- direct identifiers 4,205 -> 1, quasi identifiers -> 0;
- target cue retention mean 1.0062, utility cue retention mean 1.0048,
  character utility retention mean 0.8512;
- HSD advisory status ok, two models, 1,971 positive and 1,859 negative
  predictions, 0.9802 original-vs-sanitized decision agreement.

Focused regression after detector tuning:

- `python -m pytest tests/test_pipeline.py -q`: 26 passed.
- `python -m pytest tests/test_pipeline.py tests/test_synthetic_pii_stress.py -q`: 29 passed during the docs refresh.
- Point-in-time optional dependency import check during the docs refresh:
  GLiNER, Presidio, scrubadub, torch, and transformers importable;
  sentence-transformers and Detoxify not importable.

Most recent local verification after the simplified pipeline and HSD advisory
ensemble update:

- `python -m compileall privhsd contextsafe_hsd workbench/backend`: passed.
- `python -m pytest tests/test_simple_pipeline.py tests/test_auto_pipeline.py tests/test_hf_utility.py tests/test_submission.py tests/test_csv_pipeline.py -q`: 29 passed.
- `python -m pytest -q`: 184 passed, 1 skipped.
- `cd workbench/frontend && npm run build`: passed.
- CLI smoke passed on cached local advisory models:

```bash
python -m privhsd.cli sanitize-classify \
  --input tests/fixtures/synthetic_pii_stress.csv \
  --output data/outputs/smoke.sanitize_classify.csv \
  --text-col text \
  --id-col id \
  --manifest data/outputs/smoke.sanitize_classify.manifest.json \
  --disable-provider presidio \
  --disable-provider scrubadub \
  --disable-provider gliner \
  --disable-model token_policy_ensemble \
  --disable-model semantic \
  --max-model-batch-size 4
```

Previous local verification after the unified auto/provider update:

- `python -m compileall privhsd workbench/backend`: passed.
- `python -m pytest -q`: 180 passed, 1 skipped.

Previous recorded verification from the pre-cleanup planning notes:

- `python -m compileall privhsd workbench/backend`: passed.
- `python -m pytest -q`: 164 passed, 1 skipped.
- `cd workbench/frontend && npm run build`: passed.
- Local environment had Presidio, torch, transformers, CUDA, and local
  RoBERTa/HateBERT token-policy artifacts.
- Local environment was missing scrubadub, GLiNER, sentence-transformers, and
  Detoxify.

Re-run these commands before treating this status as current.

## Evidence Table

| Path | Latest durable evidence | Verdict |
| --- | --- | --- |
| `auto` exact-format | Preserves exact schema, records provider/model status, falls back safely when optional components are missing. | Primary path for new exact-format candidates. |
| `sanitize-classify` enriched CSV | Replaces text in place, preserves original metadata, appends advisory HSD prediction columns, and logs aggregate score drift only. | Practical local path for large unseen CSV triage; not an upload candidate. |
| `balanced` exact-format | Merged public bundle: 159,668 rows, validation passed, identifier detections 40,304 -> 5, target and utility cue retention 0.9999. | Deterministic compatibility fallback. |
| Source-aware regression | Reports by source/label/split/platform/type and row ID without raw text. | Required before tuning or pitching. |
| Filtered Presidio reranking | Full Dynahate run selected filtered Presidio candidate for 6,085 rows with utility-cue retention 1.0 and target retention 0.9974. | Strong alternate after baseline validation. |
| RoBERTa token policy | 30k action-balanced weak labels, CUDA, one epoch, dev macro F1 0.9061. | Advisory model and presentation evidence. |
| RoBERTa grouped K-fold | Five grouped folds, macro F1 mean 0.8977, zero duplicate text overlap across folds. | Anti-overfit evidence. |
| RoBERTa + HateBERT ensemble | External TweetEval macro F1 0.8837, `PROTECT_TARGET` F1 0.8143. | Best current token-policy evidence. |
| Local LLM and DPMLM candidates | Generated and validated candidates, but reranking selected few or none. | Candidate-only research paths. |

## Current Submission Rule

Create `auto` first and validate exact shape. Use `balanced` as the deterministic
fallback and compare alternates only after the baseline exists. Use
token-policy outputs as advisory evidence or reranker support until an audited
candidate path improves official scores.
