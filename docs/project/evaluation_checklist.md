# Evaluation Checklist

Date: 2026-06-12

Use this checklist to test whether the system protects identifiers without
destroying the evidence needed for hate-speech detection and human review.

## What To Record

For every manual or generated test row, record:

- expected privacy spans: names, handles, emails, phones, locations, schools,
  case IDs, ages, dates, URLs, and other direct or quasi identifiers;
- expected target spans: protected groups, slurs, nationality/origin terms,
  religion, race/ethnicity, gender/sexuality, disability, and age groups;
- expected utility cues: threat, exclusion, dehumanization, harassment,
  negation, quotation, reporting, counterspeech, sarcasm, emoji, and hashtags;
- expected mode behavior: `balanced` should preserve target-group meaning,
  while `privacy` may generalize target groups.

## Manual Stress Matrix

Cover these categories before trusting a new rule, model checkpoint, or demo
build:

| Category | Example pattern | Expected behavior |
| --- | --- | --- |
| Direct IDs | email, phone, URL, handle, IP, ticket/case ID | Always replace with typed placeholders. |
| Person names | titlecase, lowercase after "my name is", ASCII transliterations and diacritic variants | Replace the person span; do not eat surrounding target text. |
| Locations | city, country, neighborhood, street address, multiword place | Replace locations when used as places, especially near `in`, `near`, `from`, `leave`, or street suffixes. |
| Organizations | school, university, workplace, NGO, clinic | Replace when it can identify the person or source. |
| Dates and ages | exact dates, relative age statements, age plus location | Replace when identifying; retain broad chronology only when needed. |
| Target groups | plain group names, plural forms, hashtags, slurs, leetspeak, one-edit typos | Preserve in `balanced`; generalize in `privacy`; detect variants near hostile context. |
| Social style | emoji, sarcasm, hashtags, punctuation floods, mixed case | Preserve utility cues; do not let formatting hide identifiers. |
| Counterspeech | "I oppose people saying ...", quotes, reporting verbs | Preserve the distinction between endorsement and reporting. |
| No-PII offensive text | harmful claim with no personal identifiers | Avoid unnecessary masking in `balanced`. |
| Benign near-matches | common words that look like names or places | Avoid overmasking unless context makes them identifying. |

## Generated Stress Cases

Use the small LM Studio stress generator as a coverage probe first:

```bash
python scripts/generate_lm_studio_stress_cases.py \
  --endpoint http://172.21.96.1:1234/v1/chat/completions \
  --model gemma-4-e4b-uncensored-hauhaucs-aggressive \
  --batches 5 \
  --cases-per-batch 8 \
  --use-presidio
```

Inspect the report for `missing_expected_privacy_spans` and
`missing_expected_target_spans`. Promote a generated pattern into training only
after dedupe, label validation, source balancing, and token-action distribution
checks.

For a large challenge-oriented corpus, use the resumable one-row-per-request
generator:

```bash
python scripts/generate_lm_studio_challenge_corpus.py \
  --endpoint http://172.21.96.1:1234/v1/chat/completions \
  --model gemma-4-e4b-uncensored-hauhaucs-aggressive \
  --target-count 100000 \
  --temperature 0.8 \
  --heartbeat-every 25 \
  --output data/outputs/synthetic_challenge_corpus.csv \
  --errors data/outputs/synthetic_challenge_corpus.errors.jsonl \
  --report data/outputs/synthetic_challenge_corpus.report.json \
  --status data/outputs/synthetic_challenge_corpus.status.json
```

This CSV stores the prompt, raw model response, parsed row labels, expected
privacy/target annotations, local detector outputs, and weak token-action
labels. It is still synthetic and must be curated before training.

## Regression Gates

Run these before pushing detector or workbench changes:

```bash
python -m pytest tests/test_pipeline.py tests/test_synthetic_pii_stress.py -q
python -m pytest -q
```

For model or dataset changes, also rerun the source regression, cue-retention,
and external/unseen evaluation scripts used in the current roadmap.

## Lexicon Policy

Use broad stopword, name, and location libraries as candidate generators only.
Do not let them directly rewrite text without context filters, because broad
lexicons can create false positives and can remove HSD utility words such as
negation or modality. The deterministic layer should still decide whether a
candidate is privacy-sensitive in this task.
