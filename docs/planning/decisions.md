# Decisions

Status: active
Owner area: architectural decisions
Last verified: 2026-06-15
Primary code: repository-wide

Use this file for short decisions that multiple agents need to respect.

## ADR-001: Active Docs Are Split By Ownership

Decision: active docs are organized as runbooks, reference, planning, research,
challenge, and coordination docs.

Reason: a single mixed roadmap made targeted updates unreliable. Agents need
one authoritative place per topic.

Implication: do not reintroduce command recipes into architecture docs or
current evidence into stable references.

## ADR-002: Exact CSV Shape Is A Contract

Decision: exact-format submission output preserves row count, row order, column
order, and non-text columns.

Reason: challenge submissions and downstream evaluation depend on stable CSV
shape.

Implication: row filtering, helper columns, or metadata transformations must be
explicit local-audit paths unless challenge rules say otherwise.

## ADR-003: Optional Components Are Local And Advisory By Default

Decision: Presidio, GLiNER, scrubadub, token-policy, semantic models, DPMLM,
SanText, and local LLMs cannot be direct official output sources.

Reason: optional components can be unavailable, slow, overmask protected cues,
or drift semantically.

Implication: optional output must pass fallback, fusion, reranking, cue checks,
and validation before influencing a candidate.

## ADR-004: Fast Metrics Are The Default Exact Path

Decision: exact submissions use fast metrics by default.

Reason: deep cue/profanity/semantic scans can make routine exact output too
slow.

Implication: deep or sampled reports are explicit local audits under ignored
`data/` paths.

## ADR-005: Enriched Classification Output Is Not Submission Output

Decision: `sanitize-classify` may replace text in place and append advisory HSD
prediction columns for local triage, but exact-format uploads still use
`create-submission`.

Reason: challenge submissions need stable input schema, while local triage
benefits from prediction columns and aggregate original-vs-sanitized score
drift.

Implication: do not present appended `is_hate_speech`, `hate_speech_score`, or
`hate_speech_model_count` columns as upload-ready unless challenge rules change.

## ADR-006: Local LLM HSD Review Is Post-PII And Advisory

Decision: deterministic PII removal remains the required first stage. Local LLM
HSD review may be added as an opt-in post-cleaning backend alongside the current
ML classifier, and may emit residual PII suggestions for traceable review
metadata only.

Reason: benchmark evidence shows deterministic PII removal is safer than
LLM-only scrubbing, while local LLM HSD classification can improve strict
hate/not-hate recall. Residual PII suggestions are useful but too noisy for
automatic removal.

Implication: local LLM review must receive cleaned text only, must not rewrite
or apply removals, and must keep ML classification available as an alternative.
See `docs/planning/llm_hsd_review_integration/plan.md`.
