# Challenge Requirements

## Expected Output

The challenge expects a working method that transforms text into a
privacy-preserved version while preserving enough signal for hate speech
detection.

```text
input dataset
  -> text privatization method
  -> privatized dataset
  -> challenge evaluator
  -> privacy/utility tradeoff score
```

## What We Are Building

We are building a preprocessing layer:

- Input: CSV with a text column.
- Output: same rows, same IDs, same labels, plus `privatized_text`.
- Audit: JSON file explaining every transformation.
- Metrics: local proxy metrics for privacy gain and utility retention.

The real privacy adversary is broader than PII lookup. The method should reduce
signals useful for authorship identification while preserving cues useful for
hate-speech detection.

## What We Are Not Building First

- A production hate speech classifier.
- A legal decision system.
- An automated takedown/moderation system.
- A system that requires an external LLM API.
- A disability-only educational dashboard as the primary product.

## Judging Fit

The project should demonstrate:

- Runnable public code.
- Practical deployability.
- Privacy preservation.
- Hate-speech utility retention.
- Explainability and auditability.
- Rights-aware framing: privacy, free expression, non-discrimination, and human
  oversight.

The public leaderboard is only one signal. A strong submission must also show:

- problem understanding and tradeoff reasoning
- human-rights-centered design
- working, reusable, packaged code
- transparent limitations and follow-up plan
- practical deployability, not just a report

## Human-Rights Acceptance Criteria

The tool must be framed and tested as a privacy-preserving preprocessing layer,
not an automated takedown or legal classification system.

It should pass these legal-design checks:

- It does not equate offensive, insulting, vulgar, shocking, political,
  satirical, or public-interest speech with hate speech by default.
- It preserves target/action/negation/modality cues so downstream HSD systems do
  not miss threats, exclusion, dehumanisation, or vilification aimed at
  vulnerable or historically targeted groups.
- It treats missing speaker, recipient, audience, and social-context data as
  uncertainty, not as permission to make a definitive legal conclusion.
- It keeps row-level reasons, typed placeholders, manifests, hashes, and metrics
  available for audit.
- It identifies where human reviewers must step in: high-risk protected-group
  targeting, threats, large semantic drift, uncertain context, and any
  moderation consequence beyond dataset anonymisation.

See `docs/human_rights_legal_test_plan.md` for the detailed ECtHR,
Framework Convention, and HUDERIA mapping.

## Webinar Method Notes

- Presidio-style entity redaction is not enough on its own.
- DPMLM-style rewriting is promising but complex and parameter-sensitive.
- Generic LLM prompting is weak; any LLM use should be specialized, constrained,
  and evaluated.
- Useful privacy evaluation should include authorship-risk reduction when an
  author column is available.

## Timeline From Webinar

- 2026-06-15: starter kit and official development dataset expected.
- 2026-06-17: hackathon begins.
- 2026-06-18 afternoon: second dataset expected.
- 2026-06-18 end of day: final code/system due.
- 2026-06-19: final pitches and winners.
