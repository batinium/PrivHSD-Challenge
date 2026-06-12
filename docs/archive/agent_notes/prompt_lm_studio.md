# Continuation Prompt: PrivHSD LM Studio Stress Test

You are working in:

```text
/home/bati/projects/PrivHSD-Challenge
```

Work autonomously. Do not stop at planning. Implement, run, measure, document,
and keep `docs/archive/agent_notes/overnight_progress.md` updated. Stop only when the success
criteria below are met or a hard blocker is documented.

## Mission

PrivHSD is a privacy-preserving text transformation system for hate-speech
detection datasets. The deterministic baseline is already strong. Your main job
now is to stress test local LM Studio models as **context labelers**, not as
direct anonymizers.

The system must still:

- preserve row count, row order, IDs, labels, and metadata;
- reduce direct identifiers, quasi-identifiers, and author-identifying style;
- preserve hate-speech detection utility;
- preserve target/action/negation/modality cues;
- avoid over-restricting offensive, toxic, political, satirical,
  counterspeech, quoted/reported, or public-interest expression;
- preserve evidence of hate against vulnerable or historically targeted groups;
- be explainable, auditable, and compatible with human review.

This is not a generic PII scrubber, not a production hate classifier, not an
automated takedown system, and not a legal decision system.

## Read First

Start by reading:

1. `docs/archive/agent_notes/current_handoff.md`
2. `docs/archive/agent_notes/overnight_progress.md`
3. `docs/archive/agent_notes/task_board.md`
4. `docs/archive/agent_notes/coding_rules.md`
5. `docs/project/roadmap.md`
6. `docs/project/pipeline_design.md`
7. `docs/project/methodology_justification.md`
8. `docs/project/real_data_playbook.md`
9. `docs/challenge/official_submission_checklist.md`
10. `docs/challenge/final_pitch_outline.md`

Then inspect the relevant implementation:

- `privhsd/lm_context_benchmark.py`
- `privhsd/context.py`
- `privhsd/source_report.py`
- `privhsd/rationale_checks.py`
- `privhsd/cue_checks.py`
- `privhsd/metrics.py`
- `privhsd/rerank.py`
- `privhsd/cli.py`
- tests under `tests/`

## Current Baseline State

Main public regression file:

```text
data/public_dev/recommended_merged.csv
```

Generated outputs are ignored and must stay under:

```text
data/outputs/
```

The merged public bundle is source-aware. Do not collapse `offensive`, `toxic`,
`abuse`, or `ambiguous` into hate unless a specific experiment documents the
mapping. Do not use `source_id` as an author label.

Fresh deterministic baseline artifacts already exist:

```text
data/outputs/recommended_merged.profile.json
data/outputs/recommended_merged.balanced.csv
data/outputs/recommended_merged.balanced.manifest.json
data/outputs/recommended_merged.balanced.validation.json
data/outputs/recommended_merged.balanced.source_regression.json
```

Latest deterministic metrics:

- rows: 159,668
- exact-format validation: valid
- changed text cells: 26,941
- identifier detections: 40,304 -> 5
- direct identifiers: 33,032 -> 4
- quasi identifiers: 7,272 -> 1
- target cue retention: 0.9999
- utility cue retention: 0.9999
- action cue retention: 0.9991
- negation/modality retention: 0.9989
- character retention: 0.9721
- rationale span retention: 47,729 / 47,740 = 0.9998
- rationale-loss rows: 11
- context-loss rows: 203
- utility-loss rows: 139

Full tests last passed:

```text
.venv/bin/python -m pytest -q
115 passed, 1 skipped
```

## LM Studio Endpoint

Use this endpoint first:

```text
http://169.254.83.107:1234
```

Confirm it before benchmarking:

```bash
curl --max-time 10 -s http://169.254.83.107:1234/v1/models
```

Earlier localhost/Tailscale checks were blocked:

```text
http://127.0.0.1:1234        connection refused
http://100.120.207.64:1234   timed out
```

Do not spend time on those unless the main endpoint fails.

Confirmed model IDs from the reachable endpoint:

```text
google/gemma-4-e2b
qwen3-0.6b
google/gemma-3n-e4b
microsoft/phi-4-mini-reasoning
qwen/qwen3-4b
qwen/qwen3-1.7b
nvidia/nemotron-3-nano-4b
liquid/lfm2-1.2b
liquid/lfm2.5-1.2b
qwen/qwen3.6-27b
google/gemma-4-e4b
mistralai/ministral-3-3b
qwen/qwen3-4b-2507
google/gemma-4-26b-a4b-qat
google/gemma-4-12b
google/gemma-4-12b-qat
gpt-oss-safeguard-20b
text-embedding-bge-m3
zai-org/glm-4.7-flash
gemma-4-26b-a4b-it
text-embedding-nomic-embed-text-v1.5
openai/gpt-oss-20b
```

Skip embedding models for chat-completion context labeling:

```text
text-embedding-bge-m3
text-embedding-nomic-embed-text-v1.5
```

## Existing LM Smoke Results

Do not treat these as comprehensive.

`qwen3-0.6b` smoke:

```bash
.venv/bin/python -m privhsd.cli benchmark-lm-context \
  --input data/public_dev/recommended_merged.csv \
  --text-col text \
  --id-col id \
  --source-col source \
  --label-col label \
  --endpoint http://169.254.83.107:1234/v1/chat/completions \
  --model qwen3-0.6b \
  --sample-size 5 \
  --timeout 30 \
  --max-tokens 160 \
  --output data/outputs/lm_context_benchmark.qwen3-0.6b.smoke5.json
```

Result: endpoint reachable, 5 attempted rows, 0 parseable outputs across JSON,
tagged, word-list, and binary modes, runtime 25.5117s.

`mistralai/ministral-3-3b` smoke:

```bash
.venv/bin/python -m privhsd.cli benchmark-lm-context \
  --input data/public_dev/recommended_merged.csv \
  --text-col text \
  --id-col id \
  --source-col source \
  --label-col label \
  --endpoint http://169.254.83.107:1234/v1/chat/completions \
  --model mistralai/ministral-3-3b \
  --sample-size 3 \
  --timeout 45 \
  --max-tokens 192 \
  --output data/outputs/lm_context_benchmark.ministral-3-3b.smoke3.json
```

Result: 3 attempted rows, 2 parsed via JSON, parse-valid rate 0.6667, p50
latency 2.6031s, p95 latency 12.2023s, rows/sec 0.0576, deterministic-tag
agreement mean 0.0, protected cue phrase hits 1, maskable cue violations 2.
Treat this as weak smoke evidence only.

## Initial Commands

Run these first:

```bash
git status --short
.venv/bin/python -m pytest -q
curl --max-time 10 -s http://169.254.83.107:1234/v1/models
```

If `.venv` is broken, use `python -m pytest -q` and repair the environment.
Do not delete or reset user changes. Do not use destructive git commands.

## Progress Log

Keep updating:

```text
docs/archive/agent_notes/overnight_progress.md
```

Update it:

- after initial tests/model discovery;
- before and after each model benchmark group;
- after parser/prompt changes;
- whenever a blocker or useful finding appears;
- at least every 60 minutes during long runs.

Use aggregate metrics, source names, row IDs, and reason codes only. Do not
paste raw sensitive/hateful examples into docs, reports, or the final answer.

## Primary Work

### 1. Make The LM Context Benchmark Reliable

The current command is:

```bash
.venv/bin/python -m privhsd.cli benchmark-lm-context \
  --input data/public_dev/recommended_merged.csv \
  --text-col text \
  --id-col id \
  --source-col source \
  --label-col label \
  --endpoint http://169.254.83.107:1234/v1/chat/completions \
  --model MODEL_ID \
  --sample-size 20 \
  --timeout 45 \
  --max-tokens 192 \
  --output data/outputs/lm_context_benchmark.MODEL_ID.sample20.json
```

The benchmark should test output modes in this order unless evidence suggests a
better order:

1. `json`
2. `tagged`
3. `word_lists`
4. `binary_tags`

If many outputs are unparseable, inspect sanitized output shapes carefully. Do
not log raw row text. It is acceptable to improve:

- prompts;
- parsing of common harmless wrappers such as markdown fences;
- parsing of simple JSON arrays or booleans;
- mode-specific fallback behavior;
- aggregate failure reason reporting.

Do not make LLMs required for the core `privhsd anonymize` or
`create-submission` path.

### 2. Benchmark Models In Controlled Groups

Do not start with large full-sample runs. Use this progression:

1. Smoke all non-embedding models with sample 3 or 5.
2. Run sample 20 for models with parse-valid rate > 0.5 or otherwise useful
   structured behavior.
3. Run sample 100 only for the best speed/usefulness tradeoffs.
4. Stop or skip models that are too slow, unparseable, or unsafe.

Recommended first model order:

```text
qwen3-0.6b
liquid/lfm2-1.2b
liquid/lfm2.5-1.2b
qwen/qwen3-1.7b
mistralai/ministral-3-3b
qwen/qwen3-4b
nvidia/nemotron-3-nano-4b
qwen/qwen3-4b-2507
google/gemma-4-e2b
google/gemma-3n-e4b
microsoft/phi-4-mini-reasoning
openai/gpt-oss-20b
```

Treat the larger 12B/20B/26B/27B models as optional later passes only if the
small/medium models are too weak and runtime is acceptable.

### 3. Evaluate The Right Signals

Measure each model on:

- parse-valid rate by mode;
- timeout/error rate;
- rows/sec and p50/p95 latency;
- agreement with deterministic context tags;
- ability to identify negation, counterspeech, quotation/reporting, protected
  targets, hostile action, threat, exclusion, and dehumanization;
- protected phrase counts and whether protected phrases include target/action/
  negation/rationale cues;
- maskable phrase counts and whether maskable phrases wrongly include protected
  target/action/rationale cues;
- uncertainty calibration if available;
- usefulness as a teacher/scorer for token-action rules or reranking features.

The model is not better just because it is bigger or writes prettier prose. The
best candidate is the fastest model that gives parseable, conservative,
useful advisory labels without marking protected cues as maskable.

### 4. Keep Reports Raw-Text-Free

Write reports under `data/outputs/`, for example:

```text
data/outputs/lm_context_benchmark.MODEL_ID.smoke5.json
data/outputs/lm_context_benchmark.MODEL_ID.sample20.json
data/outputs/lm_context_benchmark.MODEL_ID.sample100.json
data/outputs/lm_context_benchmark.summary.json
```

Reports must not contain raw text. Row IDs, source names, labels, predicted
tags, deterministic tags, counts, errors, latency, and reason codes are OK.

### 5. Optional: Improve Deterministic Rules From Evidence

Only integrate LM evidence through deterministic validators, token-action
rules, or reranking features. Do not let an LLM directly produce final
privatized text.

If model outputs reveal a repeated deterministic blind spot, add focused tests
and improve:

- `privhsd/context.py`
- `privhsd/lm_context_benchmark.py`
- `privhsd/rerank.py`
- `privhsd/token_actions.py`

Any change must preserve or improve the baseline source-aware report metrics.

## Required Final Checks

Before stopping, always run:

```bash
.venv/bin/python -m pytest -q
git status --short
```

Update:

- `docs/archive/agent_notes/overnight_progress.md`
- `docs/archive/agent_notes/current_handoff.md`
- `docs/archive/agent_notes/task_board.md`
- `docs/project/roadmap.md`
- `docs/project/pipeline_design.md` if CLI/report behavior changes
- `docs/challenge/final_pitch_outline.md` if model evidence changes the story
- `docs/project/methodology_justification.md` if context/rationale logic changes
- `docs/challenge/official_submission_checklist.md` if required checks change

## Success Criteria

Do not stop until one of these is true.

### Total Success

- Full tests pass.
- LM Studio endpoint/model discovery is recorded.
- Every reachable non-embedding small/medium model has at least a smoke result.
- At least two promising models have sample-20 results, or blockers explain why
  none are promising.
- At least one best model has sample-100 results, or runtime/quality blockers
  explain why sample-100 is not useful.
- An aggregate leaderboard exists with parse-valid rate, latency, agreement,
  protected cue hits, maskable cue violations, and recommendation/skip reason.
- Docs and handoff files record exact commands, outputs, aggregate metrics, and
  remaining risks.

### Minimum Success

- Full tests pass.
- At least 5 reachable non-embedding models have smoke results.
- At least 1 model has a sample-20 result.
- Parser/prompt limitations are documented.
- No raw sensitive/hateful examples are written to docs or reports.
- The repo remains ready to profile, process, validate, and diagnose official
  CSVs immediately.

### Hard Blocker

Stop only if:

- the same blocker recurs after at least three serious workaround attempts;
- no other useful model, parser, deterministic-rule, or documentation work can
  proceed;
- `docs/archive/agent_notes/overnight_progress.md` records the exact command, error, attempted
  workarounds, and next action.

## Final Summary Requirements

The final response must include:

- what was implemented or changed;
- exact commands run;
- models tested and sample sizes;
- key aggregate metrics;
- files changed;
- outputs written under `data/outputs/`;
- remaining risks;
- next best action when the official CSV arrives.
