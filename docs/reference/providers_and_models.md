# Providers And Models Reference

Status: active
Owner area: auto orchestration, span providers, token-policy runtime
Last verified: 2026-06-14
Primary code: `privhsd/auto/context.py`, `privhsd/auto/model_registry.py`,
`privhsd/span_providers/`, `privhsd/models/`

This is the authoritative reference for optional providers and local model
behavior.

Detailed implementation handoffs live in planning docs. For GLiNER PII,
future `openai/privacy-filter` work, provider lifecycle history, and benchmark
gates, use `docs/planning/privacy_span_model_integration_plan.md`.

## Lifecycle Rules

- Build one `AutoPipelineContext` at command startup.
- Discover providers and local model artifacts once at command startup.
- Initialize optional providers/models lazily when routing sends rows to them,
  then keep loaded components alive until the run finishes.
- Batch provider/model inference when the component API supports it.
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
| GLiNER | Ready if dependency and local/download-allowed model exist | Supplemental NER spans; supports `general` and `pii` profiles |
| Token-policy ensemble | Ready if local model dirs and torch/transformers initialize | Advisory token-action evidence |
| HSD advisory ensemble | Ready if torch/transformers initialize and approved local/download-allowed models load | Candidate drift support and enriched hate prediction columns |
| Semantic models | Ready only if artifacts and dependencies exist | Candidate drift/audit support |
| Local LLM reviewer | Disabled by default in official mode | Structured local review only |

## Trusted Enriched Pipeline

The selected `sanitize-classify` configuration for large local CSV triage is:

```text
deterministic balanced baseline
  -> routed Presidio spans
  -> routed scrubadub spans
  -> routed token-policy ensemble spans
  -> candidate generation and fusion
  -> two-model RoBERTa HSD advisory candidate scoring
  -> selected sanitized text
  -> appended HSD label, score, and model-count columns
```

Provider/model loads are per run, not per row. The final 3,830-row unseen test
loaded Presidio once, scrubadub once, the token-policy ensemble once, and the
HSD advisory ensemble once.

Example manifest status:

```json
{
  "providers": {
    "deterministic": {"status": "ready"},
    "presidio": {"status": "ready"},
    "gliner": {"status": "missing_artifact"},
    "scrubadub": {"status": "ready"}
  },
  "models": {
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

## HSD Advisory Role

The default advisory ensemble uses these approved OSS Hugging Face classifiers
when they are available locally or `--allow-model-download` is set:

```text
facebook/roberta-hate-speech-dynabench-r4-target
cardiffnlp/twitter-roberta-base-hate-latest
```

`sanitize-classify` uses the same runtime to append prediction columns after
sanitization. The command also compares original-vs-sanitized scores in the
manifest without storing row text. The Cardiff multiclass hate model is in the
approved registry as an opt-in diagnostic probe, but it is not part of the
default binary label ensemble.

## Acceptance Tests

- Fake provider/model load counters show one load per run, not one load per row.
- Missing dependency/artifact statuses do not fail exact submission.
- CUDA model load failures fall back to CPU or skip according to configured
  severity.
- Token-policy candidates cannot mask protected target terms unless fusion and
  cue policy explicitly allow it.
