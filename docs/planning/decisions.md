# Decisions

Status: active
Owner area: architectural decisions
Last verified: 2026-06-13
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
