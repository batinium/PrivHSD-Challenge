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

## Model-Backed Plan

Do not train a new attention mechanism first. The available data is better used
for evaluation, reranking, and small calibration tests. The practical plan is:

| Component | Role | Default? |
| --- | --- | --- |
| Local TF-IDF classifiers | HSD utility proxy and author-risk adversary. | Optional, lightweight |
| `facebook/roberta-hate-speech-dynabench-r4-target` | Dynabench-aligned HSD utility evaluator. | Optional |
| `cardiffnlp/twitter-roberta-base-hate-latest` | Social-media hate/offensive utility evaluator. | Optional |
| HateXplain models | Target/rationale cue checks and explainability support. | Optional |
| `unitary/toxic-bert` or Detoxify | Toxicity proxy for weak-signal comparison only. | Optional |
| DPMLM | Bounded rewrite spike with epsilon/runtime/utility reports. | No |
| Local LLM through LM Studio or llama.cpp | Schema-constrained candidate generation only. | No |

External models should support measurement and candidate generation. They should
not become required for `privhsd anonymize`, and their weights, raw downloaded
datasets, and generated official examples must not be committed.

Near-term implementation order:

1. Add author-risk evaluation when an `author` column exists. **Done.**
2. Add deterministic style scrubbing for non-lexical author signals. **Done.**
3. Add a Hugging Face utility evaluator behind an optional extra. **Done.**
4. Add candidate reranking that balances HSD utility against privacy risk.
5. Spike DPMLM on small samples with protected HSD cues and explicit epsilon
   reporting.
6. Add exact-format submission validation and final judging narrative.

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

Status: implemented as `privhsd evaluate-author-risk`. The command trains a
local optional scikit-learn author adversary when the requested author column is
available, reports original versus privatized accuracy, macro-F1, confidence
drop, privacy ratios/gains, residual high-risk row IDs, and local HSD proxy
retention, and writes a structured skipped JSON report when no author column is
present.

When an `author` column is available, train a local author classifier on
original text and evaluate it on privatized text.

Report:

- author-classification accuracy/F1 before and after privatization
- top residual author-confusable examples by row ID only
- privacy gain as author-signal loss
- HSD utility retention in the same report

This aligns the local evaluation with the actual privacy adversary.

### 2. Style-Scrubbing Transformer

Status: implemented behind `--style-scrub` and
`PrivatizerConfig(style_scrub=True)`. The pass is deterministic, runs locally
after privacy masking, preserves placeholders and HSD cues, and records
style-scrub metrics in CSV audit rows.

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
- optional DPMLM or local-LLM rewrite

Candidate score should penalize author-classifier confidence and residual
identifiers while preserving HSD classifier confidence and target/action cues.
When Hugging Face evaluators are available, include their HSD score deltas as
utility signals. Keep all candidate text row-local; do not use neighboring rows
as context.

### 4. Hugging Face Utility Evaluator

Status: implemented as `privhsd hf-model-registry` and
`privhsd evaluate-hf-utility` behind the optional `privhsd[hf-utility]` extra.
The evaluator samples rows by default, records structured skip JSON for missing
dependencies or model failures, and reports model ID, revision when available,
device, runtime, sample size, score drift, threshold agreement, and row IDs with
large utility drops.

Add `privhsd evaluate-hf-utility` behind an optional dependency extra. It should
accept original and privatized columns, run one or more approved local
Transformers classifiers, and write JSON with:

- model name, revision if available, device, runtime, and sample size
- original vs privatized HSD/toxicity probabilities
- label agreement and confidence drift
- rows with large utility drops by row ID only
- skipped/model-load failures without failing the core package

Start with small samples. Full-dataset runs are useful only after memory,
runtime, and license checks are documented.

### 5. DPMLM Spike

Run a small, optional DPMLM-style experiment after the author-risk and HF
evaluators exist. Use only bounded samples at first.

Questions to answer before integration:

- What epsilon values are practical?
- How slow is it on the dev set?
- Does it preserve HSD labels better than style scrubbing?
- Does it reduce author-classifier accuracy?
- Can outputs be reproduced enough for audit?
- Can HSD cue tokens, target groups, negation, and threat/action terms be
  protected from rewriting?

Do not make DPMLM part of the core pipeline until these are answered.

### 6. Specialized LLM Rewrite

If using an LLM, avoid generic "anonymize this" prompting. Use a structured
pipeline:

1. Detect privacy spans and HSD cues.
2. Produce a protected cue skeleton: target, hateful action, intensity,
   negation, threat, and modality.
3. Ask the model to rewrite only author/style-bearing parts.
4. Enforce a JSON schema with preserved cue fields.
5. Run residual privacy, author-risk, and HSD utility checks.
6. Reject or rerank weak candidates.

Keep this optional and local where possible. LM Studio or llama.cpp can be used
through an OpenAI-compatible local endpoint, but the candidate must still pass
the same validators as deterministic candidates.

### 7. Exact-Format Submission Validator

Add a final command that verifies official upload files:

- same columns and row count as the provided dataset unless `--replace-text` is
  explicitly required
- text columns privatized in place when required by the leaderboard
- no extra helper columns in submission mode
- stable row order and IDs
- no raw example leakage into reports, docs, or logs
- machine-readable manifest with command, git commit, dataset path hash, and
  metric summary

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
