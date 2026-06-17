# Providers And Models

Status: active
Last verified: 2026-06-17

The final runtime has a small provider/model story.

## Always-On Code

- Deterministic PII detectors and masking rules.
- Span fusion and overlap filtering.
- Residual direct-identifier cleanup.
- HSD cue safeguards.

## Optional PII Assist

Presidio and scrubadub are local optional helpers. They add span evidence only;
they do not directly rewrite text. Their spans pass through fusion, filtering,
cue checks, and candidate selection.

Missing dependencies or initialization errors are reported in the manifest and
fall back to deterministic output.

## Local LLM Sidecar Review

The main retained classifier runtime is
`contextsafe_hsd.models.local_llm_hsd_review_runtime`.

It runs after sanitization, receives cleaned text only, and returns structured
sidecar metadata:

- HSD label
- reason tags
- review-needed flag
- parse/fallback counts
- validated residual PII suggestions

It must not rewrite whole comments and must not append columns to exact output.

## Default Local LLM Verifier

`contextsafe_hsd.models.local_llm_hsd_verifier_runtime` is the default
second-pass verifier for local LLM runs. It runs only after the main local LLM
reviewer and only on rows the main reviewer marked positive.

It returns:

- agree/disagree/uncertain decision
- suggested label
- reason code
- human-review routing action
- parse/fallback counts

Verifier output is sidecar-only. It must not rewrite text, append CSV columns,
or override the main sidecar label automatically. Use `--llm-verifier off` to
disable it for offline or classifier-only runs.

## Verifier Evaluation Command

`mini-verifier-eval` is an isolated command for comparing local HSD verifier
models against the current `openai/gpt-oss-20b` sidecar review. It does not
modify protected text or append output columns.

The 2026-06-16 follow-up runs tested `qwen/qwen3-4b` and
`qwen/qwen3.5-9b` as sidecar-only positive verifiers. Both remain research
artifacts: neither model should be used as an automatic label-changing
safeguard because the recall damage is too high relative to the precision gain.
The one-off full-sample Qwen comparison command was removed from the public CLI;
keep those results under ignored `data/outputs/` paths if they are needed for
council review.

Keep generated verifier artifacts under ignored `data/outputs/` paths.

## Removed Runtime Families

The final package does not include:

- GLiNER provider code
- HSD advisory model ensembles
- ML classifier training/evaluation/prediction commands
- semantic triage/report commands
- token-policy, DPMLM, or local LLM rewrite candidates
- dataset preparation scripts

Historical experiments can be rebuilt outside the public package if needed.
