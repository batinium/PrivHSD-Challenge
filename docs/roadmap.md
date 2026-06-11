# PrivHSD Roadmap

## Mission

Privatize text so author-identifying signals are reduced while hate-speech
detection cues remain useful.

This is not just PII redaction. Authorship identification is itself a
classification task, and the system should make that task harder without
destroying the signal needed for hate-speech detection.

## Webinar Takeaways

- The expected artifact is a text-to-text privatization mechanism.
- The output must preserve dataset shape and metadata while changing the text.
- The desired tradeoff is high HSD utility and low author-identification
  utility.
- Presidio-style entity anonymization is a useful baseline, but it misses many
  author signals and can score poorly.
- DPMLM-style rewriting can work, but it adds privacy parameters, stochastic
  behavior, runtime cost, and implementation complexity.
- LLMs may help only when specialized: constrained outputs, explicit
  preservation checks, reranking, and local/offline operation where possible.
  Simple prompting is not enough.
- Winning the public leaderboard does not automatically win the hackathon.
  Judges also evaluate problem understanding, human-rights framing,
  feasibility, impact, limitations, and presentation.

## Current Baseline

The current best submission candidate is `balanced` mode:

- masks direct and quasi identifiers
- preserves target-group terms by default
- keeps row order and metadata
- has strong local utility retention on Dynahate
- remains reproducible and auditable

Latest local Dynahate summary:

| Metric | Value |
| --- | ---: |
| Rows | 41,144 |
| Placeholders | 2,315 |
| Residual identifiers | 3 |
| Residual quasi-identifiers | 0 |
| Target cue retention | 0.9994 |
| Character retention | 0.9953 |
| Local classifier macro-F1 delta | -0.0008 |

## Strategic Gap

The current system is strong at identifier masking, but the challenge is broader
than identifier masking. It needs explicit pressure against authorship cues:

- casing and punctuation habits
- repeated characters and elongations
- emoji and symbol style
- spacing and formatting habits
- slang, idiolect, catchphrases, signatures
- recurring phrase templates
- author-specific topic/context combinations

These can identify authors even when names, handles, and locations are removed.

## Next Technical Bets

### 1. Authorship-Risk Evaluator

When an `author` column is available, train a local author classifier on
original text and evaluate it on privatized text.

Report:

- author-classification accuracy/F1 before and after privatization
- top residual author-confusable examples by row ID only
- privacy gain as author-signal loss
- HSD utility retention in the same report

This aligns the local evaluation with the actual privacy adversary.

### 2. Style-Scrubbing Transformer

Add an optional deterministic text pass that normalizes authorship style while
preserving hate-speech content:

- collapse repeated punctuation
- normalize repeated letters
- normalize casing
- normalize whitespace
- remove signatures and self-tags
- replace emojis/symbol clusters with typed placeholders
- optionally normalize dialectal spellings only when they are not target or
  hate cues

This is likely cheaper and more auditable than full neural rewriting.

### 3. Candidate Generation and Reranking

Generate multiple privatized candidates per row, then pick the best by a local
score:

- deterministic balanced
- balanced plus style scrub
- privacy mode
- balanced with target generalization
- optional Presidio-augmented spans
- optional specialized rewrite

Candidate score should penalize author-classifier confidence and residual
identifiers while preserving HSD classifier confidence and target/action cues.

### 4. DPMLM Spike

Run a small, optional DPMLM-style experiment only after the official dev schema
is known.

Questions to answer before integration:

- What epsilon values are practical?
- How slow is it on the dev set?
- Does it preserve HSD labels better than style scrubbing?
- Does it reduce author-classifier accuracy?
- Can outputs be reproduced enough for audit?

Do not make DPMLM part of the core pipeline until these are answered.

### 5. Specialized LLM Rewrite

If using an LLM, avoid generic "anonymize this" prompting. Use a structured
pipeline:

1. Detect privacy spans and HSD cues.
2. Produce a protected cue skeleton: target, hateful action, intensity,
   negation, threat, and modality.
3. Ask the model to rewrite only author/style-bearing parts.
4. Enforce a JSON schema with preserved cue fields.
5. Run residual privacy, author-risk, and HSD utility checks.
6. Reject or rerank weak candidates.

Keep this optional and local where possible.

## Presidio Role

Presidio should be integrated as a comparison backend, not as the product.

Useful outputs:

- spans only Presidio catches
- spans only PrivHSD catches
- overlap
- false-positive risk on target-group/hate cues
- runtime and dependency cost

This makes Presidio evidence in the pitch rather than a fragile dependency.

## Judging Strategy

The final demo should show:

- runnable system and package
- reproducible commands
- exact dataset shape preservation
- privacy/HSD tradeoff metrics
- author-risk evaluation plan
- ablation table
- limitations and failure cases
- human-rights framing: privacy, free expression, non-discrimination,
  transparency, and human oversight

Leaderboard score matters, but it is not sufficient. The pitch must explain why
the mechanism is thoughtful, deployable, auditable, and aligned with democratic
and human-rights constraints.
