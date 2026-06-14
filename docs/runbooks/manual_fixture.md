# Manual Fixture Runbook

Status: active
Owner area: synthetic/manual fixtures
Last verified: 2026-06-14
Primary code: `tests/fixtures/manual_privacy_expectations.csv`,
`contextsafe_hsd/pipeline.py`, `contextsafe_hsd/cue_checks.py`

Use this when checking hand-authored examples and expected GUI behavior.

## Purpose

The manual fixture exercises examples that are easy to inspect by eye:

- direct identifiers;
- quasi identifiers;
- target-group terms that must remain visible;
- hostile action, negation, modality, quotation, and counterspeech cues;
- author-style artifacts.

## Exact-Format Check

```bash
contextsafe-hsd create-submission \
  --input tests/fixtures/manual_privacy_expectations.csv \
  --output data/outputs/manual_privacy_expectations.auto.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --metric-depth fast \
  --manifest data/outputs/manual_privacy_expectations.auto.manifest.json

contextsafe-hsd validate-submission \
  --source tests/fixtures/manual_privacy_expectations.csv \
  --submission data/outputs/manual_privacy_expectations.auto.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/manual_privacy_expectations.auto.validation.json
```

## Review Points

- Identifiers should become typed placeholders.
- Protected target words should remain available for HSD review.
- Output should avoid broad target generalization in the default path.
- The exact-format command should keep the fixture's original columns and row
  order; no `privatized_text` helper column should appear when `--replace-text`
  is used.
- The workbench should show changed spans, protected spans, warning codes,
  provider/model status, and downloadable audit artifacts.
