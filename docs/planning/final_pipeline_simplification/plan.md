# Final Pipeline Simplification Plan

Status: implementation in progress
Owner area: final MVP pipeline, workbench alignment, dead-code removal
Last updated: 2026-06-15
Primary prompt: `docs/planning/final_pipeline_simplification/prompt.md`

## Decision

The final MVP should be one explainable CSV pipeline:

```text
input CSV
  -> PII sanitization with deterministic detectors and PII Assist
  -> target/HSD cue preservation
  -> local LLM review for classification and PII suggestions
  -> exact-format output CSV with only text replaced
  -> manifest/audit sidecars
```

`sanitize-classify` is analysis-oriented because it appends helper columns. The
final upload-shaped command should write the original schema only.

## Keep In The Final Path

- Deterministic PII detectors and placeholders.
- Presidio and scrubadub as local PII Assist.
- Candidate selection and residual PII cleanup.
- Target/action/negation/quote/counterspeech cue preservation.
- Local LLM HSD classification, reason tags, and validated PII suggestions.
- Exact CSV validation.
- Manifest/audit sidecars.
- Workbench CSV flow aligned with the same backend path.

## Off By Default

- Author-group masking/checking.
- Deep metric audits.
- Debug provider/model toggles.
- Full-dataset sweeps.

## Remove Or Quarantine

The next implementation pass should remove confirmed dead code and hide
research-only components from the normal runtime:

- DPMLM and LLM rewrite candidate paths.
- Token-policy experiment/runtime paths if they are not needed by the final
  command.
- GLiNER public/default path.
- HF HSD advisory classifier path once local LLM sidecar review is wired into
  the final command.
- Duplicate CLI surfaces and stale workbench controls.
- Config-search and ablation code from production flow.

Deletion should be incremental. Run focused tests after each deletion group and
commit/push stable milestones.

## Required Final Behavior

- Output CSV row count and order match input.
- Output CSV columns match input exactly.
- Selected text column is replaced with sanitized text.
- LLM classification and PII suggestion details are recorded in sidecars only.
- Manifest states which providers/models ran, skipped, or failed.
- Workbench exports exact-format CSV by default.
- Logs and reports avoid raw row text.

## Implemented In This Pass

- Added `run_final_csv_pipeline` and `build_final_pipeline_rows` as the shared
  exact CSV backend for the final path.
- Wired `protect --preset exact|audit` to the final backend. The output CSV
  keeps the original columns only; local LLM classification, reason tags, and
  validated residual PII suggestions are sidecar-only.
- Added `--llm-review local-llm`, local LLM endpoint/model/batch controls,
  `--require-llm-review`, and progress reporting to `protect`.
- Added progress events inside local LLM review batches.
- Updated the workbench exact CSV endpoint to call the same final backend and
  default to exact-format export.
- Added focused tests for exact CSV shape preservation, sidecar-only fake local
  LLM output, and workbench local LLM review without helper columns.
- Removed the abandoned DPMLM spike, DPMLM rewrite-candidate, and local LLM
  rewrite-candidate modules, CLI commands, and legacy tests. This does not
  affect the local LLM HSD review runtime used by the final sidecar path.
- Removed token-policy experiment/runtime modules, CLI commands, workbench
  model controls, training runbook, and legacy tests from the production tree.
- Removed GLiNER and HF HSD advisory public runtime knobs from the CLI and
  workbench dashboard. Historical advisory code remains quarantined outside the
  final exact CSV path.

Focused verification so far:

```bash
python -m py_compile contextsafe_hsd/simple_pipeline.py contextsafe_hsd/cli.py contextsafe_hsd/models/local_llm_hsd_review_runtime.py workbench/backend/app.py
python -m pytest tests/test_simple_pipeline.py tests/test_submission.py tests/test_workbench_csv.py tests/test_local_llm_hsd_review_runtime.py tests/test_local_llm_hsd_suggestions.py -q
```

Result: `45 passed`.

Final verification:

```bash
python -m ruff check contextsafe_hsd workbench/backend tests
python -m pytest -q
npm --prefix workbench/frontend run build
```

Result on 2026-06-15: ruff passed; pytest `266 passed, 1 skipped`; frontend
build passed. A live 25-row `protect --preset exact --llm-review local-llm`
smoke preserved row order/count/columns exactly, changed only the `text`
column, appended no helper columns, and wrote manifest/audit sidecars with
local LLM status `ok`, parse count 25, fallback count 0, reason tag counts,
and validated PII suggestion counts.

## Small-Batch Verification Policy

Use a 25-100 row local batch for system checks while cleaning. Avoid the full
train split until the simplified path is stable.

Minimum final checks:

```bash
python -m ruff check contextsafe_hsd workbench/backend tests
python -m pytest -q
npm --prefix workbench/frontend run build
```

Run a small live local-LLM smoke only when the endpoint is available. If it is
not available, fake-runtime tests are acceptable, but the blocker must be
recorded.

## Handoff Notes

- Current local LLM endpoint: `http://100.120.207.64:1234/v1/chat/completions`.
- Current local LLM model: `openai/gpt-oss-20b`.
- The last full train split local-LLM sweep succeeded and is summarized in
  `docs/planning/current_status.md`.
- Do not commit generated `data/` outputs.
- Keep commits small enough that a broken cleanup can be reverted without
  losing unrelated work.
