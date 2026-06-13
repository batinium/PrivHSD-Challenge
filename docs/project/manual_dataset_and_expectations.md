# Manual Privacy Expectations

Date: 2026-06-13

This guide explains the manual fixture at
`tests/fixtures/manual_privacy_expectations.csv`. Use it for demos, GUI checks,
and judge questions about what the system should mask, what it should preserve,
and how to test author re-identification risk.

## What The Fixture Covers

The fixture has 18 synthetic rows with repeated `author` values. It covers:

- direct identifiers: names, handles, email, phone, URL, IP, case/reference IDs;
- quasi-identifiers: age, date, city, school, organization, author style;
- HSD cues: protected targets, exclusion, deportation, threat/action words;
- legal/context cues: negation, counterspeech, quotation/reporting, benign
  near-matches, no-PII hate rows, and no-PII non-hate rows;
- known stress gaps: obfuscated contact information and short names in threat
  contexts.

Each row includes:

- `expression_context`: the speech context to preserve, such as
  `counterspeech`, `reported_hate`, `benign_public_discussion`,
  `targeted_hate_claim`, or `threat_documentation`;
- `expression_protection`: the free-expression or victim-protection failure
  mode to avoid, such as `avoid_false_hate`, `avoid_false_endorsement`,
  `preserve_benign_context`, or `preserve_hsd_evidence`;
- `expected_min_placeholders`: the minimum placeholder types we expect in a
  strong output;
- `expected_preserve_terms`: words or phrases that should stay readable;
- `overmask_if_lost`: terms whose loss probably means the output damaged HSD
  meaning or legal context;
- `notes`: the reason the row exists.

## Marking Freedom Of Expression

Do not mark freedom of expression as a single legal ground-truth label like
`free_speech=true`. A short dataset row usually does not contain enough speaker,
audience, intent, jurisdiction, public-interest, or harm context to make a real
Article 10 decision.

Instead, mark the row-level expression risk:

- `avoid_false_hate`: lawful or benign speech could be made to look hateful if
  negation, topic, or benign context is erased;
- `avoid_false_endorsement`: quoted, reported, or counterspeech hate could be
  converted into apparent endorsement;
- `preserve_benign_context`: privacy masking should not rewrite a non-hate
  private-detail row into something semantically different;
- `preserve_hsd_evidence`: vulnerable-group target/action evidence must remain
  available for downstream hate-speech detection;
- `avoid_erasing_threat_evidence`: threat/action words are legally and
  operationally important and must not disappear.

That gives us a practical test: the privatized text should protect privacy
while preserving the cues needed for a human or downstream model to tell
counterspeech, reporting, benign speech, and targeted hate apart.

## Run It Through The CLI

For audit-style output with a `privatized_text` helper column:

```bash
.venv/bin/python -m privhsd.cli anonymize \
  --input tests/fixtures/manual_privacy_expectations.csv \
  --output data/outputs/manual_privacy_expectations.auto.csv \
  --text-col text \
  --id-col id \
  --output-col privatized_text \
  --mode auto \
  --metric-depth fast \
  --audit data/outputs/manual_privacy_expectations.auto.audit.json
```

Then check cue retention:

```bash
.venv/bin/python -m privhsd.cli check-hsd-cues \
  --input data/outputs/manual_privacy_expectations.auto.csv \
  --text-col text \
  --privatized-col privatized_text \
  --id-col id \
  --output data/outputs/manual_privacy_expectations.auto.cue_checks.json
```

For exact-format behavior, use `create-submission --replace-text`:

```bash
.venv/bin/python -m privhsd.cli create-submission \
  --input tests/fixtures/manual_privacy_expectations.csv \
  --output data/outputs/manual_privacy_expectations.exact.auto.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode auto \
  --metric-depth fast \
  --manifest data/outputs/manual_privacy_expectations.exact.auto.manifest.json
```

## What Good Output Looks Like

Good masking:

- direct identifiers become typed placeholders such as `[PERSON]`, `[EMAIL]`,
  `[USER]`, `[PHONE]`, `[URL]`, `[ID]`, `[DATE]`, `[AGE]`, `[LOCATION]`, or
  `[ORG]`;
- target-group and HSD evidence remains readable in `balanced` and `auto`
  modes, for example `refugees`, `women`, `Muslims`, `black people`,
  `disabled students`, `should leave`, `deported`, `attack`, `threats`, `not`;
- quotation, reporting, counterspeech, and negation remain understandable;
- rows with no direct or quasi identifiers are mostly unchanged except for
  optional style normalization;
- exact-format output preserves row count, row order, column order, IDs,
  labels, source/split fields, and author metadata.

Too little masking:

- names, emails, handles, phone numbers, URLs, IP addresses, case IDs, exact
  dates, schools, cities, or stacked quasi-identifiers survive;
- author metadata values appear in the text;
- repeated style markers remain strong enough that a local author classifier
  can still predict the author much better than chance.

Too much masking:

- target groups disappear in `balanced` or `auto` mode;
- action, negation, modality, or reporting cues disappear;
- a row with no identifiers is rewritten heavily;
- the output becomes mostly placeholders;
- the HSD label would no longer make sense to a human reviewer.

The practical local thresholds are:

- residual direct identifiers should be zero or explicitly queued for review;
- `target_cue_retention` and `utility_cue_retention` should be `1.0` for rows
  with explicit cues;
- warning codes such as `target_cue_loss`, `low_character_utility_retention`,
  `high_placeholder_density`, or `changed_without_detected_sensitive_span`
  should be reviewed by row ID;
- exact submission validation must pass.

## How This Relates To Evaluation

The official evaluator is expected to score the uploaded privatized dataset as
a privacy/HSD utility tradeoff. It will not directly ask whether each row is
"free speech" or "not free speech". In practice:

- privacy scoring rewards reducing re-identification and author-identifying
  signals;
- utility scoring rewards keeping enough hate-speech detection signal for
  downstream models;
- a good rights-aware system avoids maximizing privacy by deleting meaning;
- our local expression markers provide evidence for the pitch and paper that
  we tested over-restriction, counterspeech, reporting, and benign speech.

So the local marking is not another official label. It is an audit layer that
helps us explain why the selected output is proportionate: it masks identifying
information, but it does not erase target/action/negation/reporting cues that
matter for legal and HSD interpretation.

For official exact-format uploads, do not add these manual columns unless the
starter kit explicitly allows them. The upload file should preserve the official
schema. Keep `expression_context` and `expression_protection` in private probes,
demo fixtures, and evidence reports.

## Current Auto Run Notes

The current `auto` run on 2026-06-13 wrote:

- `data/outputs/manual_privacy_expectations.auto.csv`
- `data/outputs/manual_privacy_expectations.auto.audit.json`
- `data/outputs/manual_privacy_expectations.auto.cue_checks.json`
- `data/outputs/manual_privacy_expectations.auto.author_risk.json`

Summary:

- identifiers: `36 -> 0`;
- direct identifiers: `22 -> 0`;
- quasi-identifiers: `14 -> 0`;
- target cue retention: `1.0`;
- utility cue retention: `1.0`;
- selected candidates: `provider_fusion_augmented=3`,
  `style_scrubbed=7`, `token_policy_candidate=8`;
- overmasking warnings: `high_mask_density=1`,
  `high_placeholder_density=2`, `low_character_utility_retention=1`.

Known issues from manual review:

- `M002` keeps `Omar Vale` in the privatized text even though the fast metric
  does not count it as a residual identifier.
- `M006` keeps `lina [at] example dot test`, so obfuscated email/contact
  detection still needs a patch.
- `M012` masks `Kill Alex` as `[PERSON]`, losing the threat verb `Kill`; this
  is an overmasking bug because the action cue is part of HSD meaning.
- Some token-policy outputs use broad `[ID]` placeholders where a demo output
  would be clearer with `[PERSON]`, `[EMAIL]`, `[USER]`, or `[DATE]`.

The author-risk run is also intentionally sobering: original author prediction
was `accuracy=1.0`, `macro_f1=1.0`, while privatized author prediction was
still `accuracy=0.8889`, `macro_f1=0.8857`. True-author confidence barely moved
from `0.4302` to `0.4267`. This means the current system reduces explicit
identifiers, but it should not be presented as strong writing-style
anonymization yet.

## What To Expect In The GUI

Open the workbench and use either the text or CSV view:

```bash
python launch.py
```

In the Text view, paste one row's `text` value. In default `balanced` mode you
should see:

- orange or placeholder-highlighted identifier replacements in the output;
- protected target cues highlighted or preserved;
- privacy gain, cue retention, text similarity, and residual-risk gauges;
- transformation rows with entity type, replacement, source, and offsets;
- warnings or review guidance when context is ambiguous.

Example expectation:

```text
My name is Lina Park, email lina.park@example.test, and @lina_watch said
refugees should leave Boston on Jan 4, 2025.
```

Expected output shape:

```text
My name is [PERSON], email [EMAIL], and [USER] said refugees should leave
[LOCATION] on [DATE].
```

Exact wording can vary by provider/model availability, but the important rule is
that `refugees should leave` remains while the person/contact/place/date signals
are masked.

In the CSV view, upload `tests/fixtures/manual_privacy_expectations.csv`, set
`Text Column` to `text`, set `ID Column` to `id`, and run `auto`. Disable
`Replace text column` if you want an audit CSV with both original `text` and
`privatized_text`. Enable it only when testing exact-format output.
The `expression_context` and `expression_protection` columns are manual audit
metadata; they should pass through unchanged and help you explain why a row is
an over-restriction, counterspeech, reporting, or victim-protection stress case.

## Author Re-Identification Answer

If the dataset includes an `author` or `author_id` column, there are two
different questions:

In current `auto` mode, the privatizer does not condition on the actual author
label. It only records whether author metadata is present as a routing/profile
signal. The separate reranking and audit commands can use `--author-col`
explicitly to measure or penalize authorship leakage.

1. **Is the author column itself visible?**
   If the output keeps an `author` column, then anyone with that CSV can read the
   author label directly. That is not reverse engineering; it is preserved
   metadata. Official challenge submissions may require preserving metadata. For
   public data sharing, drop or separately pseudonymize author metadata if rules
   allow it.

2. **Can the author be inferred from writing style alone?**
   This is what `evaluate-author-risk` measures. It trains a lightweight
   character n-gram author classifier on original text and compares how well it
   predicts authors from original vs privatized text.

Run it on the manual fixture after creating `privatized_text`:

```bash
.venv/bin/python -m privhsd.cli evaluate-author-risk \
  --input data/outputs/manual_privacy_expectations.auto.csv \
  --text-col text \
  --privatized-col privatized_text \
  --author-col author \
  --id-col id \
  --label-col label \
  --test-size 0.5 \
  --output data/outputs/manual_privacy_expectations.auto.author_risk.json
```

What to report:

- original author accuracy, macro-F1, and true-author confidence;
- privatized author accuracy, macro-F1, and true-author confidence;
- `privacy_gain_macro_f1` and `privacy_gain_true_author_confidence`;
- `residual_high_risk_rows`, which are row IDs where the author is still
  predictable after privatization.

Good author-risk behavior means the privatized score drops toward chance. With
three authors, chance accuracy is about `0.333`. It does not prove anonymity,
but it is defensible evidence that text-only author signal was reduced.

Limits to state clearly:

- if every author appears only once, author-risk evaluation should skip;
- if topics are unique to authors, text may remain linkable even after style
  masking;
- if official rules require preserving `author_id`, we can reduce text-based
  authorship leakage but cannot claim the released CSV hides the author label;
- this local adversary is a proxy, not the official privacy evaluator.
