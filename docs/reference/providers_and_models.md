# Providers And Models Reference

Status: active
Owner area: auto orchestration, span providers, local LLM review
Last verified: 2026-06-15
Primary code: `contextsafe_hsd/auto/context.py`, `contextsafe_hsd/auto/model_registry.py`,
`contextsafe_hsd/span_providers/`, `contextsafe_hsd/models/`

This is the authoritative reference for optional local helpers and model
behavior. Public runbooks should say `PII Assist`; this file records the
component-level detail needed for debugging and research.

Detailed implementation handoffs live in planning docs. For GLiNER PII,
future `openai/privacy-filter` work, provider lifecycle history, and benchmark
gates, use `docs/planning/privacy_span_model_integration_plan.md`.

## Lifecycle Rules

- Build one `AutoPipelineContext` at command startup.
- Discover optional dependencies and local model artifacts once at command
  startup.
- Initialize optional providers/models lazily when routing sends rows to them,
  then keep loaded components alive until the run finishes.
- Batch provider/model inference when the component API supports it.
- Default sensitive-data processing to local-only model usage. Downloads
  require explicit debug/research approval and are not part of the public
  `protect` workflow.
- Missing optional dependencies or artifacts must produce structured manifest
  status and deterministic fallback, not exact-output failure.
- Provider/model audit payloads must not include raw row text.

## PII Assist

PII Assist is the internal grouping for local privacy-detection helpers. It is
not a public menu of pipeline branches.

| Component | Status rule | Role |
| --- | --- | --- |
| Deterministic baseline | Always ready | Required direct/quasi identifier spans and fallback candidate. |
| Presidio | Ready if dependency and spaCy model initialize | Supplemental names, locations, and durable dates after filtering. |
| scrubadub | Ready if dependency initializes | Supplemental direct identifier spans. |
| GLiNER | Disabled by default; available only when an explicit local/debug model is configured | Research-only supplemental NER spans. It must not download models during sensitive-data processing. |

Public manifests should group these under
`stages.privacy_detection.pii_assist.components`. The default public PII Assist
surface lists Presidio and scrubadub. GLiNER appears there only for explicit
research/debug runs that configure a model; provider-specific status and load
counts may also remain in debug sections for reproducibility.

Example grouped status:

```json
{
  "stages": {
    "privacy_detection": {
      "baseline": "deterministic_balanced",
      "pii_assist": {
        "components": {
          "presidio": "ready",
          "scrubadub": "ready"
        }
      }
    }
  },
  "providers": {
    "deterministic": {"status": "ready"},
    "presidio": {"status": "ready"},
    "scrubadub": {"status": "ready"},
    "gliner": {"status": "disabled"}
  }
}
```

## Local LLM Review

Local LLM review belongs under Verification.

In exact mode, it reviews cleaned text only and writes HSD labels, reason tags,
provider diagnostics, parse/fallback counts, and validated PII suggestions to
sidecars. It must not append columns to exact output and must not rewrite whole
comments.

## Removed Model Paths

Token-policy candidate generation and training/evaluation commands were removed
from the production code path. The final pipeline keeps deterministic span
detection, Presidio/scrubadub PII Assist, candidate selection with cue
preservation, and sidecar-only local LLM review.

Hugging Face HSD advisory model-selection and evaluation commands were removed
from the production CLI. Historical advisory results remain planning evidence
only.

## Other Research Model Paths

Semantic models and other rewrite candidates are not production branches.
Local LLM usage is limited to post-cleaning HSD classification, reason tags,
and validated residual PII suggestions in sidecars.

## Trusted Enriched Analysis

`protect --preset analysis` and the compatibility command `sanitize-classify`
may produce a local enriched CSV:

```text
Privacy Detection
  -> Meaning Protection
  -> Verification with local LLM review columns
```

This output is useful for triage and error analysis. Because it may append
columns, it is not exact-format and should not be treated as the upload path.

## Acceptance Tests

- Deterministic baseline always runs.
- Missing optional dependency/artifact statuses do not fail exact submission.
- PII Assist components load at most once per run, not once per row.
- GLiNER is not part of the default auto path and does not download models
  during sensitive-data processing.
- Exact mode writes no HSD prediction columns.
- Advisory HSD predictions are documented as local diagnostics, not production
  classifier truth.
- Token-policy candidates cannot mask protected target terms unless fusion and
  cue policy explicitly allow it.
