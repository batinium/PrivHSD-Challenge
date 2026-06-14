# Review-Safe Statement Layer

## Concept

Add an optional reviewer-facing layer that rewrites protected rows into
non-traceable, normalized statements for the review portal.

The core pipeline still produces the exact protected CSV for challenge scoring
and reproducible audit. The reviewer portal gets a safer view:

```text
raw row
  -> deterministic privacy pipeline
  -> exact protected output for scoring/submission
  -> review-safe statement for human review
```

The goal is not to let an LLM decide hate speech. The goal is to reduce author
traceability for reviewers while preserving the hate-speech-relevant context
needed for assessment.

## Reviewer Experience

Use progressive disclosure:

1. Default: show a review-safe statement.
2. Evidence: show structured cue chips, such as target group, harm action,
   negation, quote/reporting context, and privacy transformations.
3. Inspect: allow the reviewer to open mechanically protected text when needed.
4. Escalate: keep raw/original text outside ordinary review. Raw access should
   require a separate trusted role or local operator.

Example:

```text
Review-safe statement:
A user says Muslims should be excluded from a location.

Evidence chips:
Target group: Muslims
Harm cue: exclusion
Context: direct statement
Privacy changes: person removed, email removed, location generalized

Inspectable protected text:
[PERSON] from [ORG] says Muslims should be kicked out of [LOCATION].
```

## LLM Role

Use a local LLM only as a constrained paraphrase and context-preservation
assistant.

Input should be protected text plus audit/cue data, not author IDs or raw
metadata. Output should be schema-checked JSON, for example:

```json
{
  "review_safe_statement": "A user says Muslims should be excluded from a location.",
  "target_group_preserved": true,
  "harm_action_preserved": true,
  "negation_preserved": true,
  "quote_or_reporting_preserved": false,
  "pii_removed": true,
  "needs_human_escalation": true,
  "reason_codes": ["protected_group", "exclusion", "location_generalized"]
}
```

## Guardrails

- Keep the LLM local-only.
- Do not send full raw CSVs or author IDs to the LLM.
- Run PII/residual leakage checks on the generated review-safe statement.
- Check target/action/negation/quote/reporting cue retention against the
  protected text.
- Treat the rewrite as a review surface, not the authoritative record.
- Fall back to protected text plus escalation flags when the rewrite loses
  legally relevant context.
- Store reviewer artifacts by hashed case IDs only.

## Why This Is Innovative

Reviewers often do not need author-traceable text to assess harm. A
cue-preserving review statement can keep the legally relevant hate-speech signal
while stripping identity, style, punctuation, metadata, and unusual wording that
could expose the author.

The system becomes:

```text
privacy-preserving preprocessing
  + cue-preserving context checks
  + reviewer-safe paraphrase
  + progressive disclosure
```

This is stronger than plain PII redaction because it addresses doxxing and
authorship risk in the human review workflow itself.

## Open Questions

- How much target detail should the default statement expose?
- Should protected group names remain literal or sometimes be categorized?
- Which rows should skip paraphrasing and go straight to protected-text review?
- Should the review-safe statement be cached, regenerated per reviewer session,
  or generated once per processed result?
- What minimum cue-retention score should be required before showing a rewrite?
