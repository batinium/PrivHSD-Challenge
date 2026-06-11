# Agent Task Board

Status values: `todo`, `in_progress`, `done`, `blocked`.

## Current Tasks

| ID | Status | Owner | Task |
| --- | --- | --- | --- |
| A01 | done | Codex | Create fresh package, CLI, CSV pipeline, metrics, and tests. |
| A02 | todo | unassigned | Add official-dataset schema adapter when starter kit/schema arrives. |
| A03 | todo | unassigned | Add minimal UI only after CLI pipeline, metrics, and demo story are stable. |
| A04 | done | Codex | Improve target-group handling with a safe preserve/generalize policy. |
| A05 | done | Codex | Add lightweight local utility proxy. |
| A06 | done | Codex | Add score-log template for official leaderboard submissions. |
| A07 | done | Codex | Add packaging/install instructions. |
| A08 | todo | unassigned | Add final pitch outline and demo script. |
| A09 | done | Codex | Research OSS and academic options; convert findings into tasks. |
| A10 | done | Codex | Add scikit-learn utility benchmark for original-vs-privatized text. |
| A11 | done | Codex | Add ablation runner for identity, regex-only, balanced, privacy, and target-generalized variants. |
| A12 | done | Copernicus | Add richer privacy/utility metrics and warnings. |
| A13 | done | Codex | Add synthetic PII stress fixtures and tests. |
| A14 | todo | unassigned | Add optional Presidio/spaCy comparison as a detector baseline, not a replacement. |
| A15 | todo | unassigned | Add optional neural utility evaluators after model-license checks. |
| A16 | done | Codex | Add local baseline classifier train/evaluate/predict workflows. |
| A17 | todo | unassigned | Add authorship-risk evaluator: train an author classifier when an `author` column exists and report accuracy/F1 drop after privatization. |
| A18 | todo | unassigned | Add style-scrubbing transformer for authorship cues: casing, punctuation bursts, emojis, repeated chars, spacing, signatures, and idiolect markers. |
| A19 | todo | unassigned | Add candidate reranking: compare deterministic, style-scrubbed, target-generalized, and optional rewrite outputs by privacy/HSD utility score. |
| A20 | todo | unassigned | Spike DPMLM-style rewriting on a tiny sample; document epsilon/runtime/utility tradeoffs before any integration. |
| A21 | todo | unassigned | Prototype specialized local LLM rewriting with schema constraints and self-checks; no generic prompting and no required external API. |
| A22 | todo | unassigned | Add human-rights and judging narrative: leaderboard score is only one criterion. |
| A23 | todo | unassigned | Add official-submission checklist that verifies metadata preservation, no raw example leakage, and reproducible artifact paths. |

## Current Priority

Read `docs/roadmap.md` first. The key correction from the webinar is that the
task is not simple PII removal. The privacy adversary is authorship
identification, while the utility target is hate-speech detection. Presidio is
useful as a comparison baseline but fails as a complete solution. DPMLM-style
methods are promising but complex. LLMs may help only if specialized,
constrained, and evaluated against privacy/utility metrics.

Recommended next sequence:

1. A17: author-attribution privacy evaluator.
2. A18: style-scrubbing transformer for authorship cues.
3. A19: candidate reranking using privacy and HSD utility scores.
4. A08/A22: final pitch/demo narrative and human-rights framing.
5. A14/A20/A21: optional Presidio, DPMLM, and specialized LLM experiments.

## Non-Negotiables

- Core `privhsd anonymize` remains local and dependency-light.
- Preserve row count, row order, IDs, labels, and metadata.
- Do not commit official/raw challenge examples or downloaded datasets.
- Optimize the privacy/HSD tradeoff, not privacy alone.
- Treat leaderboard score as evidence, not the whole hackathon result.
