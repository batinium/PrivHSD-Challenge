# Overnight Agent Prompt: PrivHSD Challenge Hardening

You are working in `/home/bati/projects/PrivHSD-Challenge`.

Your job is to work autonomously overnight on the PrivHSD system until the
project is materially stronger for the official challenge evaluator. Do not stop
after a shallow pass. Keep iterating through implementation, tests, experiments,
and documentation until you either meet the success criteria below or hit a
hard blocker that cannot be worked around.

## Mission

Build and validate a privacy-preserving text transformation system for hate
speech detection datasets.

The system must:

- preserve row count, row order, IDs, labels, and metadata;
- reduce direct identifiers, quasi-identifiers, and author-identifying style;
- preserve hate-speech detection utility;
- preserve target/action/negation/modality cues;
- avoid over-restricting offensive, insulting, toxic, political, satirical,
  counterspeech, or public-interest expression;
- preserve evidence of hate against vulnerable or historically targeted groups;
- be explainable, auditable, and compatible with human review.

This is not a generic PII scrubber, not a production hate classifier, not an
automated takedown system, and not a legal decision system.

## Read First

Start by reading these files:

1. `docs/real_data_playbook.md`
2. `docs/roadmap.md`
3. `docs/challenge_requirements.md`
4. `docs/human_rights_legal_test_plan.md`
5. `docs/methodology_justification.md`
6. `docs/pipeline_design.md`
7. `docs/dataset_plan.md`
8. `docs/official_submission_checklist.md`
9. `docs/final_pitch_outline.md`
10. `agents/current_handoff.md`
11. `agents/task_board.md`
12. `agents/coding_rules.md`

Also inspect the implementation before changing it:

- `privhsd/pipeline.py`
- `privhsd/detectors.py`
- `privhsd/style.py`
- `privhsd/metrics.py`
- `privhsd/rerank.py`
- `privhsd/cue_checks.py`
- `privhsd/dataset_profile.py`
- `privhsd/submission.py`
- `privhsd/cli.py`
- relevant tests under `tests/`

## Current Data

Public local data is available. The main public regression file is:

```text
data/public_dev/recommended_merged.csv
```

Raw and normalized public data are archived under:

```text
data/public_dev/archive/raw/
data/public_dev/archive/normalized/
```

Important caveat: `recommended_merged.csv` is an evaluation/regression bundle,
not one homogeneous training table. `label`, `target`, `type`, and
`rationale_spans` are source-aware. Do not blindly collapse `offensive`,
`toxic`, `abuse`, and `ambiguous` into `hate`. Do not use `source_id` as an
author label; it is unique within each source.

Generated outputs must go under ignored `data/outputs/`.

## Persistent Progress Memory

Keep a live markdown progress log while working. Create or update:

```text
agents/overnight_progress.md
```

Update it:

- after the initial test/profile pass;
- before and after each long-running experiment;
- after each model benchmark group;
- whenever a blocker or useful finding appears;
- at least every 60 minutes during a long overnight run.

Use this structure:

```text
# Overnight Progress

## Current Objective

## Completed Since Start

## Running Now

## Metrics Snapshot

## Model Benchmark Notes

## Blockers / Skips

## Next Action
```

Do not paste raw sensitive/hateful examples into the progress file. Use row IDs,
aggregate metrics, source names, and reason codes only.

## Initial Commands

Run these first:

```bash
git status --short
.venv/bin/python -m pytest -q
.venv/bin/python -m privhsd.cli profile-dataset \
  --input data/public_dev/recommended_merged.csv \
  --output data/outputs/recommended_merged.profile.json
```

If `.venv` is broken, use `python -m pytest -q` and repair the local
environment. Do not delete or reset user changes. Do not use destructive git
commands.

## Autonomy Rules

You may:

- search the web for current official docs, model cards, or research;
- use the Consensus MCP if available for research questions;
- use Hugging Face tooling and download models/datasets when useful;
- train small local models;
- run long CPU jobs if they produce measurable evidence;
- install optional dependencies into `.venv` if needed;
- add code, tests, docs, and CLI commands.

You must not:

- make Hugging Face, Presidio, spaCy, DPMLM, LLMs, or fine-tuned models required
  for the base `privhsd anonymize` path;
- commit/download model weights, caches, raw challenge data, or `data/outputs/`;
- paste raw hateful/sensitive examples into docs or final reports;
- rely on a remote paid API unless explicitly authorized by the user;
- replace the deterministic baseline with an opaque model;
- stop just because one optional model path fails.

If an optional path fails, write a structured skip/blocker report and continue
to the next path.

## Success Criteria

Do not stop until one of these is true:

### Total Success

All of the following are achieved:

- full tests pass;
- `profile-dataset` works on `recommended_merged.csv`;
- exact-format `balanced` output works on `recommended_merged.csv`;
- at least one source-aware regression report exists for original/protected
  comparisons;
- context/cue/rationale preservation is measured beyond global averages;
- local small-model context-labeler stress tests have been run or clearly
  blocked, with speed/usefulness results recorded;
- any implemented improvement beats or matches the current baseline without
  weakening HSD utility or legal framing;
- docs and handoff files are updated with exact commands, metrics, outputs, and
  remaining risks.

### Minimum Overnight Success

If total success is not feasible, achieve all of the following:

- full tests pass;
- implement at least one high-leverage missing evaluator or report;
- run it on `recommended_merged.csv` or a clearly justified source-stratified
  sample;
- run at least a small LM Studio context-labeler benchmark if LM Studio is
  reachable;
- record aggregate results and blockers in docs;
- leave the repo in a state where the official CSV can be profiled, processed,
  validated, and diagnosed immediately.

### Hard Blocker

Only stop for a hard blocker if:

- the same blocker recurs after at least three serious workaround attempts;
- no other useful implementation or experiment can proceed;
- you write a clear blocker note with the exact command, error, and next action.

## Minimum Metrics To Protect

Treat these as guardrails, not official scores:

- exact-format validation must pass;
- target cue retention should stay at or above `0.999` globally and should not
  show systematic loss on HateCheck/Hatemoji/protected-group slices;
- utility cue retention should stay at or above `0.999` globally;
- any candidate that lowers utility/cue retention must have a clear privacy win
  and be source-slice safe;
- residual identifier counts should not exceed the current `balanced` baseline
  on the same file;
- no candidate should erase protected-group target evidence by default;
- offensive/toxic/ambiguous/counterspeech rows must not be treated as automatic
  hate in reports or model mappings.

Current merged `balanced` baseline from prior run:

- rows: 159,668
- changed text cells: 26,941
- identifier detections: 40,304 -> 5
- direct identifiers: 33,032 -> 4
- quasi identifiers: 7,272 -> 1
- target cue retention: 0.9999
- utility cue retention: 0.9999
- character retention: 0.9721
- manifest: `data/outputs/recommended_merged.balanced.manifest.json`
- output: `data/outputs/recommended_merged.balanced.csv`

## Highest Priority Work

Work in this order unless local evidence shows a better order.

### 1. Build Source-Aware Regression Reporting

Implement a command or module that compares original and protected CSVs grouped
by source-aware slices.

Required inputs:

- original CSV;
- protected CSV;
- original text column;
- protected text column;
- ID column;
- grouping columns such as `source`, `label`, `split`, `platform`,
  `target_categories`, and possibly `type`.

Required aggregate outputs:

- row count per group;
- changed-text rate;
- identifier before/after;
- direct identifier before/after;
- quasi identifier before/after;
- target cue retention;
- utility cue retention;
- action cue retention if available;
- negation/modality retention if available;
- character retention;
- warning counts;
- top risky groups by privacy warnings and utility loss;
- no raw text.

Run it on:

```text
data/public_dev/recommended_merged.csv
data/outputs/recommended_merged.balanced.csv
```

If the full file is too slow, run source-stratified samples first, then optimize
or stream.

### 2. Improve Context Awareness Deterministically

Before adding a micro LLM, inspect existing cue/context logic and improve it if
needed.

Add or improve deterministic row-context tags such as:

- `protected_target`
- `historical_victim_group`
- `hostile_action`
- `threat`
- `dehumanization`
- `exclusion`
- `negated_hate`
- `counterspeech`
- `quoted_or_reported`
- `public_interest_or_institutional_criticism`
- `offensive_only_risk`
- `missing_context`

Use context tags for audit/reranking policy, not as legal conclusions. They can
be used to penalize candidates that lose critical cues or to identify slices
for reporting.

Add focused tests for:

- same target/action words with negation versus endorsement;
- counterspeech containing slurs or target terms;
- quotation/reporting of hateful words;
- offensive insult without protected target;
- protected group plus direct threat/exclusion;
- historical-victim group examples;
- public official/institution criticism without protected target.

### 3. Rationale/Span Preservation

Implement or prototype source-aware rationale/span preservation checks.

Rules:

- HateXplain `rationale_spans` are token-index ranges.
- Toxic Spans `rationale_spans` are character-offset ranges.
- Parser must branch on `source`.
- Do not print raw span text; report counts and row IDs only.

Measure:

- rows with rationale spans;
- rationale spans that overlap replacements/placeholders;
- rationale-bearing tokens/spans preserved after privatization;
- source-level and label-level retention.

Use this as a stronger utility check than dictionary cues alone.

### 4. LM Studio Small-Model Context Labeler Stress Test

The user has downloaded several small local models in LM Studio. Stress test
them for **context understanding**, not direct anonymization. The model should
produce advisory labels that help decide which words must not be masked.

Do not let an LLM directly produce the final privatized text unless the output
is validated and reranked. The best architecture is:

```text
row text
  -> deterministic cue/context detector
  -> small LLM context-labeler advisory JSON
  -> token-action/context policy
  -> deterministic masker/style scrubber
  -> validators/reranker
```

First discover the available LM Studio endpoint and model IDs:

```bash
curl -s http://127.0.0.1:1234/v1/models
curl -s http://100.120.207.64:1234/v1/models
```

Try localhost first. If neither endpoint is reachable, record a structured
blocker and continue with deterministic/HF work.

User-reported local models to try if available:

| Nickname | Expected model family / ID hint | Size | Quantization |
| --- | --- | ---: | --- |
| `qwen3-0.6b` | `lmstudio-community/qwen3-0.6b` or `qwen3-0.6b` | 0.6B | Q8_0 |
| `lfm2-1.2b` | `liquid/lfm2-1.2b` | 1.2B | Q8_0 |
| `lfm2.5-1.2b` | `liquid/lfm2.5-1.2b` | 1.2B | Q8_0 |
| `qwen3-1.7b` | `qwen/qwen3-1.7b` | 1.7B | Q6_K |
| `phi-4-mini-reasoning` | `microsoft/phi-4-mini-reasoning` | 3B | Q4_K_M |
| `ministral-3-3b` | `mistralai/ministral-3-3b` | 3B | Q8_0 |
| `qwen3-4b` | `qwen/qwen3-4b` | 4B | Q4_K_M |
| `nemotron-3-nano-4b` | `nvidia/nemotron-3-nano-4b` | 4B | Q4_K_M |
| `qwen3-4b-2507` | `qwen/qwen3-4b-2507` | 4B | Q8_0 |
| `gemma-4-e2b` | `google/gemma-4-e2b` | 4.6B | Q4_K_M |
| `gemma-3n-e4b` | `google/gemma-3n-e4b` | 6.9B | Q4_K_M |

Exact LM Studio model IDs may differ. Use `/v1/models` output as source of
truth.

Implement or reuse a benchmark command/script that sends a source-stratified
sample to each reachable model and tests **multiple output formats**. Small
models may fail strict JSON but still provide useful context signals as short
lists or tagged text. If no command exists, implement one. Suggested command
name:

```bash
.venv/bin/python -m privhsd.cli benchmark-lm-context \
  --input data/public_dev/recommended_merged.csv \
  --text-col text \
  --id-col id \
  --source-col source \
  --label-col label \
  --endpoint http://127.0.0.1:1234/v1/chat/completions \
  --model MODEL_ID \
  --sample-size 100 \
  --output data/outputs/lm_context.MODEL_ID.sample100.json
```

Test these modes, from strictest to most permissive:

1. `json`: ask for valid JSON only.
2. `tagged`: ask for one field per line with stable prefixes.
3. `word_lists`: ask for compact comma-separated lists only.
4. `binary_tags`: ask for yes/no tags plus protected words.

The strict JSON response requested from each model should look like:

```json
{
  "context_tags": [
    "protected_target",
    "hostile_action",
    "negated_hate",
    "counterspeech",
    "quoted_or_reported",
    "offensive_only_risk",
    "missing_context"
  ],
  "protected_phrases": ["phrase that must remain semantically visible"],
  "maskable_phrases": ["phrase likely to be identifier/style only"],
  "uncertainty": "low|medium|high",
  "reason_codes": ["target_action_preserved", "quote_marker_present"]
}
```

The tagged fallback can look like:

```text
TAGS: protected_target, hostile_action, negated_hate
PROTECT: group name; action phrase; not/never/should markers
MASKABLE: username; email; location if not target cue
UNCERTAINTY: low
REASONS: negation_present; target_action_present
```

The word-list fallback can look like:

```text
protected_words: word1, phrase two, phrase three
maskable_words: word4, phrase five
context_tags: counterspeech, quoted_or_reported
```

The binary-tags fallback can be even simpler:

```text
protected_target=yes
hostile_action=yes
negation=no
counterspeech=no
quoted_or_reported=yes
protect=phrase one; phrase two
mask=phrase three
```

Build parsers for these fallback formats if useful. They do not need to be
perfect, but they must be measurable and reject ambiguous output. The benchmark
should record the best parse mode per model and the failure modes.

Use short prompts and low `max_tokens` so models can be tested in bursts. Good
defaults:

- sample 20 for initial smoke across all models;
- sample 100 for promising models;
- temperature 0 or as low as LM Studio supports;
- max output tokens 160-256;
- timeout 20-60 seconds per row depending on model size;
- record schema-valid rate, timeout rate, invalid JSON rate, and latency.

Sample selection must be source/label/functionality aware. Include, when
available:

- HateCheck contrastive cases;
- Hatemoji perturbations;
- HateXplain rationale rows;
- Toxic Spans rationale rows;
- Measuring Hate Speech ambiguous/severity bands;
- Davidson offensive rows;
- protected-group plus threat/exclusion rows;
- counterspeech/quotation/negation patterns.

Evaluate each model on:

- parse validity by mode: JSON, tagged, word-list, binary-tags, or failed;
- rows/second and p50/p95 latency;
- agreement with deterministic context tags;
- ability to identify negation/counterspeech/quotation;
- whether protected phrases include target/action/negation cues;
- whether maskable phrases avoid target/action/rationale spans;
- uncertainty calibration;
- usefulness as a teacher for token-action training or reranker features.

Write aggregate model leaderboard output only, no raw text:

```text
data/outputs/lm_context_benchmark.summary.json
data/outputs/lm_context_benchmark.MODEL_ID.json
```

The most useful result is not necessarily the largest model or the best JSON
writer. Prefer the model with the best speed/usefulness tradeoff and the lowest
unparseable-output rate. A 0.6B or 1.2B model is valuable if it reliably
identifies context tags and protected/maskable phrases through any parseable
format.

If a model is promising, use it as a teacher or advisory scorer:

- generate context tags/protected phrases for a stratified sample;
- compare against deterministic tags;
- train or improve weak token-action/context rules;
- integrate only through validators/reranking, not direct final rewriting.

Update `agents/overnight_progress.md` after each model or model group.

### 5. Source-Stratified HF Utility Evaluation

If useful, run Hugging Face utility models on a source-stratified sample, not
just the first N rows.

Allowed examples:

- `facebook/roberta-hate-speech-dynabench-r4-target`
- `cardiffnlp/twitter-roberta-base-hate-latest`
- `unitary/toxic-bert`
- other well-justified public models after checking model cards

You may search the web or Hugging Face model cards. If using search, prefer
official docs/model cards. Record model ID, revision, runtime, sample size,
device, and skip reasons.

Do not make these models required for the core anonymizer.

### 6. Train Small Local Models Only If They Answer A Question

You may train local lightweight models when useful:

- source-aware TF-IDF utility classifiers;
- one-vs-rest or per-source utility probes;
- author-risk adversary only if repeated author/user labels exist;
- token-action uncertainty scorer.

Do not train a large transformer first. Do not commit checkpoints. Save metrics
and model artifacts only under `data/outputs/`.

### 7. Reranking Experiments

Run reranking only after the reporting above can show slice-level tradeoffs.

Compare:

- `balanced`;
- `balanced --style-scrub`;
- `rerank-candidates`;
- `rerank-candidates --presidio-augment`;
- any new context-aware reranking policy.

Do not select a global winner based only on a global average. Check hard slices:

- HateCheck functionality cases;
- Hatemoji perturbation cases;
- HateXplain rationale rows;
- Toxic Spans rationale rows;
- Measuring Hate Speech severity bands;
- offensive/toxic/ambiguous labels;
- protected and historical-victim groups.

## Web, Hugging Face, And Consensus Use

You are allowed to search the web. Use it when:

- model cards or package docs may have changed;
- you need current Hugging Face model details;
- you need official challenge/Council of Europe references;
- you are unsure about a legal/research claim.

When using search for technical claims, prefer primary sources: official docs,
model cards, papers, and repository docs.

If the Consensus MCP is available, use it for research questions like:

- best practices for hate speech utility evaluation;
- context-sensitive hate speech detection;
- authorship obfuscation evaluation;
- privacy-preserving text rewriting;
- rationale preservation in HSD.

When adding research-backed claims to docs, cite sources or record the source
names/URLs. Do not let research browsing replace implementation and measurement.

## Official Data Strategy

When the real CSV arrives, the runbook is:

1. `profile-dataset`
2. create exact-format `balanced`
3. `validate-submission`
4. local utility/cue/privacy evidence
5. official upload
6. diagnose official score
7. try one targeted alternate

Do not start with DPMLM, LLM rewriting, raw Presidio, broad target
generalization, or large model training.

## Commands To Keep Handy

Profile:

```bash
.venv/bin/python -m privhsd.cli profile-dataset \
  --input data/public_dev/recommended_merged.csv \
  --output data/outputs/recommended_merged.profile.json
```

Exact-format baseline:

```bash
.venv/bin/python -m privhsd.cli create-submission \
  --input data/public_dev/recommended_merged.csv \
  --output data/outputs/recommended_merged.balanced.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode balanced \
  --manifest data/outputs/recommended_merged.balanced.manifest.json
```

Validate:

```bash
.venv/bin/python -m privhsd.cli validate-submission \
  --source data/public_dev/recommended_merged.csv \
  --submission data/outputs/recommended_merged.balanced.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/recommended_merged.balanced.validation.json
```

Full tests:

```bash
.venv/bin/python -m pytest -q
```

## Required Updates Before Stopping

Before stopping, always run:

```bash
.venv/bin/python -m pytest -q
git status --short
```

Update these files:

- `docs/roadmap.md` with aggregate results, exact commands, outputs, and
  blockers;
- `docs/real_data_playbook.md` if the official-data workflow changes;
- `docs/final_pitch_outline.md` if results materially change the story;
- `docs/methodology_justification.md` if you add new context/rationale logic;
- `docs/official_submission_checklist.md` if required checks change;
- `agents/current_handoff.md` with the exact final state;
- `agents/task_board.md` with completed/in-progress tasks.

Leave a final summary that includes:

- what was implemented;
- what commands were run;
- key metrics;
- files changed;
- outputs written under `data/outputs/`;
- remaining risks;
- next best action when the official CSV arrives.

Do not stop at a plan. Implement, run, measure, document, and continue until the
success criteria are met or a real blocker is documented.
