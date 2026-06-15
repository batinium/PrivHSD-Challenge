# CLI Reference

Status: active
Owner area: CLI and public command contracts
Last verified: 2026-06-15
Primary code: `pyproject.toml`, `contextsafe_hsd/cli.py`

This file maps command ownership. Full recipes belong in `docs/runbooks/`.
The installed console script is `contextsafe-hsd`, which dispatches to
`contextsafe_hsd.cli:main`. Repository examples may also use
`python -m contextsafe_hsd.cli`.

## Public Command

`protect` is the short, human-facing command for the public pipeline:

```text
Input CSV -> Privacy Detection -> Meaning Protection -> Verification
```

```bash
contextsafe-hsd protect \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col id \
  --llm-review local-llm \
  --local-llm-endpoint http://100.120.207.64:1234/v1/chat/completions \
  --local-llm-model openai/gpt-oss-20b \
  --manifest OUTPUT.manifest.json
```

`protect` defaults to `--preset exact` and uses the final exact CSV path. It is
local-first and preserves the source CSV schema in exact mode. `--llm-review
local-llm` runs sidecar-only HSD classification, reason tags, and validated PII
suggestions after sanitization; the LLM never rewrites the output CSV.

| Preset | Contract |
| --- | --- |
| `--preset exact` | Default. Cleaned text only, original schema preserved, sidecar LLM review when requested. |
| `--preset analysis` | Enriched local output. May append advisory HSD columns; not exact-format. |
| `--preset audit` | Exact output plus deeper sidecar/audit reporting when supported. |

Common public flags:

```text
--input PATH
--output PATH
--text-col COLUMN
--id-col COLUMN
--manifest PATH
--audit PATH
--preset exact|analysis|audit
--llm-review off|local-llm
--local-llm-endpoint URL
--local-llm-model MODEL
--local-llm-batch-size N
--require-llm-review
```

## Compatibility Commands

These commands remain supported for existing scripts, tests, and research
workflows.

| Command | Owner workstream | Notes |
| --- | --- | --- |
| `create-submission` | CSV contract and auto orchestration | Legacy exact-output interface without sidecar LLM review. Prefer `protect --preset exact --llm-review local-llm` for the final path. |
| `sanitize-classify` | Auto orchestration and HSD advisory | Enriched local output: text replaced in place plus appended advisory HSD prediction columns. Not exact-format. |
| `anonymize` | CSV contract and deterministic masking | Local deterministic output path; may add helper columns unless replace-text behavior is requested. |
| `validate-submission` | CSV contract and submission | Required exact-shape gate. |
| `profile-dataset` | CSV contract and submission | Inspect columns before choosing a run path. |

Important legacy exact-output flags:

```text
--replace-text
--mode auto|utility|balanced|privacy
--metric-depth fast|sampled|deep
--text-col COLUMN        # repeatable for create-submission
--manifest PATH
```

## Verification And Audit Commands

| Command | Owner workstream | Notes |
| --- | --- | --- |
| `source-regression-report` | Metrics and evaluation | Slice privacy/utility by metadata columns. |
| `check-hsd-cues` | Metrics and evaluation | Check target/action/negation/modality retention. |
| `semantic-triage-report` | Metrics and evaluation | Produce repair/review queues. |
| `check-metadata-leakage` | Metrics and evaluation | Scan whether metadata values leak into text columns. |
| `evaluate-author-risk` | Metrics and evaluation | Only meaningful with repeated author/user IDs. |
| `evaluate` | Metrics and evaluation | Local proxy metrics for an existing original/privatized-column CSV. |
| `benchmark-utility` | Metrics and evaluation | Local classifier utility proxy, not part of the public exact path. |
| `ablate` | Metrics and evaluation | Compare deterministic privatization variants. |
| `compare-presidio` | Provider evaluation | Optional provider comparison. |
| `evaluate-hf-utility` | Model evaluation | Optional Hugging Face HSD/toxicity probes. |
| `benchmark-lm-context` | Model evaluation | Local LM Studio context-labeler benchmark. |
| `bound-contributions` | CSV contract and evaluation | Drops rows; not exact-format by default. |

## Research And Candidate Commands

| Command | Owner workstream | Notes |
| --- | --- | --- |
| `hf-model-registry` | Model evaluation | Write the approved optional HF utility model registry. |
| `train-classifier` | Classifier baseline | Train a local TF-IDF/logistic baseline. |
| `evaluate-classifier` | Classifier baseline | Evaluate the local baseline on labeled CSV rows. |
| `predict-classifier` | Classifier baseline | Write row-preserving baseline predictions. |
| `train-token-action-tagger` | Token-policy training and runtime | Weakly supervised non-neural token-action tagger. |
| `label-feature-report` | Token-policy training and runtime | Source-aware weak-label feature/action report. |
| `rerank-candidates` | Candidate generation and reranking | Checked alternate path, never raw provider output. |
| `train-token-policy` | Token-policy training and runtime | Weak token-action model training. |
| `evaluate-token-policy` | Token-policy training and runtime | Single model evaluation. |
| `evaluate-token-policy-ensemble` | Token-policy training and runtime | Ensemble evaluation. |
| `predict-token-policy` | Token-policy training and runtime | Single-model advisory token-action spans. |
| `predict-token-policy-ensemble` | Token-policy training and runtime | Advisory predictions. |
| `apply-token-policy-candidates` | Candidate generation and reranking | Candidate helper; still requires audit. |

## Dataset Prep Commands

| Command | Owner workstream | Notes |
| --- | --- | --- |
| `prepare-dynahate` | Dataset preparation | Download/normalize public Dynahate data. |
| `prepare-recommended-datasets` | Dataset preparation | Download, normalize, and merge recommended public dev datasets. |
| `prepare-tweet-eval-unseen` | Dataset preparation | Fetch TweetEval hate/offensive test splits as external unseen data. |

## Debug Runtime Flags

Not every flag is accepted by every command; use `COMMAND --help` for the
exact parser contract. These are intentionally not part of `protect`:

```text
--allow-model-download
--gliner-model MODEL_ID_OR_LOCAL_PATH
--gliner-profile general|pii
--hsd-advisory-model APPROVED_MODEL_ID
--device cpu|auto|cuda  # defaults to cpu; opt in to cuda/auto explicitly
--max-model-batch-size N
--max-provider-rows N
--disable-provider NAME
--disable-model NAME
--enable-token-policy
--audit-level summary|row|debug
--style-scrub
--presidio-augment
--generalize-targets | --preserve-targets
```

GLiNER flags are research/debug-only. The default public `protect` and `auto`
path do not use GLiNER unless a command explicitly configures a model; model
downloads remain opt-in and should not be used during sensitive-data
processing.

Token-policy ensemble candidate generation is also disabled by default. Use
`--enable-token-policy` only for research or audit ablations where token-action
candidate behavior is being measured explicitly.

Important `sanitize-classify` prediction flags:

```text
--hate-label-col is_hate_speech
--hate-score-col hate_speech_score
--hate-model-count-col hate_speech_model_count
--overwrite-hate-columns
--require-hate-classification
```

Defaults should favor exact shape, local-only execution, fast verification,
deterministic fallback, and sidecar reporting of residual risk. Compatibility
commands may expose provider/model/debug controls for controlled local audits;
normal users should start with `protect`.
