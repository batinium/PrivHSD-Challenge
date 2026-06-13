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

The webinar clarified that this is a text-to-text privatization challenge. The
official evaluator benchmarks the privatized dataset with transformer-based
utility/privacy scoring and returns a tradeoff score, roughly on a negative to
positive scale. A strong leaderboard score matters, but it is not the only
judging signal.

## What We Are Building

We are building a preprocessing layer:

- Input: CSV with a text column.
- Output: same rows, same IDs, same labels, and either an added
  `privatized_text` column for local audit or text replaced in place for an
  exact-format submission.
- Audit: JSON file explaining every transformation.
- Metrics: local proxy metrics for privacy gain and utility retention.

The real privacy adversary is broader than PII lookup. The method should reduce
signals useful for authorship identification while preserving cues useful for
hate-speech detection.

The intended public artifact is a runnable system, not a one-off notebook:

- public working code that a judge can install and run;
- packaged CLI/API behavior, ideally as a Python package;
- exact-format CSV output for the official evaluator;
- a public-facing UI or workbench that makes the backend testable;
- reproducible manifests and audit reports;
- clear explanation of what was changed and why.

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
- Lightweight enough processing for dataset-scale use.
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

See `docs/challenge/human_rights_legal_test_plan.md` for the detailed ECtHR,
Framework Convention, and HUDERIA mapping.

## Webinar Method Notes

- Presidio-style entity redaction is not enough on its own.
- Simple named-entity anonymization can produce poor tradeoffs because privacy
  in text includes more than names and contact details.
- DPMLM-style rewriting is promising but complex and parameter-sensitive.
- Generic LLM prompting is weak; any LLM use should be specialized,
  constrained, reproducible, and evaluated behind reranking.
- Large model calls on every row are risky for scale, cost, privacy, and
  explainability.
- Useful privacy evaluation should include authorship-risk reduction when an
  author column is available.
- Differential privacy is a plausible foundation, but not required. The method
  still needs empirical tradeoff evidence.

## Timeline From Webinar

- 2026-06-15: starter kit and official development dataset expected.
- 2026-06-15 onward: request team credentials for the challenge leaderboard.
- 2026-06-17: hackathon begins.
- 2026-06-18 afternoon: second dataset expected.
- 2026-06-18 end of day: final code/system due.
- 2026-06-19: final pitches and winners.

See `docs/challenge/webinar_alignment.md` for the current deliverable focus.
