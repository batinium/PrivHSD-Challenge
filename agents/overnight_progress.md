# Overnight Progress

This file is the live memory log for long autonomous runs. Update it during the
overnight run so progress survives context resets.

## Current Objective

- Completed the deterministic evaluator hardening pass. Current follow-up is
  LM Studio context-labeler stress testing through the reachable endpoint
  `http://169.254.83.107:1234`.

## Completed Since Start

- Read `prompt.md` continuation instructions.
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

## Running Now

- Success criteria review and final summary.

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
