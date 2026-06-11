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

The first exact-format submission candidate remains `balanced` mode unless
official scores prove otherwise:

- masks direct and quasi identifiers
- preserves target-group terms by default
- keeps row order and metadata
- has strong local utility retention on Dynahate
- remains reproducible and auditable

Latest local Dynahate summary:

| Variant | Residual IDs | Residual quasi IDs | Target retention | Character retention | Local macro-F1 delta | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `balanced` | 3 | 0 | 0.9994 | 0.9953 | -0.0008 | Prior full Dynahate run. |
| `balanced --style-scrub` | 3 | 0 | 0.9994 | 0.9434 | +0.0017 | Stronger style normalization; 77 changed local predictions. |
| `rerank-candidates` | 3 | 0 | 0.9997 | 0.9868 | +0.0019 | Chose `balanced` for 37,506 rows, `style_scrubbed` for 3,615, `privacy` for 23. |
| `rerank-candidates --presidio-augment` | 3 | 0 | 0.9997 | 0.9755 | +0.0048 | Chose `presidio_augmented` for 6,085 rows; utility-cue retention 1.0. |
| `create-submission --replace-text --mode balanced` | 3 | 0 | 0.9994 | 0.9953 | n/a | Exact-format validation passed: 41,144 rows, same columns/order, no helper columns. |

Additional reranked cue check: 59 rows with any conservative cue loss;
target-term retention mean 0.9971, utility-cue retention mean 1.0, action-term
retention mean 0.9995, and negation/modality retention mean 1.0001.

Bounded model-backed evidence added on 2026-06-11:

| Probe | Sample | Status | Mean delta | Agreement | Runtime | Notes |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| `facebook/roberta-hate-speech-dynabench-r4-target` | 100 | ok | -0.0005 | 1.0 | 36.637s | CPU, revision `391c99ab8b3f65beb77746a2cf6ddf1ddf9817e6`, no large utility-drop rows. |
| `cardiffnlp/twitter-roberta-base-hate-latest` | 100 | ok | -0.0016 | 1.0 | 41.2954s | CPU, revision `cc56585908cbda6d04ba2e1234d911fd1578c9ab`, no large utility-drop rows. |
| `unitary/toxic-bert` | 25 | ok | -0.0 | 1.0 | 20.6408s | CPU toxicity proxy, revision `4d6c22e74ba2fdd26bc4f7238f50766b045a0d94`, no large utility-drop rows. |
| HateXplain classifier variants | 25 | skipped | n/a | n/a | n/a | Both approved HateXplain probes loaded but failed pipeline inference with `tuple index out of range`; keep conservative cue checks as fallback. |

Presidio/spaCy sample-100 comparison: Presidio found 27 spans, PrivHSD found
1 span, overlap was 1, Presidio-only spans were 26, PrivHSD-only spans were 0,
and 9 Presidio detections were flagged as false-positive risk on HSD
cues/targets. Runtime after model setup was 0.4389s, but Presidio's default
initialization downloaded `en_core_web_lg` 3.8.0, a 400.7 MB spaCy model, after
the smaller `en_core_web_sm` had already been installed.

Presidio/spaCy sample-500 comparison: Presidio found 174 spans, PrivHSD found
8 spans, overlap was 6, Presidio-only spans were 168, PrivHSD-only spans were
2, and 52 Presidio detections were flagged as false-positive risk on HSD
cues/targets. Runtime after setup was 1.4907s.

Filtered Presidio augmentation full run: raw Presidio `NRP` spans and
target/action cue overlaps are rejected, while likely `PERSON`, `LOCATION`, and
durable `DATE_TIME` spans are added as optional masks. Full Dynahate reranking
selected `presidio_augmented` for 6,085 rows, with local macro-F1 delta
+0.0048, utility-cue retention 1.0, target-term retention 0.9974, and
character retention 0.9755. Concrete fixed misses include `Amy`, `Steven`,
`Mustafa`, `Britain`, `Caribbean`, and `the 1950s`; concrete rejected false
positives include `Muslims`/`Hindus` target terms, `ngl`, and `sl33p`.

Weak token-action tagger sample-5,000 training: 67,415 weakly labeled tokens,
dev accuracy 0.9888, macro-F1 0.8556, `PROTECT_HSD` F1 0.9890,
`PROTECT_TARGET` F1 0.7810, `MASK_IDENTIFIER` F1 0.8000 on only two dev
examples, and `GENERALIZE_CONTEXT` F1 0.5823. Treat this as detector/reranker
evidence, not supervised privacy truth.

DPMLM local probe: `dpmlm` 1.1.2 installs and imports after NLTK resources are
downloaded. The repository spike detects it but still reports
`adapter_not_implemented` because no audited adapter exists. A tiny direct probe
rewrote protected cues, while a protected-token low-level probe preserved
`immigrants should leave` but produced poor tiny-model text quality.

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
| Weak token-action tagger | Optional detector/reranker feature trained from weak local labels. | No |
| Filtered Presidio augmentation | Optional high-recall entity candidate for reranking/submission alternates. | No |
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
   **Done.**
5. Spike DPMLM on small samples with protected HSD cues and explicit epsilon
   reporting. **Done as a bounded blocker/report harness.**
6. Add exact-format submission validation and final judging narrative.
   **Done.**

## Next Experiment Phase Without Official Files

Official challenge files are not available yet. Continue by stress-testing the
optional model-backed paths on local Dynahate and synthetic fixtures, while
keeping core `privhsd anonymize` deterministic and dependency-light.

Recommended order:

1. Hugging Face utility model runs:
   - status: bounded runs complete in `.venv` with CPU Torch and Transformers
   - default probes passed on sample 25 and 100 with negligible score drift,
     1.0 agreement, and no large utility-drop rows
   - `unitary/toxic-bert` passed on sample 25 as a toxicity proxy
   - HateXplain classifier variants currently produce structured inference
     skips; use conservative HSD cue checks as the reliable fallback
   - sample 500 or full runs are optional longer CPU jobs after license and
     cache-size review
2. Presidio comparison:
   - status: bounded sample-100 and sample-500 comparisons complete
   - Presidio produced many detector-only spans, but a third of those spans
     carried false-positive risk on HSD cues/targets in the first 100 rows
   - sample 500 found 174 Presidio spans versus 8 PrivHSD spans, with 52
     false-positive-risk spans
   - dependency cost is high for a comparison baseline because default
     initialization pulled `en_core_web_lg` 3.8.0
   - filtered augmentation is implemented behind `--presidio-augment`; full
     reranking selected it for 6,085 rows and improved local macro-F1 delta to
     +0.0048 while preserving utility cues
3. Local LLM candidate generation:
   - status: bounded LM Studio run complete against
     `http://100.120.207.64:1234`
   - implementation now supports LM Studio-compatible JSON schema output,
     response-format fallback, wrapped JSON extraction, and aggregate
     `status_counts`
   - `openai/gpt-oss-20b` sample 10 accepted 3 candidates and rejected 7 by
     cue/length checks in 18.2567s
   - reranking selected no LLM candidates; chosen counts and metrics matched
     deterministic `rerank-candidates`
   - `mistralai/ministral-3-3b` was faster but accepted 0 of 3 real rows under
     the conservative checks
   - `qwen/qwen3-4b-2507` and `google/gemma-4-e4b` also accepted 0 of 3 real
     rows under the same checks
   - do not scale LLM generation unless accepted candidates start winning the
     reranker on bounded samples
4. DPMLM rewrite spike:
   - status: `dpmlm` 1.1.2 installed and importable after NLTK resources
   - current spike detects the backend but blocks with `adapter_not_implemented`
   - direct tiny-model DPMLM rewrote protected cues, so it cannot be used raw
   - protected-token low-level probe preserved HSD cues but needs a real model,
     determinism controls, and measured privacy/HSD gains before integration
   - do not integrate into core unless it beats deterministic/reranked outputs
5. Weak token-action training:
   - status: sample-5,000 training complete with macro-F1 0.8556 against weak
     labels
   - use it next as a scorer/reranker feature or uncertainty detector, not as
     a direct anonymizer
6. Transformer fine-tuning or attention experiments:
   - use them only as optional evaluators, rerankers, or candidate scorers
   - do not train a new attention mechanism as the first-line solution
   - compare against local TF-IDF utility, HF utility probes, author-risk
     metrics when author labels exist, cue checks, runtime, and auditability

For every experiment, write outputs under ignored `data/outputs/`, avoid raw
official examples, keep downloaded weights/caches out of git, and update
`agents/current_handoff.md` with concise aggregate results.

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

Status: implemented as `privhsd rerank-candidates`. The command generates
row-local deterministic candidates (`balanced`, `style_scrubbed`, `privacy`,
and `target_generalized`), accepts optional rewrite candidate columns, scores
privacy/style risk against target/action cue retention and drift, and uses an
optional local author scorer only when an author column and scikit-learn are
available.

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
large utility drops. Bounded Dynahate reranked runs now pass for the Dynabench,
CardiffNLP, and Toxic-BERT probes with negligible score drift and no large
utility-drop rows; HateXplain classifier variants currently load but fail
pipeline inference and should remain optional skips.

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

### 4a. HSD Cue Checks

Status: implemented as `privhsd check-hsd-cues`. This is the conservative local
fallback for A26 when rationale models are unavailable. It reports target-term,
utility-cue, action-term, and negation/modality retention by row ID without raw
text.

### 5. DPMLM Spike

Status: implemented as `privhsd dpmlm-spike`. In the current local environment
`dpmlm` 1.1.2 is installed and importable after NLTK resources are present, but
the command still writes a structured `adapter_not_implemented` blocker report
with epsilon sweep configuration, protected cue manifest, runtime, sample IDs,
and existing privatized-column baseline metrics when available. DPMLM remains
outside core anonymization.

Direct library probes show why: the default sentence rewrite can modify
protected HSD cues, while a low-level protected-token probe can freeze those
cues but still needs real-model quality checks, determinism controls, and
audited row-local integration.

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

Status: implemented as `privhsd generate-llm-candidates` for LM Studio or
llama.cpp-style OpenAI-compatible local endpoints. The command requests
schema-constrained JSON, checks target/action cue retention and length drift,
and writes candidates only for later reranking. The client now handles LM
Studio JSON-schema response formatting, fallback behavior, and wrapped JSON
content. Current bounded endpoint evidence is low-yield: `openai/gpt-oss-20b`
accepted 3 of 10 sample candidates, but reranking selected none of them over
deterministic candidates.

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

Status: implemented as `privhsd create-submission` and
`privhsd validate-submission`. The creator requires `--replace-text`, supports
repeatable text columns privatized in place, preserves exact source columns,
and writes a manifest with command, git commit, file hashes, mode, validation,
and aggregate metrics. The validator checks row count, column set/order, ID
order, metadata preservation, and helper-column rejection for upload mode.

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

Status: implemented as `privhsd compare-presidio` behind the optional
`privhsd[presidio]` extra. The current local `.venv` has Presidio/spaCy
installed for comparison runs. On the first 100 Dynahate rows, Presidio found
27 spans versus 1 PrivHSD span, with 1 overlap and 9 false-positive-risk spans
on HSD cues/targets. Treat this as evidence that Presidio is useful for
comparison but risky as a direct anonymization backend.

On the first 500 Dynahate rows, Presidio found 174 spans versus 8 PrivHSD
spans, with 6 overlaps and 52 false-positive-risk spans on HSD cues/targets.
The larger sample strengthens the same conclusion: Presidio is useful evidence,
but direct replacement would likely overmask utility-bearing content.

Status update: filtered Presidio augmentation is now implemented on
`anonymize`, `rerank-candidates`, and `create-submission` via
`--presidio-augment`. It rejects `NRP`, protected cue overlaps, transient dates,
and common shape false positives, then allows reranking to decide whether the
augmented candidate is worth the utility drift.

Useful outputs:

- spans only Presidio catches
- spans only PrivHSD catches
- overlap
- false-positive risk on target-group/hate cues
- runtime and dependency cost

This makes Presidio evidence in the pitch rather than a fragile dependency.

## Judging Strategy

Status: a compact final pitch/demo outline and human-rights framing live in
`docs/final_pitch_outline.md`.

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
