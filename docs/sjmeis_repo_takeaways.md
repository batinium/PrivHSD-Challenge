# sjmeis DP Text Repo Takeaways

Date: 2026-06-11

Scope: public repositories under `https://github.com/sjmeis?tab=repositories`
that are relevant to privacy-preserving text rewriting. No external code was
downloaded into this project for this note.

## Core Takeaway

Do not import whole research stacks during the hackathon. Use these repos as
design evidence for small optional candidate generators, budget policies, and
evaluation checks around the existing deterministic pipeline.

The project should keep this shape:

```text
deterministic baseline candidates
  + optional DP/text-obfuscation candidates
  + optional entity detector candidates
  -> cue-preserving validators
  -> privacy/utility reranker
  -> exact-format submission
```

The default `privhsd anonymize` path should remain local, deterministic,
dependency-light, and auditable.

## Patterns Worth Building

### 1. Candidate Adapters, Not New Default Pipelines

`DPMLM`, `Diffractor`, `MLDP`, and `SANTEXT` are best treated as optional
candidate sources. Each adapter should produce proposed `privatized_text`
variants and metadata, then let our existing cue checks and reranker decide
whether the candidate is usable.

Adapter output should include:

- source mechanism name
- package/repo version when available
- epsilon and other privacy parameters
- seed
- runtime
- changed token count
- rejected/protected token count
- validator status

### 2. Privacy Pressure Allocation

Several repos focus on where to spend the privacy budget instead of rewriting
everything uniformly. We can build a lightweight local version without a heavy
research stack.

Increase rewrite pressure for:

- direct identifiers and quasi-identifiers
- author-style signals such as casing, punctuation habits, elongations, and
  repeated symbols
- rare terms and recurring author-specific phrases when author labels exist
- non-HSD topical details that may identify an author

Protect or freeze:

- target-group terms needed for HSD utility
- action and threat cues
- negation, modality, and quoted/ironic markers
- placeholders already inserted by the privacy pass

This maps cleanly onto `token_actions`, `cue_checks`, and reranking features.

### 3. Collocation-Aware Rewriting

Word-level DP methods can damage multi-word expressions. `CLMLDP` and
`DP-Decompose-Distribute` point to a practical rule: detect phrases before
replacement, and either freeze important HSD phrases or rewrite non-HSD phrases
as a unit.

Small local version:

- detect repeated bigrams/trigrams in the input corpus
- mark target/action cue phrases as protected chunks
- mark high-risk non-HSD phrases as rewrite candidates
- audit chunk decisions per row

### 4. Post-DP Repair And Rejection

`PPDPTR` reinforces that DP rewritten text often needs post-processing. For
this project, post-processing should be conservative and validator-driven.

Run every optional DP candidate through:

- residual identifier checks
- HSD cue retention checks
- target-term retention checks
- length and placeholder sanity checks
- style normalization already supported by this repo

Reject candidates that fail instead of trying to make the DP mechanism itself
perfect.

### 5. Evaluation As A Three-Way Tradeoff

The most reusable idea across these repos is evaluation design. The report
should compare privacy, HSD utility, and text quality rather than any single
metric.

Useful local measures:

- static author adversary: train on original text, test on privatized text
- adaptive author adversary: train/test on privatized text when enough author
  labels exist
- HSD utility: local classifier and optional Hugging Face probes
- cue retention: target/action/negation checks
- residual leakage: built-in identifier and optional Presidio checks
- semantic drift: optional sentence-transformer or lightweight similarity
- operational cost: runtime, dependencies, model/cache size, determinism

## Repo-Specific Notes

| Repo | Takeaway | Build Action |
| --- | --- | --- |
| [DPMLM](https://github.com/sjmeis/DPMLM) | Masked-LM DP rewriting is a serious candidate source, but it is stochastic and parameter-sensitive. | Keep as optional bounded spike and reranker-only candidate generator. Do not make default. |
| [Diffractor](https://github.com/sjmeis/Diffractor) | Packaged word-level metric DP with fast perturbation and automatic embedding cache. | Best next optional adapter to try after DPMLM. Run on small samples first because it lowercases text and may affect HSD cues. |
| [MLDP](https://github.com/sjmeis/MLDP) | Unified benchmark suite for several word-level metric DP mechanisms. | Mine for mechanism comparison and experiment design. Direct use is embedding-heavy. |
| [SANTEXT](https://github.com/sjmeis/SANTEXT) | Natural text sanitization is a useful baseline class. | Treat as comparison baseline if time permits. Avoid making it part of core dependencies. |
| [EpsilonDistributor](https://github.com/sjmeis/EpsilonDistributor) | Budget distribution matters as much as the rewrite mechanism. | Implement a small heuristic privacy-pressure allocator in our codebase. |
| [DP-Decompose-Distribute](https://github.com/sjmeis/DP-Decompose-Distribute) | Chunking plus budget allocation is useful, and its eval setup includes attacker variants. | Borrow the chunking/evaluation ideas. Do not run the full FineWeb/Word2Vec workflow during the hackathon. |
| [CLMLDP](https://github.com/sjmeis/CLMLDP) | Collocations are a known weakness for word-level DP. | Add phrase-aware protect/rewrite rules before adding more DP mechanisms. |
| [PPDPTR](https://github.com/sjmeis/PPDPTR) | Post-processing can improve utility and human acceptance of DP rewrites. | Build local repair/reject validators rather than depending on token/HF-heavy post-processing. |
| [PrivFill](https://github.com/sjmeis/PrivFill) | Infilling-based DP rewriting may improve fluency but pulls in larger HF models. | Defer unless deterministic and DPMLM/Diffractor candidates underperform badly. |
| [DPNONDP](https://github.com/sjmeis/DPNONDP) | Prompting can be compared against DP methods, but generic prompting is risky here. | Use only as literature support for why constrained local generation must be validated. |
| [DPST](https://github.com/sjmeis/DPST) | Semantic triples are interesting for document generation privacy. | Defer; setup requires local vector DB, corpus preparation, clustering, and generation models. |
| [privacy-judge](https://github.com/sjmeis/privacy-judge) | Human/LLM privacy perception can help frame limitations. | Use for presentation framing only. Do not use LLM-as-judge as the primary evaluator. |

## Concrete Backlog

1. Add a `Diffractor` optional candidate adapter.
   - Extra: likely `diffractor = ["dp-diffractor>=..."]` after version check.
   - CLI: `generate-diffractor-candidates`.
   - Output: candidate CSV plus JSON audit compatible with reranking.
   - First test: sample 100, compare against `balanced` and
     `balanced --style-scrub`.

2. Add a lightweight privacy-pressure allocator.
   - Inputs: detector spans, cue checks, token-action features, optional author
     labels.
   - Output: per-token actions such as `freeze`, `mask`, `generalize`,
     `rewrite_low`, `rewrite_high`.
   - Use it first as a reranker feature, not as a hard dependency.

3. Add phrase-aware chunk protection.
   - Start with local bigram/trigram counts and existing cue lexicons.
   - Protect HSD cue phrases.
   - Flag recurring non-HSD phrases as author-risk candidates.

4. Add post-DP candidate validation.
   - Centralize reject reasons so DPMLM, Diffractor, local LLM, and future
     adapters are scored consistently.
   - Report aggregate reject reasons in audit JSON.

5. Extend author-risk evaluation when official author labels arrive.
   - Keep the existing static adversary.
   - Add adaptive adversary only when repeated author labels are sufficient.
   - Report privacy gain alongside HSD utility retention.

6. Add an experiment manifest template.
   - Record package versions, epsilon, seeds, runtime, model/cache paths,
     changed rows, accepted candidates, rejected candidates, and metric deltas.
   - Store runs under ignored `data/outputs/`.

## Promotion Rules

Promote an optional repo-backed method only if it beats the current reranked
deterministic alternatives on a bounded sample and does not weaken the core
contract.

Minimum bar:

- exact CSV shape and row order preserved
- no required external API calls
- audit output available
- HSD cue retention remains high
- residual identifier leakage does not increase
- author-risk score improves when author labels are available
- runtime and dependencies are acceptable for the challenge deadline

If a method only improves fluency or novelty but fails privacy, utility, or
operational checks, keep it as presentation context rather than submission code.
