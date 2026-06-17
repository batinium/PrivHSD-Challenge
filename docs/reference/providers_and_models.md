# Providers And Models

Status: active
Last verified: 2026-06-16

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

The only retained model runtime is
`contextsafe_hsd.models.local_llm_hsd_review_runtime`.

It runs after sanitization, receives cleaned text only, and returns structured
sidecar metadata:

- HSD label
- reason tags
- review-needed flag
- parse/fallback counts
- validated residual PII suggestions

It must not rewrite whole comments and must not append columns to exact output.

## Research Verifier Candidate

`mini-4b-verifier-ablation` is an isolated research command for comparing small
local HSD verifier models against the current `openai/gpt-oss-20b` sidecar
review. It is not part of the exact CSV runtime and does not modify protected
text or append output columns.

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
