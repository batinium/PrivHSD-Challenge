# Overnight Progress

Archived note: this is a historical run log. Use
[../../README.md](../../README.md) and [../../project/roadmap.md](../../project/roadmap.md)
for current workflow.

This file is the live memory log for long autonomous runs. Update it during the
overnight run so progress survives context resets.

## Current Objective

- Completed Qwen 3 local LLM integration testing. Qwen is now documented as an
  optional source/label-aware candidate generator behind strict validation and
  reranking, not as a replacement for the deterministic baseline.

## Completed Since Start

- 2026-06-12 07:39 +03: Resumed the LM Studio context-labeler stress-test
  phase from `docs/archive/agent_notes/prompt_lm_studio.md`.
- Initial checks for this phase:
  - `git status --short`: no output.
  - `.venv/bin/python -m pytest -q`: 115 passed, 1 skipped in 4.26s.
  - `curl --max-time 10 -s http://169.254.83.107:1234/v1/models`: reachable,
    returned the expected 22 model IDs including 20 non-embedding chat/model
    IDs and 2 embedding IDs.
- Hardened `privhsd/lm_context_benchmark.py` parser handling for common
  harmless wrappers and variants: fenced JSON, JSON arrays of tags, JSON
  alias keys, boolean tag fields, and explicit empty structured outputs.
- Focused parser/benchmark tests passed:
  `.venv/bin/python -m pytest -q tests/test_lm_context_benchmark.py` -> 4
  passed in 0.06s.
- Smoke3 batch 1 completed after parser hardening:
  - `qwen3-0.6b`: parse-valid 0.0; skipped as still unparseable.
  - `liquid/lfm2-1.2b`: parse-valid 1.0, p50 0.2677s, rows/sec 0.812,
    deterministic agreement 0.0, 0 maskable cue violations.
  - `liquid/lfm2.5-1.2b`: parse-valid 0.6667, p50 0.2755s, rows/sec 0.1806,
    deterministic agreement 0.125, 0 maskable cue violations.
  - `qwen/qwen3-1.7b`: parse-valid 0.3333, p50 0.4837s, rows/sec 0.1094,
    deterministic agreement 1.0 on the one parsed row only.
  - `mistralai/ministral-3-3b`: parse-valid 1.0, p50 1.254s, rows/sec 0.2953,
    deterministic agreement 0.3333, 0 maskable cue violations.
  Batch-1 conclusion: parser hardening helps, but the fastest parseable models
  are still weak context labelers on agreement.
- Smoke3 batch 2 completed:
  - `qwen/qwen3-4b`: parse-valid 0.0; skipped as unparseable.
  - `nvidia/nemotron-3-nano-4b`: parse-valid 1.0, p50 1.1981s, p95 16.44s,
    rows/sec 0.1538, deterministic agreement 0.4, 0 maskable cue violations.
  - `qwen/qwen3-4b-2507`: parse-valid 1.0, p50 0.7813s, p95 11.1295s,
    rows/sec 0.2452, deterministic agreement 0.3333, 0 maskable cue
    violations.
  - `google/gemma-4-e2b`: parse-valid 0.0; skipped as unparseable.
  - `google/gemma-3n-e4b`: blocked on first request by timeout at 35s.
  Batch-2 conclusion: Nemotron 4B and Qwen 4B 2507 are parseable but still weak
  on agreement in the tiny smoke; Gemma variants are not useful at this timeout.
- User noticed LM Studio was not showing model loads during batch 3. Checked
  processes and stopped the still-running benchmark loop, which was on
  `zai-org/glm-4.7-flash`.
- Network diagnosis:
  - `169.254.83.107:1234` no longer accepted TCP from this WSL shell; `nc` and
    `curl --noproxy '*'` timed out.
  - `172.21.96.1:1234` accepted TCP and `/v1/models` returned the same LM
    Studio model list.
  - A tiny chat completion against
    `http://172.21.96.1:1234/v1/chat/completions` with
    `liquid/lfm2-1.2b` returned `{"ok":true}` in 2.3059s.
  - `127.0.0.1:1234` still refused connections.
- Treat `microsoft/phi-4-mini-reasoning` and `google/gemma-4-e4b` smoke3.v2
  reports written through `169.254.83.107` as endpoint/routing failures, not
  model-quality results; rerun any needed remaining smokes through
  `172.21.96.1`.
- Corrected gateway smoke3 results:
  - `microsoft/phi-4-mini-reasoning`: reachable but parse-valid 0.0.
  - `google/gemma-4-e4b`: reachable but parse-valid 0.0.
  - `zai-org/glm-4.7-flash`: reachable but parse-valid 0.0.
  These are real model/prompt-format skips through the working gateway, not the
  stale link-local routing failure.
- Sample20 gateway results:
  - `liquid/lfm2-1.2b`: parse-valid 1.0, p50 0.3051s, p95 0.5214s,
    rows/sec 2.2848, deterministic agreement 0.0625, protected cue phrase
    hits 16, maskable cue violations 3.
  - `mistralai/ministral-3-3b`: parse-valid 1.0, p50 1.3387s, p95 1.3947s,
    rows/sec 0.7192, deterministic agreement 0.1292, protected cue phrase
    hits 4, maskable cue violations 0.
  - `nvidia/nemotron-3-nano-4b`: parse-valid 0.25, p50 1.2649s, p95 5.2275s,
    rows/sec 0.0748, deterministic agreement 0.4133 on only 5 parsed rows,
    maskable cue violations 0.
  - `qwen/qwen3-4b-2507`: parse-valid 1.0, p50 0.8756s, p95 1.4897s,
    rows/sec 0.8739, deterministic agreement 0.1663, protected cue phrase
    hits 11, maskable cue violations 3.
  Sample20 conclusion: no model is strong enough to integrate as a context
  teacher; `mistralai/ministral-3-3b` is the least unsafe candidate for one
  sample100 confirmation because it parsed every row and had zero maskable cue
  violations.
- Sample100 gateway confirmation:
  - `mistralai/ministral-3-3b`: parse-valid 1.0, p50 1.1017s, p95 1.3727s,
    rows/sec 0.9268, deterministic agreement 0.1525, protected cue phrase hits
    23, maskable cue violations 9, runtime 107.8999s.
  - Conclusion: do not integrate LM Studio context labels into deterministic
    rules or reranking yet. Even the least-bad model is format-compliant but
    low-agreement and unsafe on maskable protected cues at larger sample size.
- Wrote aggregate leaderboard and decision report:
  `data/outputs/lm_context_benchmark.summary.json`.
- Final full test suite passed:
  `.venv/bin/python -m pytest -q` -> 116 passed, 1 skipped in 3.13s.
- Final `git status --short` included expected LM benchmark/docs changes from
  that task plus README changes not edited in that pass.
- Read `docs/archive/agent_notes/prompt_lm_studio.md` continuation instructions.
- Checked LM Studio endpoints:
  - `http://127.0.0.1:1234/v1/models`: connection failed.
  - `http://100.120.207.64:1234/v1/models`: timed out after 5 seconds.
- `git status --short` produced no output before changes in this run.
- Required initial tests passed:
  `.venv/bin/python -m pytest -q` -> 101 passed, 1 skipped in 2.57s.
- Required dataset profile completed:
  `data/outputs/recommended_merged.profile.json`.
- Read the required docs and handoff/task/coding-rule files.
- Added deterministic context tag, source-aware rationale parsing, source
  regression report, and LM context benchmark modules with focused tests.
- Focused new tests passed: 13 passed in 0.10s.
- Regenerated exact-format `balanced` output:
  `data/outputs/recommended_merged.balanced.csv`.
- Regenerated manifest:
  `data/outputs/recommended_merged.balanced.manifest.json`.
- Standalone exact-format validation passed:
  `data/outputs/recommended_merged.balanced.validation.json`.
- LM context benchmark blockers written:
  `data/outputs/lm_context_benchmark.summary.json` for localhost and
  `data/outputs/lm_context_benchmark.tailscale.blocked.json` for Tailscale.
- Full source-aware regression report completed:
  `data/outputs/recommended_merged.balanced.source_regression.json`.
- Fixed a Toxic Spans rationale parser edge case for invalid/negative offsets.
- Full test suite passed:
  `.venv/bin/python -m pytest -q` -> 115 passed, 1 skipped in 3.22s on the
  final rerun.
- Final `git status --short` showed only expected modified docs/source/tests
  and new source/test files from this run.
- Later user-provided LM Studio endpoint check succeeded:
  `http://169.254.83.107:1234/v1/models` returned 22 model IDs.
- Confirmed reachable model IDs:
  `google/gemma-4-e2b`, `qwen3-0.6b`, `google/gemma-3n-e4b`,
  `microsoft/phi-4-mini-reasoning`, `qwen/qwen3-4b`,
  `qwen/qwen3-1.7b`, `nvidia/nemotron-3-nano-4b`,
  `liquid/lfm2-1.2b`, `liquid/lfm2.5-1.2b`,
  `qwen/qwen3.6-27b`, `google/gemma-4-e4b`,
  `mistralai/ministral-3-3b`, `qwen/qwen3-4b-2507`,
  `google/gemma-4-26b-a4b-qat`, `google/gemma-4-12b`,
  `google/gemma-4-12b-qat`, `gpt-oss-safeguard-20b`,
  `text-embedding-bge-m3`, `zai-org/glm-4.7-flash`,
  `gemma-4-26b-a4b-it`, `text-embedding-nomic-embed-text-v1.5`,
  `openai/gpt-oss-20b`.
- Ran a tiny reachable-endpoint smoke on `qwen3-0.6b`:
  `data/outputs/lm_context_benchmark.qwen3-0.6b.smoke5.json`.
- A `mistralai/ministral-3-3b` smoke was started before the user asked not to
  start more benchmarks; no process remained running, and the completed output
  is `data/outputs/lm_context_benchmark.ministral-3-3b.smoke3.json`.
- Added source/label-aware Qwen candidate support:
  - `generate-llm-candidates` accepts `--source-col` and `--label-col`.
  - Local LLM candidate prompts include source/label/target metadata as
    cue-preservation context.
  - Bounded LLM samples use source/label round-robin selection.
  - Rewrite validation rejects action-cue loss and negation/modality-cue loss.
- Qwen 3 label-aware context benchmark:
  `data/outputs/lm_context_benchmark.qwen-qwen3-4b-2507.sample100.labelaware.json`.
  Model `qwen/qwen3-4b-2507` parsed 100/100 rows, p50 latency 0.7684s, p95
  1.3709s, rows/sec 1.204, deterministic agreement 0.2226, and 1 maskable cue
  violation.
- Qwen 3 source/label-stratified candidate run:
  `data/outputs/recommended_merged.qwen_stratified80.qwen_candidates.report.json`.
  Accepted 43/80 candidates and rejected 37/80 by checks. Reject reasons:
  unchanged 13, target cue loss 12, residual direct identifier 11, length drift
  5, utility cue loss 3, action cue loss 3, residual quasi identifier 1,
  style-risk increase 1, low character retention 1.
- Qwen 3 reranking:
  `data/outputs/recommended_merged.qwen_stratified80.qwen_rerank.audit.json`.
  Selected `balanced` for 50 rows, `style_scrubbed` for 29 rows, and
  `rewrite:qwen_candidate` for 1 row.
- Qwen 3 final checks:
  `data/outputs/recommended_merged.qwen_stratified80.qwen_reranked.cue_checks.json`
  reported zero cue-loss rows; target retention 1.0303, utility/action/
  negation-modality retention all 1.0. Source regression reported identifiers
  22 -> 0, direct identifiers 21 -> 0, quasi identifiers 1 -> 0, utility-loss
  rows 0, context-loss rows 2, rationale-loss rows 0.
- Wrote raw-text-free Qwen decision summary:
  `data/outputs/recommended_merged.qwen_stratified80.qwen_experiment_summary.json`.
- Final full test suite passed after Qwen code/docs updates:
  `.venv/bin/python -m pytest -q` -> 118 passed, 1 skipped in 4.34s.
- Added semantic triage fallback layer:
  - New command: `semantic-triage-report`.
  - Always uses deterministic context tags and conservative cue checks.
  - Optionally uses a trained local classifier artifact for prediction shift,
    low confidence, low margin, and confidence drop.
  - Routes rows to `repair_before_model_review`, `qwen_semantic_check`, or
    `no_review`.
  - Writes raw-text-free JSON and optional queue CSV.
- Real fallback run on the Qwen stratified 80-row reranked output:
  `data/outputs/recommended_merged.qwen_stratified80.semantic_triage.json`.
  It selected 21/80 rows for review: 2 hard repair rows due to lost
  quoted/reported context and 19 rows for Qwen semantic checking.

## Running Now

- Final summary.

## Metrics Snapshot

- `recommended_merged.csv`: 159,668 rows; detected `text`, `id`, `label`,
  `source`, and `split`; 9 sources; 26,912 rows with `rationale_spans`;
  no blank text values; unique merged IDs.
- Fresh `balanced` manifest: 159,668 rows; exact-format validation valid;
  changed text cells 26,941; identifier detections 40,304 -> 5; direct
  identifiers 33,032 -> 4; quasi identifiers 7,272 -> 1; target cue retention
  0.9999; utility cue retention 0.9999; character retention 0.9721.
- Source-aware regression report overall: changed text rate 0.1687; identifiers
  40,304 -> 5; direct 33,032 -> 4; quasi 7,272 -> 1; target cue retention
  0.9999; utility cue retention 0.9999; action cue retention 0.9991;
  negation/modality retention 0.9989; character retention 0.9721; utility-loss
  rows 139; context-loss rows 203; rationale-loss rows 11.
- Rationale preservation: 26,909 rows with parsed rationale spans; 47,740
  rationale spans; 47,729 preserved; retention 0.9998; 56 overlap changed
  regions; 41 overlap placeholders.

## Model Benchmark Notes

- Initial LM Studio endpoints were unavailable from this shell:
  localhost refused and Tailscale timed out.
- `benchmark-lm-context` localhost blocked after 1 attempted row:
  connection refused, runtime 0.0347s.
- `benchmark-lm-context` Tailscale blocked after 1 attempted row:
  timeout, runtime 2.0379s.
- User later provided reachable endpoint `http://169.254.83.107:1234`.
- `qwen3-0.6b` smoke5 on source/label round-robin real rows:
  status `skipped`, parse-valid rate 0.0, 5/5 failed, all four parse modes
  failed, runtime 25.5117s.
- `mistralai/ministral-3-3b` smoke3:
  status `ok`, parse-valid rate 0.6667, parsed 2/3 via JSON, p50 latency
  2.6031s, p95 latency 12.2023s, rows/sec 0.0576, deterministic-tag agreement
  mean 0.0, protected cue phrase hits 1, maskable cue violations 2. Treat this
  as a weak smoke result only, not a model recommendation.

## Blockers / Skips

- The original localhost/Tailscale LM Studio endpoints are still blocked from
  this shell, but `http://169.254.83.107:1234` is reachable.
- Comprehensive LM Studio model testing is not done. Next agent should use the
  reachable endpoint and run controlled model groups; do not start with large
  full-sample jobs.

## Next Action

- Next agent should run comprehensive LM Studio context-labeler stress tests:
  discover `/v1/models`, smoke all non-embedding models on small
  source/label/functionality-aware samples, improve parser/prompt handling if
  needed, then run sample-20/sample-100 only for promising models. Keep raw text
  out of reports and update docs with aggregate leaderboards.
