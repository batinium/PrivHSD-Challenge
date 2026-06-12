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

Merged public bundle baseline added on 2026-06-11:

| Dataset | Rows | Output | Validation | Changed text cells | Identifier before/after | Target cue retention | Utility cue retention | Character retention |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `data/public_dev/recommended_merged.csv` | 159,668 | `data/outputs/recommended_merged.balanced.csv` | exact format valid | 26,941 | 40,304 -> 5 | 0.9999 | 0.9999 | 0.9721 |

The merged balanced manifest is
`data/outputs/recommended_merged.balanced.manifest.json`. It reduced direct
identifier detections from 33,032 to 4 and quasi-identifier detections from
7,272 to 1. Remaining warning counts: 5 residual privacy rows, 17 target-cue
loss rows, 1,324 low character-retention rows, 221 high-placeholder-density
rows, and 210 high-mask-density rows. This makes the merged bundle the new
default public regression benchmark, while Dynahate remains the cleanest
single-source comparison to older results.

Source-aware merged regression report added on 2026-06-12:

```text
data/outputs/recommended_merged.balanced.source_regression.json
```

Command:

```bash
.venv/bin/python -m privhsd.cli source-regression-report \
  --original data/public_dev/recommended_merged.csv \
  --protected data/outputs/recommended_merged.balanced.csv \
  --original-text-col text \
  --protected-text-col text \
  --id-col id \
  --group-col source \
  --group-col label \
  --group-col split \
  --group-col platform \
  --group-col type \
  --output data/outputs/recommended_merged.balanced.source_regression.json
```

Overall metrics: 159,668 rows, changed-text rate 0.1687, identifiers
40,304 -> 5, direct identifiers 33,032 -> 4, quasi identifiers 7,272 -> 1,
target cue retention 0.9999, utility cue retention 0.9999, action cue
retention 0.9991, negation/modality retention 0.9989, character retention
0.9721, 139 utility-loss rows, 203 context-loss rows, and 11 rationale-loss
rows. Rationale preservation was 47,729/47,740 spans, or 0.9998 retention,
across 26,909 rows with parsed HateXplain token ranges or Toxic Spans
character ranges. The report includes source/label/split/platform/type groups,
top risky groups, warning counts, context-tag counts, and row IDs only.

LM Studio context-labeler benchmark scaffolding was added on 2026-06-12 as
`privhsd benchmark-lm-context`. The original localhost/Tailscale checks wrote
structured blocked artifacts: `data/outputs/lm_context_benchmark.summary.json`
for localhost (`connection refused`, 0.0347s) and
`data/outputs/lm_context_benchmark.tailscale.blocked.json` for the Tailscale
endpoint (`timed out`, 2.0379s).

The user later provided a reachable LM Studio endpoint:

```text
http://169.254.83.107:1234
```

`/v1/models` returned 22 IDs, including `qwen3-0.6b`,
`liquid/lfm2-1.2b`, `liquid/lfm2.5-1.2b`, `qwen/qwen3-1.7b`,
`microsoft/phi-4-mini-reasoning`, `mistralai/ministral-3-3b`,
`qwen/qwen3-4b`, `nvidia/nemotron-3-nano-4b`,
`qwen/qwen3-4b-2507`, several Gemma variants, `openai/gpt-oss-20b`,
and embedding models. During the later WSL benchmark run, that link-local
endpoint stopped accepting TCP; the working WSL endpoint was:

```text
http://172.21.96.1:1234
```

The parser was hardened for harmless wrappers and variants such as fenced JSON,
JSON arrays of tags, alias keys, boolean tag fields, and explicit empty
structured outputs. Controlled smoke/sample20/sample100 reports are aggregated
in `data/outputs/lm_context_benchmark.summary.json`. The best parse/speed
candidates still failed the utility/safety bar:

| Model | Sample | Parse valid | p50 latency | Rows/sec | Agreement | Maskable cue violations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `liquid/lfm2-1.2b` | 20 | 1.0 | 0.3051s | 2.2848 | 0.0625 | 3 |
| `mistralai/ministral-3-3b` | 100 | 1.0 | 1.1017s | 0.9268 | 0.1525 | 9 |
| `qwen/qwen3-4b-2507` | 20 | 1.0 | 0.8756s | 0.8739 | 0.1663 | 3 |
| `nvidia/nemotron-3-nano-4b` | 20 | 0.25 | 1.2649s | 0.0748 | 0.4133 | 0 |

Decision: do not integrate LM Studio context labels into deterministic rules or
reranking yet. Use deterministic context/rationale/cue checks as the trusted
signal; keep local LM context labels as optional exploratory diagnostics.

Qwen 3 candidate-generation integration was tested on 2026-06-12 through the
working WSL LM Studio gateway:

```text
http://172.21.96.1:1234/v1/chat/completions
```

The tested model was `qwen/qwen3-4b-2507`. The code path now sends
source/label metadata to `generate-llm-candidates`, uses source/label
round-robin sampling, and rejects rewrite candidates that lose target, utility,
action, or negation/modality cues. A label-aware context benchmark parsed
100/100 rows with p50 latency 0.7684s and 1.204 rows/sec, but deterministic-tag
agreement remained low at 0.2226 and there was 1 maskable cue violation. On a
source/label-stratified 80-row candidate run, Qwen accepted 43 candidates and
rejected 37 by checks; rejection reasons included unchanged output, target cue
loss, residual direct identifiers, length drift, utility cue loss, and action
cue loss. Reranking selected `rewrite:qwen_candidate` for only 1/80 rows, with
`balanced` selected for 50 and `style_scrubbed` for 29. The final reranked
sample had zero residual identifiers and zero conservative HSD cue-loss rows,
with action and negation/modality retention both at 1.0.

Decision: Qwen is safe enough only as a constrained optional candidate source
behind strict validation and reranking. It should not replace the deterministic
baseline, and it should be considered for an official alternate only if upload
budget allows. Summary artifact:
`data/outputs/recommended_merged.qwen_stratified80.qwen_experiment_summary.json`.

Semantic triage was added after the Qwen experiment to make the fallback policy
explicit. The new `semantic-triage-report` command does not rewrite text or call
Qwen. It ranks already-privatized rows into `repair_before_model_review`,
`qwen_semantic_check`, and `no_review` using deterministic context tags,
conservative cue checks, optional trained classifier confidence/margin, and
source labels. On the Qwen stratified 80-row sample, deterministic fallback
triage selected 21 rows for review: 2 hard repair rows due to lost
quoted/reported context and 19 rows for selective Qwen semantic checking. The
artifact is:
`data/outputs/recommended_merged.qwen_stratified80.semantic_triage.json`.

A larger 20,000-row source/label-stratified exact-format triage sample completed
in 38.92s on one CPU core with `--privacy-scan changed`. It selected 4,887 rows
for review: 84 hard repair rows, 4,803 Qwen semantic-check rows, and 15,113
no-review rows. The report returned the top 500 review rows and truncated the
remaining 4,387. This confirms that triage should be sampled or parallelized for
interactive use; full semantic triage is an overnight CPU job unless the
deterministic regex/context layer is rewritten for parallelism.

Decision: this is the robust path. Deterministic masking remains the safe
baseline, a trained model supplies confidence/margin uncertainty when available,
and Qwen is consulted only on the semantic review queue.

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
downloaded. A protected-token candidate generator now uses the low-level DPMLM
API with `FacebookAI/roberta-base`, per-row seeding, strict frozen-token policy,
and reranking-only output. Safe default eligibility (`min_eligible_score=5`)
accepted 0/8 first-row candidates because likely rewrite targets overlapped
protected HSD/style signals. A looser `min_eligible_score=4` sample accepted
11/12 candidates in 4.9143s, but reranking selected 0 DPMLM candidates over
deterministic alternatives. DPMLM remains optional evidence, not a submission
path.

## Recommended Merged Dataset Inspection

Path: `data/public_dev/recommended_merged.csv`

Schema:

```text
id,text,label,source,split,target,type,platform,source_id,severity,target_categories,rationale_spans,meta
```

Aggregate inspection:

- rows: 159,668
- file size: 58 MB
- no blank `text` values
- no duplicate merged `id` values
- text length: p25 46, p50 86, p75 154, p95 340, p99 602, max 2,374
- normalized duplicate text: 519 duplicate groups, 2,343 rows
- cross-source duplicate text: 64 groups, 245 rows
- `source_id` is unique within every source, so it is not an author label
- `rationale_spans` is present for 26,912 rows, mainly HateXplain and Toxic
  Spans
- `severity` is present for 39,565 Measuring Hate Speech rows
- `target_categories` is present for 70,198 rows

Source composition:

| Source | Rows | Labels | Useful metadata |
| --- | ---: | --- | --- |
| `dynahate` | 41,144 | hate/not_hate | target/type, train/dev/test split |
| `measuring_hate_speech` | 39,565 | hate/not_hate/ambiguous | continuous severity, target categories, harm-score metadata |
| `davidson` | 24,783 | hate/offensive/not_hate | noisy Twitter offensive-vs-hate contrast |
| `hatexplain` | 20,148 | hate/offensive/not_hate | targets and rationale spans for 56.65% of rows |
| `toxic_spans` | 16,100 | toxic/not_abusive | toxic-span preservation for 96.27% of rows |
| `hatemoji_build` | 5,912 | hate/not_hate | emoji/leetspeak adversarial construction |
| `convabuse` | 4,185 | abuse/not_abuse/ambiguous_abuse | conversational-AI platform, directness/bot metadata |
| `hatemoji_check` | 3,930 | hate/not_hate | compact emoji functional tests |
| `hatecheck` | 3,901 | hate/not_hate | compact protected-group and functionality tests |

Global label distribution:

| Label | Rows |
| --- | ---: |
| `not_hate` | 57,442 |
| `hate` | 50,775 |
| `offensive` | 24,951 |
| `toxic` | 16,019 |
| `ambiguous` | 6,215 |
| `not_abuse` | 3,544 |
| `abuse` | 580 |
| `not_abusive` | 81 |
| `ambiguous_abuse` | 61 |

Important interpretation:

- The bundle is strong for utility, cue-retention, robustness, and legal
  over-restriction testing.
- It is still weak for true authorship-risk evaluation because there is no
  repeated author/user column.
- `source_id` should not be used as an author adversary target; every source
  has unique nonblank source IDs.
- `offensive`, `toxic`, `ambiguous`, and `abuse` labels should not be collapsed
  blindly into binary hate. They are valuable because they test the legal
  distinction between offensive speech, toxicity, abuse, and hate speech.
- The rationale/span fields create a new measurable target: privatization
  should preserve the words/spans that explain HSD or toxicity labels unless
  they are true identifiers.

Merge audit and caveats:

- The merge is meaningful as a public regression/evaluation bundle: every
  source was normalized into the same 13-column schema, all merged IDs are
  source-prefixed, `source_id` is preserved, `meta` is valid JSON for every
  row, and row provenance remains recoverable from the archived normalized
  files under `data/public_dev/archive/normalized/`.
- It is not meaningful as one undifferentiated training table. The `label`
  column is a source-normalized top-level label, not a single legal ontology.
  `hate`, `offensive`, `toxic`, `abuse`, `ambiguous`, and `not_hate` must stay
  source-aware unless an explicit mapping policy is documented for an
  experiment.
- Some rows are synthetic or adversarial by design, not necessarily AI
  generated. Dynahate, HateCheck, and Hatemoji use `platform=synthetic` because
  they are challenge/test-suite style resources. That is useful for functional
  regression, but these rows should not be presented as natural social-media
  prevalence evidence.
- Some derived labels are created by the normalizer and must be treated as
  documented proxies. Measuring Hate Speech maps continuous/ordinal harm scores
  into `hate`, `ambiguous`, and `not_hate` using the policy stored in `meta`;
  `severity` preserves the continuous score and is the better signal for drift
  analysis.
- The `type` column is intentionally overloaded. Depending on source it means
  hate subtype, functional test category, toxic-span type, ConvAbuse category,
  or the synthetic value `severity_score`. Do not aggregate `type` globally.
- The `target` and `target_categories` columns are heterogeneous. Dynahate and
  Hatemoji include shorthand target codes, HateXplain uses target names, and
  Measuring Hate Speech uses target indicator names. Use these for grouping and
  cue checks, not as a single normalized protected-characteristic taxonomy
  until a separate target normalizer exists.
- `rationale_spans` is also source-dependent: HateXplain uses token-index
  ranges, while Toxic Spans uses character-offset ranges. Any parser must branch
  on `source`.
- `platform` is useful provenance, but Measuring Hate Speech currently carries
  numeric platform codes from the raw file. Decode or document those codes
  before using platform as a presentation variable.
- For most pipeline commands only `id`, `text`, `label`, and `source` are
  required. Keep the other columns in the merged CSV for audit and evaluation,
  but create slim source-specific views for experiments that do not need
  `meta`, `severity`, targets, or rationales.

## Model-Backed Plan

Do not train a new attention mechanism first. The available data is better used
for evaluation, reranking, and small calibration tests. The practical plan is:

The mentor-adjacent DP NLP literature review in
`docs/research/dp_text_privacy_literature_notes.md` supports this direction: DPMLM and
word-level metric DP are serious candidate baselines, but the strongest
defensible architecture is selective cue protection, privacy-pressure
allocation, post-processing/reranking, and empirical adversarial evaluation.

| Component | Role | Default? |
| --- | --- | --- |
| Local TF-IDF classifiers | HSD utility proxy and author-risk adversary. | Optional, lightweight |
| `facebook/roberta-hate-speech-dynabench-r4-target` | Dynabench-aligned HSD utility evaluator. | Optional |
| `cardiffnlp/twitter-roberta-base-hate-latest` | Social-media hate/offensive utility evaluator. | Optional |
| HateXplain models | Target/rationale cue checks and explainability support. | Optional |
| `unitary/toxic-bert` or Detoxify | Toxicity proxy for weak-signal comparison only. | Optional |
| Weak token-action tagger | Optional detector/reranker feature trained from weak local labels. | No |
| Filtered Presidio augmentation | Optional high-recall entity candidate for reranking/submission alternates. | No |
| DPMLM | Protected-token candidate generator and bounded epsilon/runtime/utility reports. | No |
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

## Next Experiment Phase With The Merged Public Bundle

Official challenge files are not available yet, but the merged public bundle is
now large and diverse enough to become the main local regression suite. Continue
keeping core `privhsd anonymize` deterministic and dependency-light, but use
`recommended_merged.csv` to measure behavior by source, label, target category,
severity band, and rationale/span availability.

Recommended order:

1. Source-aware regression report:
   - add or script a report over original/protected CSV pairs grouped by
     `source`, `label`, `split`, `platform`, and `target_categories`
   - report privacy warnings, target-cue loss, utility-cue retention,
     character retention, and changed-cell rate per group
   - start from the completed balanced exact-format output:
     `data/outputs/recommended_merged.balanced.csv`
   - use this before tuning, because one global average can hide failures on
     HateCheck, Hatemoji, HateXplain, or vulnerable-group slices
2. Rationale/span preservation:
   - parse `rationale_spans` for HateXplain and Toxic Spans rows
   - measure whether privatization preserves rationale-bearing tokens/spans
     after identifier masking
   - flag cases where a rationale span is replaced by `[PERSON]`,
     `[LOCATION]`, or another placeholder, because those are either true
     privacy wins or dangerous utility losses
   - add this as a stronger utility check than dictionary cue retention alone
3. Measuring Hate Speech severity drift:
   - use the `severity` column as a continuous utility target
   - compare original/protected classifier score drift by severity band, not
     just binary agreement
   - explicitly track ambiguous and supportive/counterspeech regions instead
     of forcing them into hate/not_hate
4. Legal over-restriction stress tests:
   - use Davidson `offensive` rows, Toxic Spans `toxic` rows, ConvAbuse
     ambiguous rows, HateCheck contrastive cases, and Hatemoji perturbations
     to test that the tool does not equate offense or toxicity with hate
   - record false-positive-sensitive slices in the final pitch as Article 10
     evidence
5. Functional cue regression:
   - run `check-hsd-cues` on balanced and style-scrubbed outputs grouped by
     HateCheck functionality and Hatemoji subset
   - treat any systematic target/action/negation loss in these compact suites
     as a blocker before official submission
6. LM Studio small-model context-labeler stress test:
   - evaluate local Qwen/LFM/Phi/Mistral/Nemotron/Gemma models as advisory
     context labelers, not direct anonymizers
   - test multiple parse modes because small models may fail strict JSON:
     strict JSON, tagged lines, comma-separated word lists, and simple
     binary-tag outputs
   - start with sample 20 across all reachable models, then sample 100 for
     promising models
   - compare speed, parse-valid rate by mode, timeout rate, agreement with
     deterministic context tags, negation/counterspeech/quotation detection,
     and whether protected phrases cover target/action/negation/rationale cues
   - use useful small-model output as teacher data or reranker features only
     after deterministic validators pass
   - write aggregate model leaderboards under `data/outputs/` and progress
     notes under `docs/archive/agent_notes/overnight_progress.md`
7. Reranking on the merged bundle:
   - run bounded source-stratified samples first, then full merged reranking if
     runtime is acceptable
   - compare `balanced`, `style_scrubbed`, `privacy`, `target_generalized`,
     and `presidio_augmented` by source and label
   - do not select a global alternate unless it improves hard slices without
     harming Article 10-sensitive offensive/counterspeech slices
8. HF utility model runs:
   - status on Dynahate: bounded runs complete in `.venv` with CPU Torch and
     Transformers
   - next: run stratified samples from `recommended_merged.csv`, not only the
     first N rows
   - keep model results source-aware because toxicity, offensive language,
     abuse, and hate labels are not interchangeable
9. Author-risk search remains open:
   - this merged bundle does not provide repeated author IDs
   - keep `evaluate-author-risk` ready for official data or a later dataset
     with stable repeated user labels
   - do not misuse unique `source_id` as an author label

Longer-running optional paths:

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
3. Local LLM candidate generation and context labeling:
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
   - new experiment direction: use small local models as **context labelers**
     rather than final rewriters. Candidate models currently available in LM
     Studio may include `qwen3-0.6b`, `liquid/lfm2-1.2b`,
     `liquid/lfm2.5-1.2b`, `qwen/qwen3-1.7b`,
     `microsoft/phi-4-mini-reasoning`, `mistralai/ministral-3-3b`,
     `qwen/qwen3-4b`, `nvidia/nemotron-3-nano-4b`,
     `qwen/qwen3-4b-2507`, `google/gemma-4-e2b`, and
     `google/gemma-3n-e4b`; discover exact IDs through LM Studio `/v1/models`
   - context-labeler output can be strict JSON, tagged lines, word lists, or
     binary tags; the benchmark should select the most reliable parse mode per
     model
   - rank models by schema-valid rate, speed, context usefulness, and safety
     against target/action/negation/rationale cue loss
   - use best models for teacher labels, uncertainty scoring, or reranker
     features, not as direct anonymization output
4. DPMLM rewrite spike:
   - status: protected-token candidate generator implemented as
     `generate-dpmlm-candidates`
   - default policy freezes target terms, utility/action cues,
     negation/modality, stopwords, capitalized tokens, repeated-letter tokens,
     placeholders, and punctuation
   - real `FacebookAI/roberta-base` safe-default sample accepted 0/8 because no
     safe rewrite targets remained
   - looser min-score-4 sample accepted 11/12 in 4.9143s, but reranking selected
     0 DPMLM candidates
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
`docs/archive/agent_notes/current_handoff.md` with concise aggregate results.

Scaling note from the first full merged run: `create-submission` completed and
validated exact format on 159,668 rows, but it performs all row transformations
and aggregate metrics before writing the output file. If merged-bundle
experiments become iterative, add streaming output plus optional metric
sampling/grouped summaries so full-dataset runs are not the bottleneck.

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

### 3a. Context Labeling And Token-Action Policy

Status: partially implemented through deterministic target/action/negation cue
checks, weak token-action labels, local LLM candidate validation, and reranking.
The next step is to make context awareness explicit and measurable.

Desired pipeline:

```text
row text
  -> deterministic context tags
  -> optional small local LLM context-labeler advisory JSON
  -> token-action policy
  -> deterministic masking/style scrub
  -> cue/privacy validators
  -> reranker
```

The small LLM should not rewrite the final text directly. It should only
propose context tags and phrase-level advice:

- protected phrases: target groups, hostile actions, negation, modality,
  counterspeech, quote/reporting markers, rationale spans
- maskable phrases: identifiers, direct metadata, author style only
- uncertainty and reason codes for audit/reranking

Evaluation must compare local models by speed and usefulness. Good small-model
candidates in the current LM Studio setup include Qwen 0.6B/1.7B/4B variants,
Liquid LFM2 1.2B variants, Phi-4-mini-reasoning, Ministral 3B, Nemotron nano
4B, and Gemma variants. The target is not maximum model quality at any cost;
the target is a fast advisory model that improves context-sensitive protection
without becoming a required dependency. Strict JSON is useful when it works,
but small models should also be tested with simpler tagged-line, word-list, and
binary-tag formats.

### 3b. Role-Aware Token Policy Fine-Tuning

Status: planned methodological extension. Do not replace the first official
`balanced` submission with this. Implement only as an optional context scorer,
review router, or reranker feature until it proves a better official
privacy/HSD tradeoff.

#### Goal

Train a small token-level policy model that helps separate:

```text
HSD utility cues      -> preserve
author identity cues  -> mask, generalize, normalize, or review
```

The model must not be a generative anonymizer and must not be a legal
hate-speech classifier. It predicts token or span roles/actions. The existing
deterministic pipeline, cue checks, exact-format validation, and reranker remain
the final authority.

The intended methodological claim:

> We use public HSD datasets to learn a context-conditioned token policy for
> privacy transformation. Labels, targets, and rationales teach which words
> carry HSD utility; deterministic privacy detectors teach which spans carry
> author/privacy risk. The learned policy proposes protect/mask/normalize/review
> actions, while deterministic validators prevent target/action/negation loss.

#### Model To Train

Default model:

```text
FacebookAI/roberta-base
```

Link: <https://huggingface.co/FacebookAI/roberta-base>

Why this default:

- MIT license on the Hugging Face model card.
- Case-sensitive, which matters because casing is an author-style signal and
  can also carry social-media emphasis.
- RoBERTa is intended to be fine-tuned for downstream tasks including token
  classification.
- It uses the same general Transformers stack already used by optional HF and
  DPMLM experiments in this repo.
- It is smaller and easier to explain than a large generative model.

Training API:

- Hugging Face token classification task guide:
  <https://huggingface.co/docs/transformers/tasks/token_classification>
- Use `AutoTokenizer` and `AutoModelForTokenClassification`.
- Use offset mappings to align weak character/token labels to subword tokens.
- Use `DataCollatorForTokenClassification` and `Trainer` if the optional
  dependency stack is available.

Optional domain ablation after the default works:

```text
cardiffnlp/twitter-roberta-base
```

Link: <https://huggingface.co/cardiffnlp/twitter-roberta-base>

Why consider it:

- It is a RoBERTa-base model trained on Twitter data.
- The model card describes training on roughly 58M tweets and TweetEval usage.
- The challenge datasets are largely short, noisy, social-media-like text.

Why not default:

- Add only after model-card/license review and after the RoBERTa-base path
  works.
- Its model card recommends replacing usernames and links with placeholders,
  which can conflict with our need to identify handles/URLs as privacy spans.
  If used, preserve original offset alignment and treat the preprocessing as a
  model-input-only view, not as the output text.

Optional later ablation:

```text
vinai/bertweet-base
```

Link: <https://huggingface.co/vinai/bertweet-base>

Why consider it:

- The model card describes BERTweet as a large-scale English Tweet model trained
  with a RoBERTa-style procedure over a very large tweet corpus.

Why defer:

- More tweet-specific preprocessing/citation considerations.
- More moving parts under hackathon time pressure.

#### Data Available

Use the normalized public bundle already downloaded locally:

```text
data/public_dev/recommended_merged.csv
```

Observed local shape on 2026-06-12:

```text
source rows:
  dynahate                 41,144
  measuring_hate_speech    39,565
  davidson                 24,783
  hatexplain               20,148
  toxic_spans              16,100
  hatemoji_build            5,912
  convabuse                 4,185
  hatemoji_check            3,930
  hatecheck                 3,901

top labels:
  not_hate                 57,442
  hate                     50,775
  offensive                24,951
  toxic                    16,019
  ambiguous                 6,215
  not_abuse                 3,544
  abuse                       580
  not_abusive                  81
  ambiguous_abuse              61
```

The merged schema is:

```text
id,text,label,source,split,target,type,platform,source_id,severity,
target_categories,rationale_spans,meta
```

Use source-aware sampling. Do not train on one undifferentiated label ontology.
`hate`, `offensive`, `toxic`, `abuse`, `ambiguous`, and `not_hate` are
source-aware context signals, not interchangeable legal labels.

#### Corpus Use Plan

Use `data/public_dev/recommended_merged.csv` as the primary corpus. It is
already normalized and deduplicated enough for development. Do not train from
the raw archived files unless the normalized merge has a bug or a source needs
special parsing.

Recommended source roles:

| Source | Use in token policy |
| --- | --- |
| `dynahate` | Main hate/not-hate target/type signal; good first smoke source. |
| `hatexplain` | Strongest target+rationale supervision for `PROTECT_TARGET` and `PROTECT_HSD`. |
| `toxic_spans` | Character-span rationale supervision for toxic cue preservation. |
| `hatecheck` | Functional guardrail for protected groups, negation, contrast, and non-hate cases. |
| `hatemoji_build` / `hatemoji_check` | Emoji, leetspeak, perturbation, and style-robustness guardrails. |
| `davidson` | Offensive-vs-hate contrast; useful for over-restriction and `REVIEW`. |
| `measuring_hate_speech` | Target categories and severity; useful for multi-target/context hints. |
| `convabuse` | Abuse/not-abuse/ambiguous-abuse contrast; useful for adjacent-label review. |

Recommended splits:

- `smoke_500`: source/label round-robin, used only for weak-label and tokenizer
  alignment tests.
- `smoke_5000`: source/label round-robin, used for relation-table and
  scikit-learn token-action iteration.
- `train_30000`: source/label round-robin, first transformer fine-tuning run.
- `eval_guardrail`: hold out all or a fixed sample from `hatecheck`,
  `hatemoji_check`, and high-rationale HateXplain/Toxic Spans rows.

Do not collapse all labels into binary hate/not-hate for token-policy training.
Use labels as context features and review-priority hints.

#### Output Labels

MVP action labels:

```text
KEEP
MASK_IDENTIFIER
GENERALIZE_CONTEXT
PROTECT_TARGET
PROTECT_HSD
NORMALIZE_STYLE
REVIEW
```

Optional role labels for reports or a later multitask model:

```text
TARGET_OF_HATE
VICTIM_OR_PROTECTED_GROUP
AUTHOR_SELF_DISCLOSURE
QUOTED_OR_REPORTED_TARGET
COUNTERSPEECH_TARGET
PUBLIC_INTEREST_REFERENCE
AUTHOR_IDENTIFIER
AUTHOR_STYLE
HATE_ACTION
NEGATION_OR_MODALITY
UNCERTAIN_CONTEXT
```

Do not start with a complex multitask head unless the action-label path works.
The first implementation should train one token classification head over action
labels and write role counts/reasons into the training report.

#### Rights Constraints

Hard constraints for all agents:

- In `balanced` mode, target-group terms are preservation anchors, not masking
  targets.
- `PROTECT_TARGET` means keep the target term unchanged unless a human-reviewed
  official rule later says otherwise.
- Preserve historical-victim and vulnerable-group references by default.
- Preserve hostile actions, threats, exclusion, dehumanization, negation, and
  modality.
- Preserve counterspeech and quote/report markers so victim-protective or
  evidence-gathering speech is not converted into a false hate signal.
- Do not use a `hate` label as permission to remove the target group.
- Do not use a `not_hate` label as permission to ignore target/action/negation
  preservation.
- Author self-disclosures involving protected identity should route to `REVIEW`
  or cautious generalization, not automatic target masking.

Borderline example:

```text
"I am Muslim and I hate refugees"
```

Expected policy:

```text
I          KEEP
am         KEEP
Muslim     REVIEW or cautious GENERALIZE_CONTEXT  # author self-disclosure
and        KEEP
I          KEEP
hate       PROTECT_HSD
refugees   PROTECT_TARGET                         # target of hostility
```

The model should learn the difference between an author self-disclosure and a
target of hostility. The deterministic validator must still prevent accidental
target/action/negation removal.

#### Weak Supervision

Generate training labels from public data and existing deterministic rules.
Manual token labeling is not required for the MVP.

Weak label sources:

- Direct identifier detectors create `MASK_IDENTIFIER`.
- Quasi-identifier detectors create `GENERALIZE_CONTEXT`.
- Target dictionaries create `PROTECT_TARGET`.
- `target` and `target_categories` metadata reinforce `PROTECT_TARGET`.
- Hate/action cue lexicons create `PROTECT_HSD`.
- Threat, dehumanization, exclusion, negation, and modality terms create
  `PROTECT_HSD`.
- HateXplain token rationales create `PROTECT_HSD` unless they overlap a direct
  identifier.
- Toxic Spans character rationales create `PROTECT_HSD` unless they overlap a
  direct identifier.
- Counterspeech, quotation/reporting, and public-interest context markers
  create `PROTECT_HSD` or `REVIEW`.
- Hashtags, repeated punctuation, repeated letters, casing bursts, emoji, and
  symbol bursts create `NORMALIZE_STYLE` unless they overlap protected HSD
  cues.
- `ambiguous`, `ambiguous_abuse`, `offensive`, `toxic`, `abuse`, `not_abuse`,
  and `not_abusive` labels add review/context priority; they do not directly
  create hate/non-hate decisions.

Priority policy when labels conflict:

```text
direct handle/email/phone/url/id    -> MASK_IDENTIFIER
target/action/negation/modality     -> PROTECT_TARGET or PROTECT_HSD
author self-disclosure              -> REVIEW
quasi identifier                    -> GENERALIZE_CONTEXT
style marker                        -> NORMALIZE_STYLE
otherwise                           -> KEEP
```

Special case: if a token is both a target-group term and a possible
context-name/location candidate, prefer target protection in `balanced` unless
there is a strong direct-identifier signal. Do not let weak person/location
patterns erase vulnerable-group target evidence.

#### Label-Feature Relation Table

Before transformer fine-tuning, implement a transparent relation-table report.
This gives an explainable "attention-like" feature-importance layer and can
feed reranking even if transformer training is skipped.

Proposed command:

```bash
contextsafe-hsd label-feature-report \
  --input data/public_dev/recommended_merged.csv \
  --text-col text \
  --id-col id \
  --source-col source \
  --label-col label \
  --target-col target \
  --target-categories-col target_categories \
  --rationale-col rationale_spans \
  --output data/outputs/recommended_merged.label_feature_report.json
```

Report rows should aggregate, without raw text examples:

```text
feature_hash
feature_preview_safe     optional short feature only if non-sensitive and not official
feature_type             unigram, bigram, char_ngram, target_span, action_span,
                         negation, rationale_span, style_marker, identifier
source
label_or_label_set
row_count_with_feature
total_occurrences
mean_tfidf
document_frequency
label_frequency
log_odds_or_pmi
mean_span_length
position_bucket
suggested_policy         protect, mask_if_identifier, normalize, review, neutral
reason_codes
```

Do not include raw official examples. For official data, prefer hashes, counts,
row IDs, and safe feature categories over literal text dumps.

#### Implementation Tasks

Add a new optional module:

```text
privhsd/token_policy.py
```

Add optional dependency extra in `pyproject.toml`:

```toml
token-policy = [
  "transformers>=4.40",
  "torch>=2.1",
  "datasets>=2.19",
  "evaluate>=0.4",
  "seqeval>=1.2",
]
```

Add CLI commands:

```text
train-token-policy
predict-token-policy
apply-token-policy-candidates
label-feature-report
```

MVP command shapes:

```bash
contextsafe-hsd train-token-policy \
  --input data/public_dev/recommended_merged.csv \
  --text-col text \
  --id-col id \
  --source-col source \
  --label-col label \
  --target-col target \
  --target-categories-col target_categories \
  --rationale-col rationale_spans \
  --model-name FacebookAI/roberta-base \
  --sample-size 30000 \
  --sample-strategy source_label_round_robin \
  --max-length 192 \
  --epochs 1 \
  --batch-size 8 \
  --output-dir data/outputs/token_policy_roberta_base \
  --report data/outputs/token_policy_roberta_base.train.json
```

```bash
contextsafe-hsd predict-token-policy \
  --input data/public_dev/recommended_merged.csv \
  --text-col text \
  --id-col id \
  --source-col source \
  --label-col label \
  --target-col target \
  --target-categories-col target_categories \
  --rationale-col rationale_spans \
  --model-dir data/outputs/token_policy_roberta_base \
  --sample-size 1000 \
  --output data/outputs/token_policy_roberta_base.predictions.json
```

```bash
contextsafe-hsd apply-token-policy-candidates \
  --input data/public_dev/recommended_merged.csv \
  --output data/outputs/recommended_merged.token_policy_candidates.csv \
  --text-col text \
  --id-col id \
  --policy-predictions data/outputs/token_policy_roberta_base.predictions.json \
  --candidate-col token_policy_candidate \
  --audit data/outputs/recommended_merged.token_policy_candidates.audit.json
```

`apply-token-policy-candidates` must not write final official output directly.
It writes candidate text or candidate action columns for reranking. Final
submission still goes through `create-submission`, `rerank-candidates`, and
`validate-submission`.

#### Tokenization And Alignment

Implementation requirements:

- Use the raw original text as the label source.
- Tokenize with the model tokenizer using `return_offsets_mapping=True`.
- Add a metadata prefix only if needed:

  ```text
  <source=dynahate> <label=hate> <target=religion> original text...
  ```

- If a metadata prefix is used, assign `-100` labels to all prefix tokens so
  they do not contribute to token loss.
- Align text-token labels to model subwords by character offsets.
- Assign `-100` to special tokens.
- For subword tokens that overlap a labeled character span, assign the span's
  action label.
- For subword tokens that do not overlap any action span, assign `KEEP`.
- Store the label map in model metadata:

  ```json
  {
    "KEEP": 0,
    "MASK_IDENTIFIER": 1,
    "GENERALIZE_CONTEXT": 2,
    "PROTECT_TARGET": 3,
    "PROTECT_HSD": 4,
    "NORMALIZE_STYLE": 5,
    "REVIEW": 6
  }
  ```

- Preserve a model card/report locally with model name, revision if available,
  data source counts, weak-label policy, training args, and limitations.

#### Inference Policy

The trained model is advisory. Convert model predictions to action spans, then
apply deterministic guardrails:

- Deterministic direct identifiers always mask.
- Deterministic target/action/negation/modality protections override model
  `MASK_IDENTIFIER` in `balanced` mode unless the token is a direct identifier
  such as email/handle/phone/URL.
- If model confidence is low or roles conflict, route to `REVIEW`.
- The model may add style-normalization pressure but cannot delete protected
  HSD cues.
- The model may penalize reranker candidates that lose high-probability
  `PROTECT_TARGET` or `PROTECT_HSD` spans.
- The model may promote candidates that mask high-probability
  `MASK_IDENTIFIER` or `GENERALIZE_CONTEXT` spans.
- Final candidate must pass:
  - exact-format validation,
  - cue checks,
  - source regression,
  - residual privacy metrics.

#### Qwen Fallback For Uncertain Rows

Qwen remains the last-resort semantic review path, not the default model and
not the final rewriter.

Use Qwen only after deterministic and token-policy signals have already narrowed
the queue:

```text
balanced/reranked candidate
  -> deterministic cue/privacy checks
  -> role-aware token-policy predictions
  -> semantic-triage-report
  -> qwen_semantic_check queue only
  -> candidate validation/reranking
  -> exact-format validation
```

Rows should enter the Qwen queue when:

- the token-policy model emits low-confidence `REVIEW`;
- protected-target and author-self-disclosure roles conflict;
- target/action/negation cues appear to be lost;
- context tags such as counterspeech, quotation/reporting, or public-interest
  criticism are present and the transformation changed the row;
- source labels are ambiguous or adjacent (`ambiguous`, `offensive`, `toxic`,
  `abuse`) and deterministic checks are not enough;
- residual privacy warnings remain after deterministic masking.

Qwen output must be treated as advisory:

- It may propose semantic tags, uncertainty reasons, or one candidate rewrite.
- It must not decide legal hate speech.
- It must not change labels or metadata.
- It must not directly overwrite the official output.
- Any rewrite must pass target/action/negation retention, residual privacy
  checks, length-drift checks, reranking, and exact-format validation.

If Qwen does not improve official or bounded local tradeoff on the review
queue, keep it as a demo/evidence path only.

#### Immediate Testing Order

Start testing without transformer fine-tuning:

1. Verify corpus availability and schema:

   ```bash
   head -1 data/public_dev/recommended_merged.csv
   python -m privhsd.cli profile-dataset \
     --input data/public_dev/recommended_merged.csv \
     --text-col text \
     --id-col id \
     --label-col label \
     --source-col source \
     --output data/outputs/recommended_merged.profile.refresh.json
   ```

2. Run a very small existing weak token-action baseline first. Do not start at
   30k during interactive development:

   ```bash
   contextsafe-hsd train-token-action-tagger \
     --input data/public_dev/recommended_merged.csv \
     --text-col text \
     --id-col id \
     --sample-size 500 \
     --model data/outputs/token_action_tagger.smoke500.pkl \
     --output data/outputs/token_action_tagger.smoke500.json
   ```

3. If the 500-row smoke is sane, run a 5k source/label baseline or update
   `train-token-action-tagger` to support source/label round-robin sampling.
   Keep 30k as a batch job:

   ```bash
   contextsafe-hsd train-token-action-tagger \
     --input data/public_dev/recommended_merged.csv \
     --text-col text \
     --id-col id \
     --sample-size 5000 \
     --model data/outputs/token_action_tagger.smoke5000.pkl \
     --output data/outputs/token_action_tagger.smoke5000.json
   ```

4. Implement `label-feature-report` and inspect whether the relation table
   finds useful protect/mask/review signals by source and label.
5. Implement weak-label dataset export for token policy training and test it on
   a tiny sample first. Verify target terms are labeled `PROTECT_TARGET`.
6. Load `FacebookAI/roberta-base` as `AutoModelForTokenClassification` with
   seven labels and run a 100-row overfit smoke test before any large run.
7. Train a bounded sample (`sample-size 30000`, one epoch) only after tokenizer
   alignment and guardrail tests pass.
8. Feed predictions into candidate/reranking reports, not into official output.
9. Use Qwen only for the final uncertain queue produced by semantic triage.

When heading home / before model downloads:

- `FacebookAI/roberta-base` is already cached locally in this environment; still
  confirm cache before relying on offline mode.
- Do not download all optional models at once. Start with RoBERTa-base.
- Download `cardiffnlp/twitter-roberta-base` only after the RoBERTa-base
  training loop and guardrail tests work.
- Defer `vinai/bertweet-base` until tweet-specific preprocessing is worth the
  complexity.
- Keep all model outputs, checkpoints, and reports under ignored `data/outputs/`
  or the Hugging Face cache. Do not commit them.

#### Evaluation

Token-policy model metrics:

- token accuracy;
- macro-F1;
- per-action precision/recall/F1/support;
- confusion matrix;
- especially report recall for:
  - `MASK_IDENTIFIER`,
  - `PROTECT_TARGET`,
  - `PROTECT_HSD`,
  - `REVIEW`.

Pipeline metrics after applying token-policy candidates through reranking:

- target cue retention;
- action cue retention;
- negation/modality retention;
- rationale-span retention;
- residual direct identifiers;
- residual quasi identifiers;
- changed-text rate;
- character retention;
- source/label slice regressions;
- local utility model agreement where available;
- runtime and model size.

Acceptance criteria before using it as an official alternate:

- `balanced` remains the first official submission.
- Token-policy candidate must not reduce target/action/negation retention
  versus `balanced`.
- It must not mask target-group terms in `balanced` mode.
- It must reduce residual privacy/style risk or improve official tradeoff.
- It must pass exact-format validation.
- It must provide a clear report explaining what it changed and why.

Stop criteria:

- If the model mostly learns the weak rules without adding useful decisions,
  keep it as evidence only.
- If it masks target groups, hostile actions, negation, or counterspeech,
  reject it.
- If runtime or dependency cost is too high for the challenge, keep the
  relation table and scikit-learn weak tagger instead.
- If official metrics do not improve after one bounded alternate submission,
  do not scale it.

#### Agent Instruction

Use this task prompt for a future coding agent:

```text
Implement the planned role-aware token policy as an optional extension.
Do not change the default balanced submission path.

Start with label-feature-report and a weak-label dataset builder over
data/public_dev/recommended_merged.csv. Then add train-token-policy using
FacebookAI/roberta-base with AutoModelForTokenClassification. Align weak
character/token action labels to tokenizer offsets. Save model artifacts and
reports only under ignored data/outputs/.

The model predicts token actions, not final text. It is advisory only. Add
predict-token-policy and apply-token-policy-candidates so predictions can feed
reranking or semantic triage. Enforce hard constraints: never mask target-group
terms in balanced mode, preserve target/action/negation/modality, and route
author self-disclosure conflicts to REVIEW. Add focused tests for weak-label
generation, tokenizer alignment, metadata-prefix label masking, and guardrails.

Use Qwen only as a last-resort semantic checker for the uncertain review queue.
Do not use Qwen on the full dataset and do not let Qwen directly overwrite final
submission text.

Run ruff, vulture, pytest, and bounded sample reports. Document model link,
revision, training args, source/label counts, per-action metrics, and
limitations. Do not commit model weights, raw official examples, downloaded
datasets, or generated output.
```

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

### 4b. Source-Aware Regression And Rationale Checks

Status: implemented as `privhsd source-regression-report`. The report compares
an original CSV against an exact-format protected CSV by requested grouping
columns such as `source`, `label`, `split`, `platform`, and `type`. It reports
changed-text rate, identifier/direct/quasi counts, target/utility/action/
negation retention, deterministic context-tag loss, warning counts, risky
groups, and rationale preservation without raw text.

Rationale parsing is source-aware: HateXplain rows use token-index ranges and
Toxic Spans rows use character-offset ranges. A full
`recommended_merged.csv` vs `balanced` run completed on 2026-06-12 and found
0.9998 rationale-span retention, with 11 rationale-loss rows available by row
ID for review.

### 5. DPMLM Spike

Status: implemented as `privhsd dpmlm-spike` plus
`privhsd generate-dpmlm-candidates`. In the current local environment `dpmlm`
1.1.2 is installed and importable after NLTK resources are present. The spike
keeps backend/blocker reporting; the candidate generator uses the low-level
DPMLM token API with frozen HSD/privacy tokens, per-row deterministic seeding,
candidate validation, CSV helper-column output, and report JSON.

Direct library probes showed why this guard is needed: raw sentence rewrite can
modify protected HSD cues. Real `FacebookAI/roberta-base` experiments showed
the other half of the tradeoff: strict protection leaves no safe candidates in
the first local sample, while looser eligibility produces fluent-looking but
semantically risky rewrites that the reranker does not select.

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

Do not make DPMLM part of the core pipeline until it beats deterministic or
Presidio-reranked outputs on official or stronger local privacy/HSD metrics.

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

### 6a. Local LLM Context Labeler Benchmark

Status: implemented as `privhsd benchmark-lm-context`. This command does not
rewrite text. It benchmarks local LM Studio models as advisory context labelers
using strict JSON, tagged-line, word-list, and binary-tag formats, then reports
parse validity, latency, agreement with deterministic context tags, protected
phrase counts, maskable phrase counts, and blocker details. The 2026-06-12 run
could not reach localhost or the Tailscale endpoint, and later found that the
WSL-reachable LM Studio endpoint was `http://172.21.96.1:1234` rather than the
stale link-local address. The benchmark summary found no model suitable for
integration: the best parser-compliant models had low deterministic-tag
agreement and some maskable protected-cue violations.

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
augmented candidate is worth the utility drift. For official alternates, use
the reranked exact-format path (`rerank-candidates --replace-text
--presidio-augment`) rather than direct raw Presidio replacement.

Useful outputs:

- spans only Presidio catches
- spans only PrivHSD catches
- overlap
- false-positive risk on target-group/hate cues
- runtime and dependency cost

This makes Presidio evidence in the pitch rather than a fragile dependency.

## Judging Strategy

Status: a compact final pitch/demo outline and human-rights framing live in
`docs/challenge/final_pitch_outline.md`.

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
