# Research Notes: Turning ContextSafe-HSD Into A Paper

Date: 2026-06-20

These notes capture the research direction discussed after the hackathon. The
main purpose is to preserve the exact framing, technical claims, data questions,
and experiment ideas for later writing.

## Current Situation

We did not win / pass the hackathon, but the project has a plausible research
contribution. The mentor did not accept the high-scoring approach, even after
tunable surrounding-context knobs were added. The likely issue is not that the
method is technically invalid, but that it did not match the mentor's unstated
expectation for the protected output.

The hidden benchmark appeared to reward a scalar privacy/utility objective, but
the mentor did not clearly specify which privacy marks or release constraints
were expected. This created a mismatch between:

- a metric-maximizing evidence-minimized representation; and
- a human-readable anonymized Reddit-like dataset.

That mismatch is itself a research point: privacy-preserving harmful-speech
dataset release needs a clear threat model, a clear utility target, and
benchmark metrics that do not silently prefer one output representation while
rejecting another.

## Important Clarification: This Was Not A Gold-Label Template Hack

The earlier "if hs, keep only hate-speech words; if not, redact completely"
description sounds like a gold-label exploit, but the actual method is stronger.

The working method did not require gold labels at transformation time. It used a
classifier trained from a pretrained DeHateBERT-style harmful-speech model. The
classifier was about 90 percent accurate, so it could predict whether a row was
harmful/offensive and identify which tokens were important to that prediction.

The transformation used token importance / occlusion-style probing:

1. Start with a Reddit sentence or a regex-PII-redacted version of the sentence.
2. Run the harmful-speech classifier.
3. Probe token importance by measuring how much each token affects the model's
   harmful-speech score.
4. Keep the most important harmful-speech evidence tokens or short spans.
5. Optionally keep a tunable number of surrounding context words.
6. Redact or minimize the rest.
7. Run final PII cleanup.

This means the method is deployable on unlabeled data, assuming a trained
classifier is available. It is not the same as using the provided `hs` column to
construct label templates.

A key observation: the method still worked on regex-redacted / PII-redacted
rows. That suggests harmful-speech utility can survive after direct identifier
removal, and that evidence minimization can be layered on top of normal PII
redaction.

## Research Framing

Best primary framing:

**Attribution-guided text minimization for privacy-preserving harmful-speech
dataset release.**

Core claim:

Harmful-speech classification utility is often concentrated in sparse lexical
or phrase-level evidence. Classifier attribution can identify this evidence and
produce minimized release representations that retain much of the harmful-speech
signal while reducing privacy exposure.

Careful wording:

- Do not claim this is full anonymization.
- Do not claim it preserves all downstream dataset uses.
- Do claim it is a release representation, audit representation, or
  privacy-aware minimized benchmark representation.
- Be explicit that there is a tradeoff between privacy, classifier utility, and
  human readability.

Refined framing after later discussion:

**Target-aware evidence minimization** is stronger than generic token filtering.
The method should not merely keep high-importance words. It should keep the
minimum evidence tuple needed for harmful-speech interpretation:

```text
target group + harmful cue + stance/context cue
```

This makes the contribution more than "advanced preprocessing." It becomes a
task-aware release method with explicit semantic constraints.

Novelty boundary:

- Not novel by itself: token importance for hate or toxicity.
- Not novel by itself: toxic span detection or rationale extraction.
- Not novel by itself: text anonymization and de-identification.
- Plausibly novel: using classifier-derived harmful-speech evidence spans as a
  privacy-preserving release representation.
- Stronger novelty: making the release target-aware by preserving target group,
  harmful cue, and stance context while minimizing private text.
- Strongest novelty: measuring the privacy/utility/context curve as the amount
  of retained surrounding context is varied.

Possible titles:

- "Attribution-Guided Text Minimization for Privacy-Preserving Harmful Speech
  Dataset Release"
- "How Much Text Does Hate-Speech Classification Need? Evidence Minimization
  for Privacy-Aware Dataset Release"
- "Classifier-Guided Evidence Minimization for Privacy-Preserving Online Abuse
  Data"
- "When Privacy Benchmarks Reward Text Collapse: Lessons from Harmful-Speech
  Dataset Sanitization"

## Why The Mentor May Have Rejected It

The mentor's rejection does not necessarily mean the method lacks research
value. It may mean the challenge expected a different artifact.

Possible intended artifact:

- human-readable protected Reddit text;
- row-level anonymized data that can still support qualitative analysis;
- outputs preserving broader conversational or social context;
- sanitized text that remains useful beyond binary harmful-speech
  classification.

Our evidence-minimization method instead produces:

- short evidence snippets;
- classifier-preserving representations;
- reduced text exposure;
- potentially less human-readable context;
- stronger privacy/utility compression for one task.

The paper should present this as a design choice, not as a claim that the
mentor's product expectation was wrong. The stronger argument is that the
benchmark and instructions did not distinguish these output types clearly.

## Threat Model And "Privacy Marks" To Define Explicitly

The challenge did not clearly state what privacy marks were expected. A paper
should define them explicitly.

Direct identifiers:

- names;
- usernames and handles;
- emails;
- phone numbers;
- addresses;
- URLs;
- social media handles;
- IDs, account names, and signatures.

Quasi-identifiers:

- locations;
- workplaces;
- schools;
- dates and timestamps;
- rare events;
- occupations;
- demographic combinations;
- family relations;
- local references;
- named organizations when they identify the author or target.

Author-linkability / style leakage:

- repeated phrases;
- idiolect;
- unusual spelling;
- punctuation style;
- emoji patterns;
- hashtags;
- catchphrases;
- repeated insults or self-references;
- repeated details across rows from the same author.

Source-recovery risk:

- whether a transformed text fragment can be searched to recover the original
  Reddit post;
- whether retained rare n-grams are enough to identify the source;
- whether a reader can infer the author, subreddit, event, or original thread.

Group leakage:

- details that identify protected groups, local communities, or a specific
  target beyond what is needed for the harmful-speech task;
- repeated author-group patterns across multiple rows.

Residual sensitive context:

- descriptions of personal trauma;
- health, sexuality, immigration, religion, or political identity details;
- context that may not be direct PII but is still sensitive.

## Utility Targets To Define Explicitly

The paper should distinguish several utility levels.

Classifier utility:

- harmful-speech label is preserved;
- classifier confidence remains usable;
- downstream HSD model performance stays high.

Rationale utility:

- retained text explains why the content is harmful or not harmful;
- important target/action/identity words are preserved where appropriate.

Context utility:

- negation is preserved;
- counterspeech is preserved;
- quoted speech is not mistaken for author endorsement;
- sarcasm/reporting context is not destroyed;
- target and action are still understandable.

Human-review utility:

- a reviewer can judge whether the transformed snippet reflects harmful speech;
- a reviewer is not forced to see unnecessary raw personal details;
- the text is not so collapsed that review becomes meaningless.

General dataset utility:

- data can support more than one classifier;
- data can support audits and error analysis;
- data can support methodological comparisons without exposing full raw text.

## Method To Describe

Working method name options:

- attribution-guided text minimization;
- classifier-guided evidence extraction;
- harmful-speech evidence minimization;
- privacy-aware evidence spans.
- target-aware evidence minimization.

Pipeline:

```text
raw Reddit text
  -> deterministic / regex direct-identifier redaction
  -> model-assisted PII / quasi-identifier detection
  -> harmful-speech classification with fine-tuned DeHateBERT
  -> token occlusion or attribution scoring
  -> target group detection
  -> harmful cue detection
  -> stance / negation / quote / counterspeech cue detection
  -> constrained evidence tuple selection
  -> optional surrounding context window
  -> cue-preservation and conflict-resolution checks
  -> final PII cleanup
  -> minimized protected text plus audit sidecars
```

The constrained evidence tuple is the key methodological object:

```text
evidence_tuple = {
  target_span,
  harmful_cue_span,
  stance_context_span,
  optional_context_window
}
```

The selected release text should minimize private/contextual exposure while
preserving this tuple when the row is predicted harmful or offensive.

Important knobs:

- maximum number of anchor tokens;
- minimum absolute score delta for anchors;
- relative score threshold against top anchor;
- context window radius around selected anchors;
- separate behavior for predicted harmful vs non-harmful rows;
- whether to use raw text, regex-redacted text, or already-protected baseline
  text for attribution and output;
- whether to preserve non-HSD rows as baseline-protected text or collapse them
  more aggressively;
- final PII cleanup level.

Important variants:

- zero-context anchors: best minimization, highest semantic brittleness;
- relaxed phrase extraction: anchors plus two to five surrounding words;
- protected-baseline extraction: use protected text only, stronger privacy
  story;
- raw-anchor / protected-output hybrid: use raw text to find evidence but copy
  from protected text when alignment works;
- regex-PII-redacted input: important because it shows the method still works
  after normal direct identifier cleanup.

## Technology And Method Stack

Regex is not enough for privacy cleanup. Names, locations, schools, workplaces,
public events, usernames, subreddits, and rare local references can survive
simple patterns. The paper should use a layered span proposal system and state
that residual leakage is measured rather than assumed solved.

Recommended span proposal layers:

- deterministic regex recognizers for emails, URLs, phone numbers, handles,
  IP-like strings, IDs, and obvious direct identifiers;
- Microsoft Presidio as the main PII/anonymization framework;
- scrubadub as an additional PII detector;
- spaCy transformer NER for common entities such as `PERSON`, `GPE`, `LOC`,
  `ORG`, `DATE`, and related labels;
- GLiNER or another flexible NER model for social-media-specific or
  task-specific spans such as `school`, `workplace`, `subreddit`,
  `local event`, `online handle`, `public figure`, `protected group`,
  `nationality`, `religion`, `gender identity`, `sexual orientation`,
  `disability`, and `immigration status`;
- harmful-speech target lexicons from HateXplain, HateCheck, Measuring Hate
  Speech, and related datasets;
- classifier token importance / occlusion scores from DeHateBERT or another
  HSD model;
- lightweight dependency or window rules to connect target spans to harmful
  cue spans.

Do not rely on one detector. The right internal representation is a typed span
graph:

```text
span = {
  start,
  end,
  text,
  labels: [PII, quasi_identifier, target_group, harmful_cue,
           stance_cue, classifier_important],
  confidence,
  source_detector
}
```

The release policy should resolve conflicts explicitly:

```text
PII + not target_group       -> mask or generalize
quasi_identifier             -> mask, generalize, or drop
target_group                 -> preserve when needed for HSD meaning
target_group + PII conflict  -> generalize unless it is a generic group term
harmful_cue                  -> preserve if needed for utility
stance_cue                   -> preserve if it changes interpretation
rare event/location          -> mask or generalize
```

Examples:

```text
Original: John from Lincoln High said immigrants should be kicked out.
Output:   [PERSON] from [SCHOOL] said immigrants should be kicked out.

More minimized:
Output:   immigrants should be kicked out.

If reporting context is necessary:
Output:   said immigrants should be kicked out.
```

This target-aware resolver is the main thing that prevents the method from
being dismissed as generic preprocessing.

## Formal Objective

Frame the method as constrained minimization:

```text
Given source text x, produce release text y.

Minimize:
  retained private text
  retained token budget
  source-recovery risk

Subject to:
  harmful-speech label is preserved
  target group is preserved when relevant
  harmful cue is preserved when relevant
  stance / negation / quote / counterspeech cues are preserved
  residual direct PII is below a threshold
```

This objective lets the paper distinguish three tasks:

- human-readable anonymization;
- classifier-preserving minimization;
- public release or audit representation.

The proposed method targets the second and third tasks, not full human-readable
paraphrase generation.

## Central Figure Idea

Show a privacy/utility/context curve:

```text
0 surrounding words    -> strongest minimization, weaker readability/context
2 surrounding words    -> good utility, moderate privacy exposure
5 surrounding words    -> stronger context, more leakage
full sentence baseline -> most readable, weakest minimization
```

Plot against:

- harmful-speech F1 / accuracy;
- residual PII count;
- retained token percentage;
- source-recovery risk;
- human context-preservation score.

This may be the most important figure in the paper.

## Key Reviewer Risks

Classifier circularity:

If DeHateBERT chooses tokens and DeHateBERT evaluates utility, reviewers will
call the result self-confirming. Need cross-model evaluation.

Mitigation:

- evaluate utility with DeHateBERT and at least one unrelated model;
- include RoBERTa / HateXplain-style models if possible;
- include LLM or human evaluation for a small sample;
- compare selected spans against human rationales on HateXplain.

Privacy overclaiming:

Token minimization is not automatically anonymization.

Mitigation:

- call it minimization or reduced exposure, not full anonymization;
- separately measure residual PII, quasi-identifiers, retained unique n-grams,
  and source-recovery risk.

Context collapse:

Short evidence spans may preserve classifier labels but lose negation,
counterspeech, quotation, sarcasm, target, or rationale.

Mitigation:

- use context-window knobs;
- use cue-preservation checks;
- evaluate against HateCheck-style phenomena;
- run human review on context preservation.

Benchmark critique sensitivity:

The mentor rejected the method. Do not write the paper as a complaint.

Mitigation:

- frame the hackathon as motivation only;
- use open datasets as the primary basis;
- say the challenge exposed an ambiguity in privacy/utility definitions.

## Experiments To Run

Main baselines:

- raw text;
- regex PII redaction only;
- deterministic ContextSafe-HSD baseline;
- full protected baseline with PII assist and cue-safe style scrubbing;
- LLM rewrite / restatement baseline if available;
- random token retention at matched token budget;
- redact-all baseline;
- label-template / high-risk collapse baseline, clearly marked as invalid or
  non-deployable if it uses labels;
- attribution-guided zero-context extraction;
- attribution-guided relaxed phrase extraction;
- protected-baseline extraction;
- raw-anchor / protected-output hybrid.

Utility metrics:

- HSD accuracy;
- macro F1;
- harmful-class F1;
- precision / recall for harmful class;
- calibration or confidence retention;
- performance across several classifiers, not only the model used for
  extraction;
- rationale overlap on datasets with human rationales.

Privacy / exposure metrics:

- residual direct PII count;
- residual quasi-identifier count;
- retained token percentage;
- retained character percentage;
- unique n-gram retention;
- exact-search recoverability if source text is public;
- author attribution accuracy if author IDs are available;
- nearest-neighbor similarity to original text;
- number of rows that still contain rare named entities.

Human evaluation:

- label preserved: yes/no/uncertain;
- harmful-speech rationale preserved: yes/no/uncertain;
- privacy risk reduced: Likert scale;
- context sufficient for review: Likert scale;
- unnecessary sensitive detail retained: yes/no;
- target group preserved when needed: yes/no/uncertain;
- harmful cue preserved when needed: yes/no/uncertain;
- stance cue preserved when needed: yes/no/uncertain;
- examples of failures: negation, counterspeech, quote/reporting, target loss,
  over-redaction.

Small annotation plan:

- no need to hand-label a full dataset for HSD labels because existing datasets
  already provide labels;
- hand-label a small evaluation set for what existing labels do not cover:
  privacy spans, target spans, harmful cues, and context preservation;
- suggested size for a workshop paper: 200 to 500 rows;
- suggested size for a stronger ARR / journal version: 500 to 1000 rows;
- use two or three annotators if possible;
- report agreement with Cohen's kappa or Krippendorff's alpha when practical;
- sample across harmful, offensive, and neutral rows;
- include cases with negation, counterspeech, quoted hate, reporting, and
  identity terms.

Annotation schema:

```text
direct_pii_span
quasi_identifier_span
target_group_span
harmful_cue_span
stance_context_span
label_preserved
target_preserved
harmful_cue_preserved
stance_preserved
privacy_risk_reduced
context_sufficient_for_review
```

The human task should compare raw, PII-redacted, and minimized versions, not
only judge the minimized output in isolation.

Ablations:

- raw input vs regex-PII-redacted input;
- DeHateBERT threshold sweeps;
- max anchors 1/2/3/5;
- context radius 0/1/2/5/full sentence;
- anchor absolute delta threshold;
- anchor relative threshold;
- PII cleanup before attribution vs after attribution vs both;
- classifier-text-source raw vs protected baseline;
- output-source raw vs protected baseline;
- non-HSD row handling: baseline protected vs empty/redacted vs evidence
  extraction.
- target-aware resolver enabled vs disabled;
- target lexicon only vs model attribution only vs combined;
- PII-first vs target-first conflict policy;
- stance cue preservation enabled vs disabled.

Main methodology in one paragraph:

Use labeled W&SM harmful-speech datasets to train or select an HSD classifier.
Transform held-out rows without using their gold labels. First apply direct PII
cleanup. Then use classifier attribution to identify important evidence tokens,
combine them with target-group, harmful-cue, and stance-cue detectors, and
select the shortest release span satisfying semantic preservation constraints.
Finally apply PII cleanup again. Compare the resulting minimized text against
redaction, rewriting, random retention, and full-text baselines using
cross-model utility, privacy exposure, rationale overlap, and small-scale human
review.

## Open Datasets To Use

Use open data as the main paper basis unless the mentor gives written
permission. This makes the paper reproducible and avoids challenge-data rights
problems.

HateXplain:

- strong primary candidate;
- includes hate/offensive/normal labels;
- includes target communities;
- includes human rationales;
- useful for comparing classifier-selected spans against human rationales.

Davidson hate speech / offensive language:

- classic benchmark;
- useful for basic HSD/offensive classification experiments;
- less rich than HateXplain for rationale comparison.

HateCheck:

- functional test suite;
- useful for context-loss stress tests;
- covers negation, counterspeech, reclaimed slurs, quoted hate, and other
  tricky phenomena.

Jigsaw Toxic Comment:

- larger-scale toxicity data;
- not exactly hate speech, but useful for robustness and scale;
- can test whether the method generalizes beyond Reddit-style HSD.

Potential additional datasets to investigate later:

- CivilComments;
- Gab Hate Corpus;
- Measuring Hate Speech;
- OLID / OffensEval;
- ToxicSpan if span labels are useful.

Need to verify licenses, redistribution terms, and citation requirements before
using any dataset in a paper.

## Mentor Dataset Permission

Do not build the main paper around the mentor's challenge dataset unless written
permission is granted. Even if the raw source is Reddit, the curated split,
labels, hidden evaluator, and benchmark website may be the mentor's or
organizers' research artifact.

Best approach:

- use public datasets as the main reproducible experiments;
- ask mentor for permission to report the challenge data as a secondary case
  study;
- ask separately about aggregate metrics, transformed examples, and raw data
  redistribution;
- avoid redistributing raw Reddit text or hidden evaluator details unless
  explicitly allowed.

Draft email:

```text
Hi [Name],

I'm planning to turn part of my hackathon work into a research paper on
classifier-guided text minimization for privacy-preserving harmful-speech
dataset release.

I want to be careful about data rights and the challenge rules. Would you be
open to granting written permission for me to use the challenge Reddit dataset
and evaluator results in the paper?

Specifically, I'd like permission to:

1. Run additional experiments on the dataset.
2. Report aggregate metrics and ablation results.
3. Describe the benchmark setup at a high level.
4. Include transformed examples only if fully anonymized, or omit examples if
   preferred.
5. Cite you, the challenge, or the organization in the acknowledgments or
   dataset section.

I would not redistribute the raw dataset, hidden evaluator, or raw Reddit text
unless you explicitly allow it. If permission is limited, I can use public
datasets as the main experiments and mention the challenge only as motivation.

Could you let me know what use is acceptable, and whether there are any privacy,
citation, or embargo constraints?

Best,
[Your Name]
```

## Venue Ideas

Near-term workshop:

- WOAH / Workshop on Online Abuse and Harms: strong topical fit for harmful
  speech, online abuse datasets, evaluation, and ethical issues.

Longer NLP path:

- ACL Rolling Review / ARR;
- Findings of ACL/EMNLP/NAACL depending on timing and review outcome.

Interdisciplinary / governance path:

- Journal of Online Trust and Safety;
- ACM FAccT if framed around benchmark design, evaluation, privacy harms, and
  governance;
- PETS / PoPETs only if the privacy threat model and empirical privacy
  evaluation become much stronger.

Likely best strategy:

1. Write a workshop-style short paper around the core idea and benchmark
   ambiguity.
2. Run expanded open-dataset experiments.
3. Convert to a stronger ARR or journal submission.

## Suggested Paper Structure

Abstract:

- State the problem: harmful-speech datasets contain classification signal and
  privacy risk.
- State the method: attribution-guided evidence minimization after PII cleanup.
- State the result: classifier utility can be preserved with much less retained
  text, but context and privacy must be evaluated explicitly.
- State the lesson: scalar metrics need clear threat models and utility targets.

Introduction:

- Harmful-speech data is privacy-sensitive.
- Standard redaction can leave style/context leakage or destroy label utility.
- Rewriting can hallucinate, shift labels, or be expensive.
- Evidence minimization is an alternative release representation.
- The hackathon experience motivates the benchmark ambiguity, but the paper
  should not depend on private challenge details.

Related work:

- harmful-speech datasets;
- text anonymization and de-identification;
- privacy-preserving NLP;
- rationales and token attribution;
- toxic span detection;
- target-aware hate-speech detection;
- dataset release ethics;
- benchmark gaming / Goodhart's law.

Closest related work buckets:

- toxic span detection and hate-speech rationale datasets show that token-level
  harmful evidence can be annotated or predicted;
- HateXplain-style datasets show that human rationales and target communities
  matter for explainability and bias;
- text anonymization work shows how to reduce identifiers and private
  attributes while preserving utility;
- the proposed novelty is to repurpose harmful-speech evidence spans as a
  privacy-aware release representation, with explicit target and stance
  constraints.

Method:

- classifier training;
- token importance / occlusion;
- target-aware evidence tuple selection;
- context radius;
- layered PII and quasi-identifier cleanup;
- typed span graph and conflict resolver;
- sidecar audit metadata;
- cue-preservation checks.

Experiments:

- datasets;
- baselines;
- utility metrics;
- privacy metrics;
- human evaluation design;
- ablations.

Results:

- privacy/utility/context tradeoff curve;
- cross-model utility;
- rationale overlap;
- failure cases;
- examples with safe synthetic or heavily transformed text only.

Discussion:

- evidence minimization is not full anonymization;
- not all dataset uses are preserved;
- benchmark objectives must specify release representation;
- human-readable anonymization and classifier-preserving minimization are
  different tasks.

Limitations:

- classifier dependence;
- English/Reddit/domain dependence;
- residual source recoverability;
- harmful-speech context complexity;
- possible bias amplification from classifier-selected evidence.

Ethics:

- do not redistribute raw private challenge data;
- avoid publishing harmful raw examples unnecessarily;
- use transformed or synthetic examples where possible;
- discuss risks of preserving slurs or harmful evidence;
- discuss reviewer exposure and public release risks.

## Repo Anchors To Revisit

Potentially relevant repo areas:

- `contextsafe_hsd/cli.py`
- `contextsafe_hsd/evidence_postprocess.py`
- `contextsafe_hsd/template_postprocess.py`
- `contextsafe_hsd/models/hf_hsd_classifier_runtime.py`
- `scripts/hf_token_importance.py`
- `docs/planning/ablation.md`
- `docs/planning/current_status.md`
- `docs/reference/pipeline.md`
- `mobile/` for human-review workflow support, not as the main paper
  contribution.

Existing repo story:

- locked baseline preserved CSV shape and used deterministic plus PII-assist
  cleanup;
- evidence extraction is the more interesting research direction;
- template/gold-label collapse should be treated as a benchmark failure mode,
  not as the proposed method;
- mobile review app is supporting infrastructure for human review and audit.

## Next Concrete Steps

1. Ask the mentor for written permission, but do not wait on that to begin open
   dataset experiments.
2. Choose one primary open dataset, likely HateXplain.
3. Define the typed span schema: PII, quasi-identifier, target group, harmful
   cue, stance cue, classifier-important token.
4. Implement or isolate the span proposal layers: regex, Presidio, scrubadub,
   spaCy / transformer NER, GLiNER-style flexible NER, target lexicon, and
   classifier token importance.
5. Implement the target-aware conflict resolver.
6. Reproduce classifier-guided token importance on the open dataset.
7. Build context-radius sweeps: 0, 1, 2, 5, full sentence.
8. Evaluate with at least one classifier not used for token selection.
9. Add privacy exposure metrics: retained tokens, residual PII, unique n-grams,
   source-recovery proxy.
10. Compare classifier-selected spans with human rationales if using HateXplain.
11. Hand-label 200 to 500 rows for target/cue/context/privacy preservation.
12. Draft a short paper around the target-aware tradeoff curve and benchmark
    ambiguity.
