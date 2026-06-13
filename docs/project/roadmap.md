# Roadmap

Date: 2026-06-13

## Mission

Build a local, auditable CSV-in/CSV-out privatization system for hate-speech
detection datasets. The user uploads or passes a CSV, selects the text column,
and downloads a CSV with the same rows, IDs, labels, metadata, and masked text.

The system must reduce direct identifiers, quasi-identifiers, and author-style
signals while preserving the evidence needed to understand hate speech directed
towards minorities and other protected or vulnerable groups. Target identity,
hostile action, threats, dehumanization, exclusion, negation, modality,
counterspeech, quotation, and public-interest context are utility cues. They
are not generic PII and must not be erased by default.

This remains a preprocessing and evidence system. It is not a legal decision
system, not a moderation/takedown system, and not a production hate-speech
classifier.

## Challenge Contract

The official path must always satisfy this contract before any upload:

- Input is a CSV with at least one text column.
- Output is a CSV with the same row count and row order.
- IDs, labels, source/split columns, and other metadata are preserved.
- For exact-format submissions, the original text column is replaced in place.
- For local audit, `privatized_text` may be added instead of replacing text.
- A manifest records command, commit, hashes, mode, metrics, and validation.
- Raw official examples, generated sensitive rows, model outputs, and reports
  stay under ignored `data/` paths and out of durable docs.

The default upload candidate remains `balanced` until official feedback proves
another path improves the privacy/utility tradeoff.

## Current Baseline

`balanced` is still the first official candidate:

- deterministic and local;
- exact-format output with row, ID, label, and metadata preservation;
- target terms preserved by default;
- strong source-aware local evidence;
- low dependency footprint and easy explanation to judges.

On `data/public_dev/recommended_merged.csv`, the latest balanced run produced:

| Rows | Changed text cells | Identifier detections | Direct IDs | Quasi IDs | Target cue retention | Utility cue retention | Character retention |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 159,668 | 26,941 | 40,304 -> 5 | 33,032 -> 4 | 7,272 -> 1 | 0.9999 | 0.9999 | 0.9721 |

Use this as the regression benchmark. New modules must beat or complement this
path without breaking exact-format output.

## Current Advisory Evidence

The transformer and rewrite paths are real, but they remain advisory until an
audited reranking path beats the deterministic baseline on official feedback.

| Path | Best current evidence | Role |
| --- | --- | --- |
| RoBERTa token policy | 30k action-balanced weak labels, dev macro F1 0.9061. | Advisory token-action model. |
| RoBERTa grouped K-fold | 5 grouped folds, macro F1 mean/std 0.8977 / 0.0152. | Anti-overfit evidence. |
| HateBERT token policy | External TweetEval `PROTECT_TARGET` F1 0.7964. | Domain-specific ensemble member. |
| RoBERTa + HateBERT ensemble | External TweetEval macro F1 0.8837, `PROTECT_TARGET` F1 0.8143. | Best current token-policy evidence. |
| Filtered Presidio reranking | Selected 6,085 Dynahate rows with local macro-F1 delta +0.0048 and utility-cue retention 1.0. | Strongest current alternate after `balanced`. |
| Local LLM candidates | Accepted some rewrites, but reranking selected very few. | Selective candidate/review path only. |
| DPMLM candidates | Protected-token path exists, but latest reranking selected 0 rows. | Research candidate path only. |

Preserve these results in the pitch and methodology, but do not let them turn
into unchecked direct output paths.

## Architecture Rule

Do not replace the pipeline with one model or one LLM prompt.

The intended architecture is:

```text
CSV
  -> profile and schema validation
  -> deterministic baseline candidate
  -> model/rule span providers
  -> span fusion and conflict policy
  -> candidate generation
  -> HSD cue and semantic drift validation
  -> row-local reranking
  -> exact-format CSV plus manifest/audit
```

The deterministic baseline is the safety floor. Models are span proposal,
uncertainty, review, or candidate-generation components unless a later audit
proves they are safe enough for direct use.

## Phase 0: Cleanup Before Expansion

The codebase is already large enough that adding every new tool directly into
the current modules will make the system hard to maintain. Do this cleanup
before adding GLiNER, scrubadub, weak supervision, rationale models, or new DP
paths.

### Cleanup Goals

- Keep the official `balanced` behavior stable.
- Make detector/model additions pluggable instead of one-off modules.
- Move source schemas, weak-label policies, and term inventories out of large
  Python files when they are data rather than logic.
- Delete or deprecate duplicated experiment paths only after tests prove the
  replacement path covers them.
- Keep optional dependencies optional. Base install should remain light.

### Proposed Module Boundaries

Create these package areas and migrate gradually:

```text
privhsd/span_providers/
  base.py                 SpanProvider protocol and provider result schema
  deterministic.py        Existing high-precision regex/context spans
  presidio.py             Filtered Presidio provider
  gliner.py               GLiNER provider
  scrubadub_provider.py   scrubadub provider
  llm_review.py           Structured local LLM span reviewer
  fusion.py               overlap, voting, calibration, conflict handling

privhsd/candidates/
  deterministic.py        balanced/privacy/style candidates
  dpmlm.py                protected-token DPMLM candidate path
  santext.py              SanText candidate path, if added
  local_llm.py            constrained local LLM candidate path
  token_policy.py         token-policy candidate application

privhsd/evaluation/
  pii_benchmarks.py       TAB and synthetic PII stress reports
  hsd_benchmarks.py       HateCheck/Hatemoji/Measuring Hate Speech reports
  semantic_drift.py       SBERT/BERTScore/classifier drift checks
  label_quality.py        cleanlab and weak-label diagnostics
```

This migration does not need to happen in one commit. The next agent should
first add the shared interfaces, then move one existing provider at a time.

### Hard-Coded Data Cleanup

- Move `TARGET_GROUP_TERMS`, action/utility cue lists, expected source labels,
  and source schema assumptions into versioned resource files such as
  `privhsd/resources/target_cues.toml`,
  `privhsd/resources/utility_cues.toml`, and
  `privhsd/resources/source_schemas.toml`.
- Keep high-precision direct identifier regexes in code: email, URL, phone,
  IP, handle, and ID-like patterns are logic.
- Do not add new handcrafted city, street, school, organization, or personal
  name dictionaries. Existing tiny location lists should be replaced by model
  span providers once provider tests pass.
- Keep protected-target terms as HSD cue policy, not as PII masking policy.
  They may be hand-curated only when backed by dataset fields, failure reports,
  or public HSD resources, and should live in resource files.

### CLI Cleanup

- Keep user-facing commands stable where possible.
- Group experimental commands in help text as `candidate-only` or `report-only`.
- Avoid adding a separate top-level CLI command for every provider. Prefer:

```bash
python -m privhsd.cli rerank-candidates \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --provider presidio \
  --provider gliner \
  --provider scrubadub \
  --audit data/outputs/INPUT.rerank.audit.json
```

- Existing commands can remain as compatibility wrappers until the new provider
  path is stable.

### Cleanup Acceptance Criteria

- `python -m pytest -q` passes.
- `balanced` output on representative fixtures is byte-for-byte unchanged.
- `create-submission --replace-text` and `validate-submission` still pass.
- No generated data, model weights, or official examples are committed.
- New provider interfaces have narrow tests before any external model is added.

## Phase 1: Span Provider Interface And Fusion

The next architectural step is a shared span proposal interface. This prevents
Presidio, GLiNER, scrubadub, regexes, token policy, and local LLM review from
becoming unrelated code paths.

### Provider Result Schema

Each provider should emit a normalized span candidate:

```text
start
end
text
entity_type              PERSON, LOCATION, ORG, EMAIL, USER, DATE, ID, etc.
privacy_class            direct_identifier | quasi_identifier | style | none
utility_class            hsd_target | hsd_action | negation | quote | none
provider                 regex | presidio | gliner | scrubadub | llm | token_policy
score
explanation_code
```

Only the final fusion layer should convert candidates into replacement spans.

### Fusion Policy

- Prefer direct identifiers when any high-precision provider detects them.
- Require stronger evidence for quasi-identifiers such as city, school,
  organization, date, or street-like phrases.
- Reject or downgrade spans that overlap protected HSD target/action/negation
  cues unless the row is in an explicit privacy mode.
- Preserve minority/protected-group target terms by default.
- Keep provider disagreement in the audit. Disagreement is review signal, not
  a silent failure.
- Calibrate thresholds per entity type. `PERSON` and `USER` should not share
  the same threshold as `LOCATION` or `DATE`.

### Fusion Acceptance Criteria

- Existing deterministic spans can be represented through the provider schema.
- Filtered Presidio behavior can be reproduced through the provider schema.
- Reranking can accept fused provider spans without knowing which model created
  them.
- Audit reports list accepted and rejected spans by provider and reason.

## Phase 2: PII And Quasi-Identifier Providers

Piiranha is excluded because its current license is not suitable for this
project. Do not add it as a dependency.

### Presidio As Orchestrator

Keep Presidio, but stop treating default Presidio as enough. Presidio should be
one provider and optionally a registry for custom recognizers.

Tasks:

- Move current filtered Presidio logic into `span_providers/presidio.py`.
- Keep existing filters: no `NRP`, no protected cue overlap, no transient dates,
  no obvious false person shapes.
- Add provider-specific audit fields for raw count, accepted count, rejected
  count, and rejection reasons.
- Keep Presidio optional under `.[presidio]`.

### GLiNER Provider

GLiNER is the primary replacement for manually coded city/street/name/school
combinations. It can run zero-shot and can later be fine-tuned.

Initial labels to request:

- `person`
- `online handle`
- `email address`
- `phone number`
- `street address`
- `city`
- `neighborhood`
- `school`
- `university`
- `organization`
- `date of birth`
- `case number`
- `student id`
- `government id`

Implementation notes:

- Add optional extra `gliner`.
- Map GLiNER labels into the shared entity taxonomy.
- Run with deterministic thresholds by entity type.
- Use GLiNER as candidate spans only. Do not directly replace output until
  fusion and cue checks accept the spans.
- Add a small synthetic fixture covering names, fictional streets, schools,
  handles, and organizations without adding name/city dictionaries.

Acceptance criteria:

- Improves recall on synthetic PII stress cases without reducing target/action
  cue retention.
- Does not mask protected group names such as nationalities, religions,
  gendered groups, sexual orientation terms, disability terms, or racialized
  target terms when they are HSD evidence.
- Produces provider-specific audit data.

### scrubadub Provider

scrubadub is a lightweight independent PII baseline. It should not replace the
pipeline, but it is useful for direct PII confirmation.

Tasks:

- Add optional extra `scrubadub`.
- Convert scrubadub detections to provider spans.
- Use scrubadub mostly for direct identifiers and address/postcode-style spans.
- Treat scrubadub name/address detections as provider evidence, not final truth.

Acceptance criteria:

- Provider can run on CSV samples without changing row shape.
- It helps direct PII recall or provider agreement reports.
- False positives on HSD target terms are filtered by fusion.

### spaCy, Stanza, And Flair

These are optional backup NER providers. Add only if GLiNER plus Presidio is
insufficient.

Preferred order:

1. Use spaCy through Presidio first, because it is already in that dependency
   path.
2. Add Stanza only if multilingual or non-Twitter text appears in official data.
3. Add Flair only if empirical tests show a gain that justifies the dependency.

Do not add all three blindly.

### Local LLM Span Reviewer

Use a small local LLM only for structured review of uncertain rows, not as the
main anonymizer.

Recommended models:

- `Qwen2.5-1.5B-Instruct` or `Qwen2.5-7B-Instruct` when Apache-2.0 licensing is
  required.
- `Phi-3.5-mini-instruct` when MIT licensing and long context are useful.

Avoid model choices with unclear, non-commercial, or non-derivative terms.

The prompt must return strict JSON:

```json
{
  "spans": [
    {
      "text": "exact substring",
      "start": 0,
      "end": 4,
      "entity_type": "PERSON",
      "privacy_risk": "direct_identifier",
      "hsd_cue_overlap": false,
      "confidence": 0.91,
      "reason": "person_name"
    }
  ]
}
```

Acceptance criteria:

- The LLM never receives official data through an external API.
- JSON parsing failures are safe failures.
- LLM spans are review/candidate evidence only.
- No freeform LLM rewrite is accepted without reranking and cue validation.

## Phase 3: Weak Supervision Instead Of Manual Labels

The token-policy model currently learns weak labels generated by local rules.
That is acceptable as advisory evidence, but the next version should make weak
labeling explicit and source-aware.

### skweak Or Equivalent Aggregation

Use weak supervision for token/span labels:

- deterministic regex provider;
- Presidio provider;
- GLiNER provider;
- scrubadub provider;
- token-policy ensemble;
- HateXplain rationale protector;
- local LLM review spans, when enabled;
- metadata-derived target fields from datasets.

The aggregator should estimate source reliability and disagreement instead of
hard-coding that one provider is always right.

Tasks:

- Add optional extra `weak-supervision`.
- Build a small `generate-weak-span-labels` report path.
- Emit span-level probabilistic labels and disagreement counts.
- Feed high-confidence weak labels into token-policy training.
- Send high-disagreement rows to semantic triage or human review.

Acceptance criteria:

- Manual source-label constants are moved to resource files.
- Training reports show label source distributions.
- Provider disagreements are measurable by entity type and source.

### cleanlab Label Quality

Use cleanlab after training classifiers/token policies to find likely label
issues, not to auto-change labels silently.

Tasks:

- Add a `label-quality-report` command or evaluation module.
- Use model predicted probabilities plus existing labels.
- Report row IDs, source, label, confidence, and issue type without raw text.
- Use reports to improve stress cases and source normalization.

Acceptance criteria:

- No automatic relabeling in the submission path.
- Cleanlab reports stay under ignored `data/outputs/`.
- Label issue counts are included in experiment reports.

## Phase 4: HSD Cue Preservation And Semantic Meaning

The core utility requirement is preserving hate-speech evidence toward
minorities and other protected groups. Do not optimize privacy by making all
text generic.

### Rationale-Aware Cue Protection

Add HateXplain-style rationale evidence as a cue protector:

- classify or score abusive/hate rationale spans;
- treat rationale spans as `PROTECT_HSD` evidence;
- use rationale overlap as a reranker penalty when a candidate masks or rewrites
  the evidence span.

This should complement, not replace, deterministic target/action/negation
checks.

### Sentence-Level Drift Checks

Add sentence-level advisory scorers:

- CardiffNLP Twitter RoBERTa hate model for hate/not-hate drift.
- Detoxify for toxicity/offensive signal, especially to separate offensive-only
  rows from protected-target hate.
- Existing local classifier path for project-specific labels.

Use these scorers only as drift checks:

- original prediction vs privatized prediction;
- confidence drop;
- margin drop;
- hate/offensive/toxicity score shift;
- disagreement between HSD scorers.

Do not let a classifier decide whether a protected group term should be masked.

### Semantic Similarity

Add semantic similarity as reranker features:

- SentenceTransformers cosine similarity for sentence-level meaning retention.
- BERTScore for token/contextual similarity on rewrite candidates.
- Existing character retention remains a cheap guardrail.

Acceptance criteria:

- Candidate rewrites that lose target/action/negation cues are rejected even if
  their semantic score is high.
- Rows with classifier prediction shifts or large confidence drops are routed
  to review or a safer deterministic candidate.
- Minority/protected target evidence is preserved unless explicit privacy mode
  says otherwise.

## Phase 5: DP And Rewrite Candidates

DP and generative rewriting are promising but risky. Keep them behind candidate
generation, validation, and reranking.

### DPMLM

Keep DPMLM as a protected-token candidate path:

- freeze target terms, hostile action cues, negation, modality, placeholders,
  and repeated-letter cue variants;
- rewrite only eligible style-bearing or low-utility tokens;
- reject unchanged, cue-losing, length-drifting, or identifier-introducing
  candidates;
- record epsilon, seed, changed tokens, rejected predictions, and validation.

DPMLM should not be used for first official submission unless local and official
feedback show it improves the tradeoff.

### SanText / SanText+

Add SanText only as an additional DP text-sanitization benchmark or candidate.

Tasks:

- Wrap it in the same candidate interface as DPMLM.
- Protect HSD cue tokens before substitution.
- Compare against DPMLM on utility retention and privacy gain.

Acceptance criteria:

- No direct submission from SanText output.
- All SanText rows go through reranking and cue validation.

### Opacus For Private Training

Use Opacus only if training token-policy or HSD advisory models on private or
official data.

Tasks:

- Add an optional DP training mode for token-policy fine-tuning.
- Report epsilon/delta, clipping, noise multiplier, epochs, and batch size.
- Compare DP-trained advisory model performance against non-DP advisory models.

This does not anonymize released text by itself; it protects model training.

### Metadata Privacy

Text masking is not enough when metadata columns identify people or tiny groups.

Add optional metadata reports:

- ARX-style k-anonymity/l-diversity/t-closeness for structured columns.
- OpenDP or diffprivlib for aggregate reporting when publishing statistics.
- Existing metadata leakage check for literal text leaks.

Acceptance criteria:

- Official submission still preserves required columns unless challenge rules
  allow metadata transformation.
- Metadata reports explain residual re-identification risk without changing
  required upload shape.

## Phase 6: Candidate Reranking

Reranking should become the central place where optional tools improve output.
No provider should write final text directly.

Candidate set:

- `balanced`
- `style_scrubbed`
- `privacy`
- `target_generalized`
- `presidio_augmented`
- `gliner_augmented`
- `scrubadub_augmented`
- `provider_fusion_augmented`
- `dpmlm_candidate`
- `santext_candidate`
- `local_llm_candidate`
- `token_policy_candidate`

Reranker features:

- direct identifier count after transformation;
- quasi-identifier count after transformation;
- provider confidence and agreement;
- HSD target retention;
- hostile action retention;
- negation/modality retention;
- quote/counterspeech/public-interest context retention;
- rationale span preservation;
- classifier prediction shift;
- classifier confidence or margin drop;
- SBERT/BERTScore similarity;
- character retention and length drift;
- style-risk count;
- author-risk score when repeated author IDs exist.

Decision policy:

- Hard reject candidates with residual direct identifiers when safer candidates
  exist.
- Hard reject candidates that lose protected target/action/negation cues.
- Penalize large semantic drift or classifier shifts.
- Prefer the least destructive candidate that materially improves privacy.
- Keep row-level chosen candidate names and rejection reasons in audit.

Acceptance criteria:

- Reranked output passes `validate-submission`.
- Source regression passes on target/action/negation/rationale slices.
- Audit can explain why each non-baseline candidate was chosen.

## Phase 7: Benchmarks And Regression Data

Add external benchmarks only when their schema, license, and overlap with
existing data are inspected.

### PII And Anonymization Benchmarks

- Text Anonymization Benchmark (TAB): use for masking decisions, confidential
  attributes, and coreference-style anonymization evaluation.
- Existing synthetic PII stress cases: keep for social-media-like handles,
  fictional addresses, names, schools, and organizations.
- Generated LM Studio stress cases: coverage probes only until deduped and
  validated.

### HSD Utility Benchmarks

- HateCheck: functional tests for target, threat, negation, counterspeech,
  reclaimed slurs, non-hateful profanity, and other edge cases.
- HatemojiCheck/HatemojiBuild: emoji-based hate and perturbation robustness.
- Measuring Hate Speech: target identity groups, dehumanization, violence,
  genocide, humiliation, insult, and other constituent labels.
- HateXplain: target community and rationale preservation.
- TweetEval hate/offensive: external social-media drift check.

### Required Reports

For every meaningful pipeline change, produce:

- privacy metrics before/after;
- HSD cue retention;
- source/label/split slice regression;
- provider span precision/recall when gold spans exist;
- candidate selection counts;
- classifier drift summary;
- label-quality/disagreement report when weak labels are used;
- exact-format validation.

No benchmark report should print raw sensitive text.

## Phase 8: Workbench And User Flow

The visible product should match the challenge task:

```text
Upload CSV -> configure columns -> run masking -> inspect audit -> download CSV
```

Required workbench capabilities:

- upload a CSV;
- choose text column and optional ID/label/source/author columns;
- choose mode: `balanced`, `privacy`, or audited reranking;
- enable optional providers when installed;
- preview a sample with typed placeholders and protected HSD cues;
- show privacy gain, residual risk, cue retention, semantic drift, and provider
  disagreement gauges;
- download exact-format CSV;
- download audit JSON and manifest;
- queue uncertain rows for human review without logging raw official examples.

The first screen should be the working CSV tool, not a marketing page.

## Dependency Policy

Base install should remain minimal. Add optional extras by workflow:

```toml
gliner = ["gliner", "torch", "transformers"]
scrubadub = ["scrubadub"]
weak-supervision = ["skweak", "cleanlab"]
semantic = ["sentence-transformers", "bert-score"]
hsd-advisory = ["transformers", "torch", "detoxify"]
dp-training = ["opacus"]
metadata-privacy = ["diffprivlib", "opendp"]
```

Exact package names and versions should be checked during implementation. Keep
heavy model dependencies out of default install.

## Official Submission Sequence

Use this order during the hackathon:

1. Profile official CSVs and inspect schema.
2. Run `balanced` exact-format candidate.
3. Validate row count, row order, column order, IDs, labels, and hashes.
4. Run source regression and HSD cue checks.
5. Submit `balanced` first.
6. If official privacy is weak, run reranking with safe providers:
   `presidio`, then `gliner`, then provider fusion.
7. Submit only an alternate that passes exact-format validation and improves
   local privacy without cue loss.
8. Treat DPMLM, SanText, and local LLM outputs as evidence/candidates until
   they prove they beat deterministic and provider-fusion candidates.

## Implementation Checklist For Next Agent

Start here:

1. Add `SpanProvider` and provider result tests.
2. Migrate existing deterministic spans into `span_providers/deterministic.py`.
3. Migrate filtered Presidio into `span_providers/presidio.py`.
4. Add fusion with protected-cue conflict handling.
5. Add GLiNER provider and optional dependency.
6. Add scrubadub provider and optional dependency.
7. Add provider-enabled reranking options.
8. Add TAB and synthetic PII provider evaluation.
9. Add HateXplain/Cardiff/Detoxify drift and rationale protection as advisory
   evaluation.
10. Add skweak/cleanlab reports for weak labels and disagreement.
11. Add semantic similarity features.
12. Add SanText and Opacus only after provider fusion is stable.
13. Extend workbench from paste-text demo to CSV upload/download.

Each step needs focused tests and a small report under ignored `data/outputs/`.

## Do Not Spend Time On

- Piiranha, unless its licensing changes and is reviewed.
- Broad target generalization as the default submission.
- Raw Presidio replacement without local filters.
- Direct LLM rewriting without validation and reranking.
- New handcrafted city, street, name, school, or organization dictionaries.
- Treating offensive-only or toxic-only text as hate by default.
- Treating unique row IDs as author labels.
- Duplicated external datasets that are already in the merged training bundle.
- Committing generated raw examples, official data, model weights, or run logs.
- More markdown run diaries. Record experiments in ignored JSON artifacts and
  keep only durable conclusions in `experiment_verdict.md`.

## Success Criteria

The improved system is successful when:

- a user can upload a CSV and download a valid masked CSV;
- direct identifiers are strongly reduced;
- quasi-identifiers improve beyond the deterministic baseline;
- target/action/negation/rationale cues for minority-directed hate are
  preserved;
- provider disagreement and review routing are visible;
- optional model paths are auditable and safely gated;
- official upload format remains exact;
- the pitch can honestly say: this is more than Presidio, but still local,
  explainable, and controlled.
