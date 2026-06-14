# CLI Reference

Status: active
Owner area: CLI and public command contracts
Last verified: 2026-06-13
Primary code: `privhsd/cli.py`, `contextsafe_hsd/`

This file maps command ownership. Full recipes belong in `docs/runbooks/`.

## Core Submission Commands

| Command | Owner workstream | Notes |
| --- | --- | --- |
| `profile-dataset` | CSV contract and submission | Inspect columns before choosing a run path. |
| `create-submission` | CSV contract and auto orchestration | Primary exact-format output. Use `--replace-text --mode auto --metric-depth fast`. |
| `validate-submission` | CSV contract and submission | Required upload gate. |
| `anonymize` | CSV contract and deterministic masking | Local output path; may add helper columns unless replace-text is used. |
| `sanitize-classify` | Auto orchestration and HSD advisory | Enriched local output: text replaced in place plus appended HSD prediction columns. Not exact-format. |

## Evidence And Audit Commands

| Command | Owner workstream | Notes |
| --- | --- | --- |
| `source-regression-report` | Metrics and evaluation | Slice privacy/utility by metadata columns. |
| `cue-checks` | Metrics and evaluation | Check target/action/negation/modality retention. |
| `semantic-triage-report` | Metrics and evaluation | Produce repair/review queues. |
| `evaluate-author-risk` | Metrics and evaluation | Only meaningful with repeated author/user IDs. |
| `benchmark-utility` | Metrics and evaluation | Local classifier utility proxy. |
| `bound-contributions` | CSV contract and evaluation | Drops rows; not exact-format by default. |

## Model And Candidate Commands

| Command | Owner workstream | Notes |
| --- | --- | --- |
| `rerank-candidates` | Candidate generation and reranking | Checked alternate path, never raw provider output. |
| `train-token-policy` | Token-policy training and runtime | Weak token-action model training. |
| `evaluate-token-policy` | Token-policy training and runtime | Single model evaluation. |
| `evaluate-token-policy-ensemble` | Token-policy training and runtime | Ensemble evaluation. |
| `predict-token-policy-ensemble` | Token-policy training and runtime | Advisory predictions. |
| `apply-token-policy-candidates` | Candidate generation and reranking | Candidate helper; still requires audit. |
| `generate-dpmlm-candidates` | Candidate generation and reranking | Research candidate path. |
| `generate-llm-candidates` | Candidate generation and reranking | Local candidate path only. |

## Shared Runtime Flags

Important exact-output flags:

```text
--mode auto
--replace-text
--metric-depth fast|sampled|deep
--allow-model-download
--gliner-model MODEL_ID_OR_LOCAL_PATH
--gliner-profile general|pii
--hsd-advisory-model APPROVED_MODEL_ID
--device auto|cpu|cuda
--disable-provider NAME
--disable-model NAME
--audit-level summary|row|debug
```

Defaults should favor exact shape, local-only execution, fast metrics, and safe
fallbacks.
