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

## Timeline From Webinar

- 2026-06-15: starter kit and official development dataset expected.
- 2026-06-17: hackathon begins.
- 2026-06-18 afternoon: second dataset expected.
- 2026-06-18 end of day: final code/system due.
- 2026-06-19: final pitches and winners.

