# Providers And Models Reference

Status: active
Owner area: auto orchestration, span providers, token-policy runtime
Last verified: 2026-06-13
Primary code: `privhsd/auto/context.py`, `privhsd/auto/model_registry.py`,
`privhsd/span_providers/`, `privhsd/models/`

This is the authoritative reference for optional providers and local model
behavior.

## Lifecycle Rules

- Build one `AutoPipelineContext` at command startup.
- Load resources, providers, and local model artifacts once per run.
- Keep loaded components alive until the run finishes.
- Batch model inference when the model API supports it.
- Default to local-only model usage. Downloads require
  `--allow-model-download`.
- Missing optional dependencies or artifacts must produce structured manifest
  status and deterministic fallback, not exact-output failure.
- Provider/model audit payloads must not include raw row text.

## Provider Order

| Component | Status rule | Role |
| --- | --- | --- |
| Deterministic provider | Always ready | Baseline spans and fallback candidate |
| Presidio | Ready if dependency and spaCy model initialize | Names, locations, durable dates after filtering |
| scrubadub | Ready if dependency initializes | Supplemental identifier spans |
| GLiNER | Ready if dependency and local/download-allowed model exist | Supplemental NER spans |
| Token-policy ensemble | Ready if local model dirs and torch/transformers initialize | Advisory token-action evidence |
| Semantic/HSD advisory | Ready only if artifacts and dependencies exist | Candidate drift/audit support |
| Local LLM reviewer | Disabled by default in official mode | Structured local review only |

Example manifest status:

```json
{
  "providers": {
    "deterministic": {"status": "ready"},
    "presidio": {"status": "ready"},
    "gliner": {"status": "missing_dependency"},
    "scrubadub": {"status": "missing_dependency"},
    "token_policy_ensemble": {"status": "ready", "device": "cuda"}
  }
}
```

## Token-Policy Role

The token-policy model is trained on weak token-action labels, not private
identity gold labels. Current actions are:

```text
KEEP
MASK_IDENTIFIER
GENERALIZE_CONTEXT
PROTECT_TARGET
PROTECT_HSD
NORMALIZE_STYLE
REVIEW
```

Runtime mapping:

- `MASK_IDENTIFIER` and `GENERALIZE_CONTEXT` become span evidence for fusion.
- `PROTECT_TARGET` and `PROTECT_HSD` protect HSD evidence from overmasking.
- `NORMALIZE_STYLE` is style-candidate evidence.
- `REVIEW` is routing/audit evidence.

Token-policy output never directly overwrites final text. It must pass fusion,
candidate scoring, cue checks, and exact-format validation before influencing
an output candidate.

## Acceptance Tests

- Fake provider/model load counters show one load per run, not one load per row.
- Missing dependency/artifact statuses do not fail exact submission.
- CUDA model load failures fall back to CPU or skip according to configured
  severity.
- Token-policy candidates cannot mask protected target terms unless fusion and
  cue policy explicitly allow it.
