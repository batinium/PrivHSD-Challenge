# Providers And Models

Status: active
Last verified: 2026-06-17

The final runtime has a small provider/model story.

## Always-On Code

- Deterministic PII detectors and masking rules.
- Technical PII checks for de-obfuscated emails, IPs, crypto wallets, Discord
  handles, social links, Luhn-valid credit cards, and Mod-97-valid IBANs.
- Span fusion and overlap filtering.
- Residual direct-identifier cleanup.
- Cue-safe style scrubbing and repeated author-group residual masking.
- HSD cue safeguards.

## Optional PII Assist

Presidio and scrubadub are local optional helpers. They add span evidence only;
they do not directly rewrite text. Their spans pass through fusion, filtering,
cue checks, and candidate selection.

Missing dependencies or initialization errors are reported in the manifest and
fall back to deterministic output.

## Default HF HSD Classifier

The default sidecar classifier is
`contextsafe_hsd.models.hf_hsd_classifier_runtime`.

It runs after sanitization, receives cleaned text only, and writes sidecar
metadata without changing the exact CSV. The selected checkpoint is
`Hate-speech-CNERG/dehatebert-mono-english` fine-tuned on the official train
split with 5-fold out-of-fold validation:

- model path: `data/outputs/dehatebert_official_kfold_20260617/final_model`
- threshold: `0.850469`
- OOF best F1: `0.8289`

Use `--hsd-classifier off` for privacy-only runs without sidecar labels.

## Optional Local LLM Sidecar Review

The retained GPT/local LLM backup runtime is
`contextsafe_hsd.models.local_llm_hsd_review_runtime`.

It runs after sanitization, receives cleaned text only, and returns structured
sidecar metadata:

- HSD label
- reason tags
- review-needed flag
- parse/fallback counts
- validated residual PII suggestions

It must not rewrite whole comments and must not append columns to exact output.
It is disabled by default; pass `--llm-review local-llm` only for optional
sidecar experiments.

## Optional Local LLM Verifier

`contextsafe_hsd.models.local_llm_hsd_verifier_runtime` is an opt-in
second-pass verifier for selected sidecar classifier runs. It reviews only rows
marked positive by the main sidecar classifier.

It returns:

- agree/disagree/uncertain decision
- suggested label
- reason code
- human-review routing action
- parse/fallback counts

Verifier output is sidecar-only. It must not rewrite text, append CSV columns,
or override the main sidecar label automatically. Use `--llm-verifier local-llm`
only for optional verifier experiments.

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
- semantic triage/report commands
- token-policy, DPMLM, or local LLM rewrite candidates

Historical experiments can be rebuilt outside the public package if needed.
