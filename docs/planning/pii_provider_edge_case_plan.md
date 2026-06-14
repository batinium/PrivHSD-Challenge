# PII Provider And Edge-Case Implementation Plan

Status: active
Owner area: planning handoff for deterministic masking and optional PII providers
Last verified: 2026-06-14
Primary code: `privhsd/detectors.py`, `privhsd/pipeline.py`,
`privhsd/span_providers/`, `privhsd/auto/`, `tests/fixtures/`

This file is an implementation handoff for agents working on PII provider
selection and the current edge-case gaps. It records the benchmark conclusion
for HydroXai PII Masker and gives concrete next tasks.

Status note: the deterministic edge-case fixes for obfuscated email/contact
forms, reported-person contexts, short-name threat cue preservation, and
conservative alias handling are now implemented and covered by
`tests/test_pipeline.py` plus `tests/test_synthetic_pii_stress.py`. The
HydroXai and provider-benchmark sections remain historical/proposed.

## Decision

Do not move HydroXai PII Masker into the default pipeline.

HydroXai can remain a research-only experiment if an agent wants to build a
local provider wrapper, but it should not become the official or default
provider until packaging, license, offset handling, and edge-case performance
are resolved.

Current engineering policy:

1. Preserve deterministic coverage for the known edge cases.
2. Keep filtered Presidio as the stronger optional provider, routed
   conservatively.
3. Keep all optional provider output behind fusion, cue protection, candidate
   scoring, and exact-format validation.
4. Add a small provider benchmark command or runbook only if future provider
   changes need comparable evidence.

## Historical Benchmark Evidence

The following generated reports predate the later deterministic detector
tuning. They still explain why HydroXai should not be promoted, but they should
not be read as the current manual-fixture detector status.

Generated reports:

- `data/outputs/hydroxai_pii_provider_benchmark.manual.json`
- `data/outputs/hydroxai_pii_provider_benchmark.manual.csv`
- `data/outputs/hydroxai_pii_provider_benchmark.public_dev_sample1000.json`
- `data/outputs/hydroxai_pii_provider_benchmark.public_dev_sample1000.deltas.csv`

These files are ignored generated evidence. Keep them out of durable commits
unless the repository policy changes.

Manual fixture: `tests/fixtures/manual_privacy_expectations.csv`

| Variant | Residual identifiers | Missing expected edge rows | Critical HSD cue-loss rows | Notes |
| --- | ---: | ---: | ---: | --- |
| `balanced` | 0 | 2 | 1 | Strong baseline but misses obfuscated contact/person cases and loses `Kill` in one synthetic threat row. |
| `presidio_augmented` | 1 | 2 | 0 | Fixes the `Kill` cue loss by rejecting the broad person span, but leaves a direct identifier in that row. |
| `hydroxai_augmented` | 0 | 2 | 1 | Adds one useful person/user mask but does not fix the hard cases. |
| `presidio_plus_hydroxai` | 1 | 2 | 0 | Same practical outcome as Presidio for the fixture, with no clear net win. |

Public-dev fixed sample: 1,000 rows, seed `20260613`

| Variant | Residual identifiers after | Placeholder total | Changed cells | Privacy-improved rows vs balanced | Extra overmask warning rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| `balanced` | 1 | 267 | 185 | n/a | n/a |
| `presidio_augmented` | 0 | 533 | 317 | 1 | 106 |
| `hydroxai_augmented` | 1 | 269 | 189 | 0 | 3 |
| `presidio_plus_hydroxai` | 0 | 525 | 317 | 1 | 106 |

Provider output summary on the public-dev sample:

| Provider | Rows with accepted spans | Accepted span types |
| --- | ---: | --- |
| Presidio | 210 | `DATE=37`, `LOCATION=131`, `PERSON=148` |
| HydroXai | 58 | `IDENTIFIER=1`, `PERSON=15`, `USER=52` |

HydroXai did not reduce residual identifiers on the public sample. It also
changed some rows in ways that reduced the number of existing deterministic
placeholders. That means it can interfere with current masking rather than only
adding useful spans.

## HydroXai Integration Risks

The benchmark used `hydroxai/pii_model_weight` with reconstructed local
artifacts because the Hugging Face model repository did not expose a normal
Transformers model package.

Observed issues:

- `hydroxai/pii_model_weight` exposed only weights in the model repo at the
  time of verification.
- `hydroxai/pii_model_longtransfomer_version` also lacked a normal
  `config.json` model package at the time of verification.
- The model pages did not expose a model card/license in the page view checked.
- The GitHub repository advertises MIT for code, but that is not enough to
  settle the model-weight license for official use.
- Raw token-classification output needs careful offset grouping. The README
  masking function is not offset-safe enough for our fusion pipeline.
- The model is trained around labels like `NAME_STUDENT`, `URL_PERSONAL`,
  `ID_NUM`, and `USERNAME`; that label set does not cover our full problem
  space, especially locations, durable dates, organizations, and HSD-specific
  cue preservation.
- On synthetic edge rows it missed the obfuscated email and did not solve the
  short-name threat case.
- On the public sample it accepted spans in only 58 of 1,000 rows and produced
  no proxy privacy improvement over `balanced`.

If an agent still implements a HydroXai provider, it must be experimental:

- Put it behind an explicit provider name such as `hydroxai_pii`.
- Keep it disabled by default.
- Require a local model directory path, or require explicit
  `--allow-model-download` plus a clear status record.
- Do not make it depend on third-party reconstructed artifacts without a
  license note and reproducibility note.
- Emit `SpanCandidate` objects only; never directly use HydroXai's masked text.
- Store no raw text in provider status or benchmark summaries.
- Add tests for token offset grouping before using it in `auto`.

## Recommended Implementation Tasks

### Task 1: Obfuscated Email Detection

Status: implemented as of 2026-06-14. Keep this section as regression context.

Historical problem:

The deterministic detector caught normal email addresses but missed synthetic
obfuscated contacts such as `lina [at] example dot test` in row `M006`.

Implementation target:

- Add a deterministic high-precision email detector for obfuscated email forms.
- Prefer a small helper function over a single unreadable regex if clarity is
  better.
- Emit entity type `EMAIL`.
- Use replacement `[EMAIL]`.
- Source should be distinguishable, for example `regex_obfuscated_email` or
  `obfuscated_email`.
- Score should be at least as high as normal direct regex spans, for example
  `0.86`, because this is a direct identifier.

Forms to handle:

- `name [at] example dot test`
- `name (at) example (dot) org`
- `name at example dot com` when contact context is nearby
- `name AT example DOT net`
- `first.last at sub domain dot org`
- `name_at_domain_dot_com` only if the implementation can avoid broad false
  positives; otherwise leave this for a later pass.

Suggested shape:

```text
local-part + at-token + domain-fragments + dot-token + tld
```

Suggested guardrails:

- Require at least one `at` marker and one `dot` marker.
- Require a local part with at least two alphanumeric characters.
- Require a final TLD-like fragment of at least two alphabetic characters.
- Allow whitespace and bracket punctuation around `at` and `dot`.
- Avoid matching target/action/negation terms as the local part.
- Avoid matching long sentence fragments. Cap the whole matched span length,
  for example at 120 characters.
- If supporting bare `at` and `dot`, prefer requiring a nearby context cue:
  `email`, `e-mail`, `mail`, `reach`, `contact`, `dm`, `message`, `send to`,
  or `write to`.

Files likely to change:

- `privhsd/detectors.py`
- `tests/test_pipeline.py`
- `tests/test_synthetic_pii_stress.py` or
  `tests/fixtures/manual_privacy_expectations.csv`

Acceptance tests:

- `M006` should contain `[EMAIL]` after privatization.
- Normal target/action terms must remain unchanged.
- A benign sentence containing `at` and `dot` as ordinary words should not
  produce `[EMAIL]`.
- Normal email behavior must still pass existing tests.

Minimum focused command:

```bash
python -m pytest tests/test_pipeline.py tests/test_synthetic_pii_stress.py -q
```

### Task 2: Reported/Counterspeech Person Names

Status: implemented as of 2026-06-14. Keep this section as regression context.

Historical problem:

Row `M002` contains a reported/counterspeech context with a person name. The
old baseline left the expected person placeholder missing.

Implementation target:

- Add or refine context-person patterns so reported-person constructions are
  masked without flattening the quote/counterspeech meaning.
- Keep target groups, quote/reporting words, negation, and action cues intact.

Candidate patterns to support:

- `I reported NAME because ...`
- `we reported NAME because ...`
- `reported NAME for ...`
- `reported NAME after ...`
- `NAME quoted ...`
- `NAME posted ...`
- `NAME wrote ...`

Guardrails:

- Capture only the name span, not the reporting verb or following quote.
- Preserve words like `reported`, `quoted`, `replied`, `do not`, `not`, and
  target-group terms.
- Reuse `trim_context_span()` so connector words are not included.
- Reject spans that are target-group terms.
- Do not introduce a broad all-titlecase phrase masker; it will overmask HSD
  evidence in public data.

Acceptance tests:

- `M002` should include `[PERSON]`.
- The output should still include the protected terms listed in the fixture:
  `Muslims`, `should leave`, `do not`, and `attack`.
- No new target-cue loss should appear in `check-hsd-cues` for the manual
  fixture.

### Task 3: Short-Name Threat Context Without Cue Loss

Status: implemented as of 2026-06-14. Keep this section as regression context.

Historical problem:

Row `M012` risked masking `Kill Alex` as a single `PERSON` span in the
deterministic baseline, which removed the HSD action cue `Kill`.

Implementation target:

- Preserve the action/threat cue.
- Mask only the person name after the action cue.
- Expected output shape should be equivalent to:

```text
Kill [PERSON] was posted ...
```

Do not require that exact punctuation or spacing, but the action term must
remain visible and the person name must be masked.

Likely root cause:

- A generic titlecase context-person pattern can capture a phrase before
  `posted`.
- `trim_context_span(... require_titlecase=True)` can keep a leading titlecase
  action word, so `Kill Alex` survives as one person span.

Recommended fix:

- Add a helper that trims leading HSD action words from candidate person spans.
- Apply it to context-person captures before the span is emitted.
- Use the existing utility/action term resources rather than hard-coding only
  `kill`.
- Only trim when the candidate has at least two words and the first word is an
  action/threat term.
- After trimming, keep the remaining titlecase name if it is non-empty.

Alternative fix:

- Add a more specific threat-name context pattern that captures only the name
  after the action term, and lower the priority or reject the broader
  `ACTION NAME` candidate.

The helper approach is safer because it prevents the same bug in other generic
context-person patterns.

Acceptance tests:

- A test sentence modeled on `M012` should keep `Kill` and mask only the name.
- The manual fixture should report zero critical cue-loss rows.
- `target_cue_retention` and `utility_cue_retention` should stay at `1.0` on
  the manual fixture.

### Task 4: Alias And Platform Handle Coverage

Status: implemented for the documented high-precision forms as of 2026-06-14.
Keep this section as regression context and as guidance for future expansion.

Historical problem:

The system handled some alias forms, but provider benchmarks showed that
social/contact identifiers remain an important class. These should be handled
deterministically where high precision is possible.

Implementation target:

- Expand alias/handle context patterns conservatively.
- Emit `ALIAS` or `USER` depending on the shape:
  - leading `@...` should be `USER`;
  - platform/context aliases without `@` can be `ALIAS`.

High-precision context cues:

- `alias`
- `aka`
- `known as`
- `goes by`
- `handle`
- `username`
- `user name`
- `Telegram`
- `Signal`
- `Discord`
- `WhatsApp`
- `Skype`
- `TikTok`
- `Instagram`

Candidate token shape:

- 3 to 64 characters;
- starts with a letter, digit, or `@`;
- may contain letters, digits, `.`, `_`, or `-`;
- must contain at least one digit, underscore, dot, dash, or be preceded by a
  strong alias cue.

Guardrails:

- Do not mask target-group terms.
- Do not mask ordinary words after platform names unless the token has
  handle-like shape or a strong cue such as `alias`.
- Do not mask HSD action/negation/reporting cues as aliases.

Acceptance tests:

- `Telegram alias night_owl77` stays masked.
- Add tests for `handle quiet.reader` and `Discord user qa-team77`.
- Add a benign sentence with a platform name and no handle; it should not add
  a placeholder.

### Task 5: Provider Fusion Should Not Replace Deterministic Strength

Status: implemented in the current `privatize_text()` provider-candidate path
and covered by span-provider/auto tests. Keep this section as a regression
policy.

Problem:

HydroXai candidate spans sometimes caused fewer placeholders than the
deterministic baseline on changed rows. Optional providers must add evidence or
support an alternate candidate; they should not weaken high-confidence direct
identifier masking.

Implementation target:

- Ensure provider-augmented candidates always include deterministic spans.
  This is already the intended behavior in `privatize_text()`, but add tests
  for provider overlaps that can otherwise change outputs unexpectedly.
- If a provider emits a candidate overlapping a deterministic direct identifier
  with a lower-priority or partial span, deterministic should win.
- Preserve high-confidence direct spans from regex/context detectors unless a
  protected HSD cue split is explicitly required.

Suggested tests:

- Deterministic `[USER]` span plus provider partial username span should still
  produce one clean `[USER]`.
- Provider person span overlapping `Kill Alex` should not force loss of `Kill`.
- Provider span that overlaps a target-group term should be rejected or trimmed
  according to existing cue-preservation rules.

### Task 6: Conservative Presidio Routing

Status: implemented as the current auto routing policy. Presidio remains
optional, discovered lazily, and routed through fusion/scoring/fallback.

Problem:

Presidio is more useful than HydroXai in the benchmark, but it also adds many
extra masks. On the 1,000-row sample it fixed the one residual proxy identifier
but added 106 extra overmask-warning rows.

Implementation target:

- Keep Presidio optional and routed only to rows with cheap residual risk.
- Do not run Presidio blindly on every row in the official path unless an
  official score proves it is worth the extra masking.
- Prefer using Presidio when baseline metrics or cheap profile show:
  - residual direct identifier;
  - residual quasi identifier;
  - person ambiguity in a context-person pattern;
  - durable location/date context;
  - reported-person context not covered by deterministic rules.

Guardrails:

- Preserve target/action/negation/reporting cues.
- Keep `rejected_counts_by_reason` in audits.
- Keep raw text out of provider status.
- Add row IDs, not raw examples, to review queues.

Acceptance tests:

- Missing Presidio dependency should not fail exact output.
- Presidio should load once per run in `auto`.
- Presidio should not reduce utility-cue or target-cue retention on manual
  fixtures.

### Task 7: First-Class PII Provider Benchmark Command

Status: not implemented. This remains proposed future work.

Problem:

The HydroXai benchmark was run with one-off scripts. Future agents should have
a reusable command so provider changes can be compared without pasting scripts
into chat.

Implementation target:

Add a CLI command such as:

```bash
python -m privhsd.cli benchmark-pii-providers \
  --input tests/fixtures/manual_privacy_expectations.csv \
  --text-col text \
  --id-col id \
  --expected-placeholders-col expected_min_placeholders \
  --preserve-terms-col expected_preserve_terms \
  --critical-terms-col overmask_if_lost \
  --provider balanced \
  --provider presidio \
  --provider hydroxai_pii \
  --output data/outputs/pii_provider_benchmark.manual.json
```

Suggested behavior:

- Always include `balanced`.
- Compare provider-augmented candidates against `balanced`.
- Record aggregate metrics and row IDs.
- Do not include raw text by default.
- Add an explicit `--include-text-debug` flag only for ignored local reports.
- Support `--sample-size` and `--random-state` for public-dev sampling.
- Record provider status and load counts.
- Record changed-vs-balanced rows, privacy-improved rows, privacy-regressed
  rows, cue-regressed rows, and extra-overmask-warning rows.

Suggested code placement:

- `privhsd/provider_benchmark.py`
- CLI registration in `privhsd/cli.py`
- Tests in `tests/test_provider_benchmark.py`

Acceptance tests:

- Manual fixture benchmark runs without optional providers installed.
- Missing provider is reported as unavailable, not fatal.
- JSON output has no raw text unless `--include-text-debug` is set.
- Public-dev sampling is deterministic for a fixed seed.

## Regression Gate For Existing Edge Fixes

When changing deterministic detectors, run:

```bash
python -m pytest tests/test_pipeline.py tests/test_span_providers.py tests/test_synthetic_pii_stress.py -q
python -m privhsd.cli anonymize \
  --input tests/fixtures/manual_privacy_expectations.csv \
  --output data/outputs/manual_privacy_expectations.edge_fixes.csv \
  --text-col text \
  --id-col id \
  --output-col privatized_text \
  --mode auto \
  --metric-depth fast \
  --audit data/outputs/manual_privacy_expectations.edge_fixes.audit.json
python -m privhsd.cli check-hsd-cues \
  --input data/outputs/manual_privacy_expectations.edge_fixes.csv \
  --text-col text \
  --privatized-col privatized_text \
  --id-col id \
  --output data/outputs/manual_privacy_expectations.edge_fixes.cue_checks.json
```

Expected manual-fixture outcome:

- `M002` includes a person placeholder while preserving reporting and
  counterspeech cues.
- `M006` includes a person placeholder, email placeholder, and alias/user
  placeholder.
- `M012` preserves `Kill` and masks only the person/location.
- Critical HSD cue-loss rows should be zero.
- Target-cue retention should remain `1.0`.
- Utility-cue retention should remain `1.0`.

Before changing the official path, also run:

```bash
python -m pytest -q
python -m privhsd.cli validate-submission \
  --source INPUT.csv \
  --submission OUTPUT.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/OUTPUT.validation.json
```

When metadata columns are available, add source regression:

```bash
python -m privhsd.cli source-regression-report \
  --original INPUT.csv \
  --protected OUTPUT.csv \
  --original-text-col text \
  --protected-text-col text \
  --id-col id \
  --group-col source \
  --group-col label \
  --group-col split \
  --output data/outputs/OUTPUT.source_regression.json
```

## Non-Goals

- Do not rewrite full sentences as the default privacy mechanism.
- Do not use HydroXai masked text directly as final output.
- Do not treat external PII providers as HSD-aware.
- Do not mask target-group evidence just because a provider labels it as a
  person, location, or organization.
- Do not paste raw public-dev or official examples into durable docs.
- Do not add model downloads to the default official path.

## Handoff Summary

Recommended next agent assignment:

1. Preserve the implemented deterministic edge-case regressions.
2. Add provider-level benchmarking only if future provider changes need
   comparable evidence.
3. Keep HydroXai research-only unless packaging, license, offset grouping, and
   benchmark performance change materially.
4. Continue using optional providers only through fusion, cue protection,
   candidate scoring, and exact-format validation.

Expected impact:

- Better edge-case privacy without adding broad overmasking.
- Better HSD cue preservation on threat/action rows.
- Less dependence on model/provider packaging.
- A cleaner story for evaluators: direct PII and quasi identifiers are masked,
  HSD evidence is deliberately preserved, and optional providers cannot override
  the safety gates.
