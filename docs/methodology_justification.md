# Methodology Justification

Date: 2026-06-11

This note explains why the pipeline uses deterministic rules, lexicons,
misspelling handling, optional Presidio/DPMLM/LLM candidates, and reranking.
It is meant to support judge questions about provenance, redundancy, and the
privacy/utility tradeoff.

For the mentor-adjacent DP NLP literature map, see
`docs/dp_text_privacy_literature_notes.md`. That companion note explains how
DPMLM, word-level metric DP, privacy-budget allocation, LLM prompting,
post-processing, and privacy evaluation papers map to the current pipeline.

For the human-rights and legal test framing, see
`docs/human_rights_legal_test_plan.md`. That note maps ECtHR Article 10,
Articles 8/13/14, Delfi, Google LLC v. Russia, the Council of Europe Framework
Convention on AI, and HUDERIA into concrete acceptance criteria for this proof
of concept.

## Core Principle

The task is not generic redaction. The privacy target is reducing
author-identifying signal, while the utility target is preserving hate-speech
detection signal. Hate speech is often defined by a target group plus hostile
action, dehumanization, threat, exclusion, or modality. Preserving those cues is
therefore intentional, not accidental.

This is also a legal safeguard. The project must not over-restrict expression:
offensive, insulting, vulgar, shocking, political, satirical, or public-interest
speech is not hate speech merely because the words are unpleasant. At the same
time, erasing target-group and hostile-action evidence can cause the opposite
failure: under-detection of hatred directed at vulnerable or historically
targeted groups. The default method therefore preserves legally relevant context
and leaves legal classification to human review.

Academic support:

- Multi-target hate-speech work argues that hate varies by target community and
  that models benefit from target/topic awareness [1].
- Target-group recognition work argues for explicit knowledge about identity
  group language to improve transparency and reduce bias [2].
- Target identity changes hate-speech language in systematic ways, so erasing
  target terms can erase utility [3].
- Identity terms alone can also trigger false positives; the safer rule is to
  preserve identity terms and their context rather than mask them blindly [4].
- DynaHate is used in target-span work, which reinforces that target spans are
  a meaningful unit for preserving harmful-content interpretation [5].

## Lexicon Provenance

| Lexicon/rule | Why it exists | Source of terms | Audit rule |
| --- | --- | --- | --- |
| Target-group terms | Needed to preserve who the hate is about. | Challenge/Dynahate target categories, dataset-observed targets, and hate-speech target-group literature. | Default is preserve; only explicit privacy modes generalize. |
| Action/utility cues | Needed to preserve whether the text expresses hate, exclusion, threat, or dehumanization. | Existing utility cues, observed local false negatives/DPMLM failures, and literature on target-specific hate language. | `check-hsd-cues` must keep action/negation/utility retention near 1.0. |
| Identifier regexes | Direct privacy baseline for emails, handles, phones, URLs, IDs, dates, locations, names in context. | Conventional PII classes plus local synthetic tests. | Must reduce residual identifiers without changing row shape. |
| Repeated-letter and spelling variants | Social media hate often uses noisy spelling, obfuscation, and filter-evasion. | Social-media hate-speech literature and local error analysis. | Normalize only when it preserves protected cue meaning; freeze repeated-letter tokens for DPMLM. |
| Presidio spans | High-recall optional detector for names, locations, and dates. | Presidio output filtered by local policy. | Reject `NRP`, target/action overlaps, transient dates, and noisy shape false positives. |

The lexicons are not presented as complete dictionaries of hate. They are a
guardrail for preserving HSD utility and preventing neural rewrites from
damaging protected cues. New entries should require at least one of:

1. Appears in the local challenge data with a target/type label.
2. Appears in a row-level audit as a cue-loss or unsafe-rewrite failure.
3. Is supported by established hate-speech resource literature.
4. Is required by a public official taxonomy or challenge rule.

Entries should also be removable: if a term creates false positives, document
the failing row IDs and move it to a narrower contextual rule.

## Misspellings And Obfuscation

Misspellings are not handled by a broad hand-written spelling dictionary. That
would be brittle and hard to defend. The current policy is narrower:

- deterministic style scrub normalizes repeated letters while preserving
  protected cue meaning;
- DPMLM freezes repeated-letter tokens because many elongated spellings in this
  dataset are themselves target or abuse cues;
- character-level and shape-level checks catch common obfuscations without
  assuming a fixed spelling list.

This is supported by social-media hate-speech work showing that noisy text,
hashtags, paralinguistic markers, and poorly written text are central detection
challenges [6], and by lexical baselines that use character n-grams because
they are robust to surface variation [7]. Prior work also explicitly notes
filter-evasion tactics in hate speech [8].

## Why Preserve Target Words?

Target words are preserved because a human or classifier often needs to know
who is targeted to determine whether text is hateful. If a sentence becomes
only "they should leave" or "those people are inferior", the HSD signal is
weaker and sometimes ambiguous.

The project therefore preserves target identity by default and separately
preserves:

- target-group terms,
- hostile action terms,
- dehumanizing/abuse descriptors,
- negation and modality,
- utility phrases such as "should leave" and "not belong".

We verify this with:

- `row_metric`: target and utility cue retention;
- `check-hsd-cues`: target/action/negation/modality retention;
- reranker penalties for cue loss;
- DPMLM protected-token freezing.

This does not guarantee semantic preservation under every sarcasm or implicit
hate case. It is a conservative safety mechanism: avoid destroying explicit HSD
cues unless an official privacy score proves the tradeoff is better.

## What Reranking Means

Reranking means the pipeline generates multiple row-local candidates, scores
each candidate, and chooses the best privacy/HSD tradeoff per row.

Current candidates include:

- `balanced`,
- `style_scrubbed`,
- `privacy`,
- `target_generalized`,
- optional filtered Presidio candidate,
- optional local LLM candidate,
- optional DPMLM candidate.

The reranker dominates the local benchmarks because no single transformation is
best for every row. It can leave a row close to `balanced` when extra masking
does not help, choose `style_scrubbed` when author style is the risk, choose
filtered Presidio when a name/location/date was missed, and reject DPMLM/LLM
candidates when they drift or lose cues. This matches authorship-obfuscation
research that frames the task as a privacy/utility tradeoff rather than pure
redaction [9].

Local evidence:

- deterministic reranking improved local macro-F1 delta over `balanced`;
- filtered Presidio reranking selected 6,085 rows and improved local macro-F1
  delta to +0.0048 while preserving utility-cue retention at 1.0;
- LLM and DPMLM candidates were generated, validated, and rejected by reranking
  when they did not beat deterministic alternatives.

## Authorship Identification Test

There are two different tests:

1. `check-metadata-leakage`: direct leakage check for whether values like
   `id` or `author` literally appear in original or privatized text.
2. `evaluate-author-risk`: stylometric adversary check for whether writing
   style still predicts an `author`, `user`, or equivalent label.

Using `id` as `author` is only valid if the ID actually groups multiple texts
from the same person. If each `id` is unique per row, it is not an author label;
the author classifier should skip because it cannot learn an author profile.

Current Dynahate limitation:

- local file columns are `id,text,label,source,split,target,type`;
- `source` has only one value, `dynahate`;
- there is no author/user label;
- each `id` occurs once, so `--author-col id` skips with
  `insufficient_author_rows`;
- direct metadata leakage scan found 0 exact/normalized `id` leaks in both
  original `text` and reranked `privatized_text`;
- a clean-text author-risk run therefore skips with
  `insufficient_author_labels`.

So the honest claim is:

- we have implemented the author-risk evaluator;
- we have not measured true author-identification reduction on Dynahate because
  the needed labels are absent;
- when official data includes author IDs, run original-clean vs protected text
  and report author accuracy/F1/confidence drop.

Stylometry literature supports treating writing style as a privacy risk even
after explicit identifiers are removed [10]. Prior work shows author
obfuscation should preserve meaning while reducing attribution accuracy [11],
and privacy text-mining work explicitly notes that simply removing identifiers
is insufficient against authorship attribution [12].

## Redundancy Reduction Policy

Do not keep a rule merely because it looks plausible. Keep it only when it
serves one of these roles:

1. It masks a direct/quasi identifier with low HSD utility risk.
2. It protects a target/action/negation cue from being destroyed.
3. It reduces author-style signal without changing HSD meaning.
4. It improves measured rerank choice or official score.
5. It explains a documented failure mode.

Remove or narrow a rule when:

- it masks target identity by default;
- it changes hate/no-hate interpretation;
- it is never selected by reranking;
- it duplicates another rule without improving audit metrics;
- it only helps a model path that remains candidate-only and low-yield.

## References

[1] [Emotionally Informed Hate Speech Detection: A Multi-target Perspective](https://consensus.app/papers/details/49be0684f8e65cdfa6b285df5027993b/?utm_source=unknown) (Patricia Chiril et al., 2021, Cognitive Computation, 84 citations).

[2] [Knowledge-Grounded Target Group Language Recognition in Hate Speech](https://consensus.app/papers/details/3023048ae9265c32977c1bfed0b2f754/?utm_source=unknown) (P. Lobo et al., 2023, Unknown Journal, 4 citations).

[3] [How Hate Speech Varies by Target Identity: A Computational Analysis](https://consensus.app/papers/details/634ae11824dc5209ac6f547c81a22261/?utm_source=unknown) (Michael Miller Yoder et al., 2022, Unknown Journal, 33 citations).

[4] [Contextualizing Hate Speech Classifiers with Post-hoc Explanation](https://consensus.app/papers/details/9964c77093e9532bb3febba2e61fdae9/?utm_source=unknown) (Brendan Kennedy et al., 2020, ArXiv, 157 citations).

[5] [Target Span Detection for Implicit Harmful Content](https://consensus.app/papers/details/6f1f58ec40145c75aa528da8b10b7ff4/?utm_source=unknown) (Nazanin Jafari et al., 2024, Proceedings of the 2024 ACM SIGIR International Conference on Theory of Information Retrieval, 9 citations).

[6] [Challenges of Hate Speech Detection in Social Media](https://consensus.app/papers/details/75e3ee2f217c5118a57aba415fbcc97c/?utm_source=unknown) (Gyorgy Kovacs et al., 2021, SN Computer Science, 144 citations).

[7] [Detecting Hate Speech in Social Media](https://consensus.app/papers/details/38e282f39f00556fbc9b410a3c0d24a9/?utm_source=unknown) (S. Malmasi et al., 2017, Unknown Journal, 338 citations).

[8] [Detecting Hate Speech on the World Wide Web](https://consensus.app/papers/details/d9f501892df85ebab5b3791f613a1039/?utm_source=unknown) (William Warner et al., 2012, Unknown Journal, 724 citations).

[9] [TAROT: Task-Oriented Authorship Obfuscation Using Policy Optimization Methods](https://consensus.app/papers/details/7834241b048c542d98628933052cf8be/?utm_source=unknown) (Gabriel Loiseau et al., 2024, ArXiv, 4 citations).

[10] [Adversarial stylometry: Circumventing authorship recognition to preserve privacy and anonymity](https://consensus.app/papers/details/b63dde96f3715d9db34be87ae58a3b36/?utm_source=unknown) (Michael Brennan et al., 2012, ACM Trans. Inf. Syst. Secur., 225 citations).

[11] [Obfuscating Document Stylometry to Preserve Author Anonymity](https://consensus.app/papers/details/17752585353d52cabda923a073ec0258/?utm_source=unknown) (Gary Kacmarcik et al., 2006, Unknown Journal, 95 citations).

[12] [SynTF: Synthetic and Differentially Private Term Frequency Vectors for Privacy-Preserving Text Mining](https://consensus.app/papers/details/839cd798509653198bb60df0ca59702e/?utm_source=unknown) (Benjamin Weggenmann et al., 2018, The 41st International ACM SIGIR Conference on Research & Development in Information Retrieval, 55 citations).
