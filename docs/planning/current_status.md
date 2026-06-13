# Current Status

Status: active
Owner area: planning and evidence snapshot
Last verified: 2026-06-13
Primary code: all workstreams

This file records durable conclusions. Raw outputs, model weights, and row-level
reports remain under ignored `data/outputs/`.

## Readiness

Current readiness: hackathon demo ready with caveats.

The exact-format auto pipeline works on local tests and the ignored external
TweetEval unseen CSV. It preserves schema, records provider/model status, and
loads optional heavy components once per run. It is not a guarantee that every
identifier is removed; residual-risk review remains required.

## Latest Verification Snapshot

Most recent local verification after the unified auto/provider update:

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
