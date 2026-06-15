# Prompt: Final Pipeline Simplification

You are the next Codex agent in `/home/bati/projects/PrivHSD-Challenge`.
Continue unattended until the final pipeline is simplified, verified on a small
batch, documented, committed, and pushed. Do not stop at a proposal.

## User Goal

Reduce the legacy codebase to the final MVP pipeline:

```text
input CSV
  -> deterministic PII sanitization
  -> Presidio/scrubadub PII assist
  -> removal/candidate selection with target-cue preservation
  -> local LLM HSD classification plus PII-removal suggestions/reasoning
  -> output CSV in the original input format, only text replaced 1:1
  -> manifest/audit sidecars with classification reasoning and suggestions
```

The user must be able to explain the code. Prefer a smaller, clearer codebase
over preserving abandoned experiment paths.

## Non-Negotiable Product Contract

- The final user-facing pipeline writes an upload-shaped CSV: same row order,
  same columns, same IDs/metadata, selected text column replaced with sanitized
  text only.
- Classification labels, LLM reasoning, PII suggestions, provider diagnostics,
  metrics, and warnings are saved to manifest/audit sidecars, not appended to
  the upload CSV by default.
- Row-level PII sanitization is the default privacy authority.
- Author-group masking/checking remains off by default. Keep it optional only if
  it does not complicate the main path.
- Preserve HSD-relevant target/action/negation/quote/counterspeech cues during
  masking.
- LLM output is advisory for classification and PII suggestions. Do not let the
  LLM rewrite whole comments in the final path.
- No raw private row text should be printed in normal logs or final reports.
- Default to CPU where possible. Local LLM calls go to the configured local
  OpenAI-compatible endpoint.
- Do not commit ignored/generated `data/` outputs unless the user explicitly
  asks. Store repeatable commands and aggregate metrics in docs instead.

## Current Important Facts

- Current local LLM endpoint:
  `http://100.120.207.64:1234/v1/chat/completions`
- Current local LLM model:
  `openai/gpt-oss-20b`
- Current live full sweep on `data/train/train_split.csv` succeeded:
  1,154 rows, 312 text changes, direct identifiers 215 -> 0, residual
  identifiers 3, local LLM parsed all rows, 176 requests, 60 fallback rows.
- `sanitize-classify` currently appends helper columns and is analysis-only.
- `protect --preset exact` / `create-submission --replace-text` are the
  current upload-shaped paths.
- The old HF HSD advisory classifier is disabled when local LLM classification
  is selected.
- Existing docs:
  - `docs/planning/current_status.md`
  - `docs/planning/llm_hsd_review_integration/plan.md`
  - `docs/planning/llm_hsd_review_integration/prompt.md`
  - `docs/planning/final_pipeline_simplification/plan.md`

## What To Keep

Keep and make easy to explain:

- CSV read/write and validation.
- Deterministic span detectors and typed placeholders.
- Presidio and scrubadub as optional/local PII Assist providers.
- Span fusion, candidate selection, residual cleanup, and metric verification.
- Target/HSD cue detection and cue-retention safeguards.
- Local LLM review runtime for cleaned-text classification, reason tags, and
  validated PII suggestions.
- Manifest/audit sidecars.
- Workbench support for the same final pipeline.
- Tests around exact shape, cue preservation, provider fallback, LLM fake
  runtime behavior, and workbench API behavior.

## What To Remove Or Quarantine

Remove confirmed dead code. Quarantine behind explicit developer commands only
if immediate deletion is too risky:

- Old abandoned candidate-generation paths not used by the final pipeline.
- DPMLM/local-LLM rewrite candidate paths that generate alternative sanitized
  texts for ranking.
- Token-policy model paths unless a test or final pipeline component still
  requires them.
- GLiNER default/public path and related public knobs.
- HF HSD advisory/classifier paths from the final runtime if local LLM is the
  accepted classifier.
- Duplicate command surfaces and aliases that make the flow hard to explain.
- Stale config-search, ablation, and experiment-only code from production CLI.
- Workbench UI/backend controls for removed modes.

Before deleting a module, verify imports, tests, CLI help, and workbench build.
Do not remove useful tests unless the tested feature is intentionally removed
and replacement coverage exists.

## Target CLI

Aim for one final command as the documented path. It may be `protect` if that
is least disruptive:

```bash
python -m contextsafe_hsd.cli protect \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --preset exact \
  --llm-review local-llm \
  --local-llm-endpoint http://100.120.207.64:1234/v1/chat/completions \
  --local-llm-model openai/gpt-oss-20b \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json
```

If different flag names already exist, prefer the existing style, but preserve
the contract: exact output CSV plus sidecar LLM classification/reasoning.

`sanitize-classify` can remain as a developer/analysis command, but it should no
longer be required for the final path and should not be the documented upload
command.

## Workbench Target

Make the workbench match the final pipeline:

- Upload CSV, select text column, run final sanitization.
- Show sanitized output preview and export an exact-format CSV.
- Show sidecar summary: provider status, changed row count, residual PII count,
  target cue retention, LLM HSD label counts, reason tag counts, PII suggestion
  counts.
- Do not expose removed legacy modes in normal UI.
- Keep any advanced/debug mode clearly separated.
- Backend should call the same final pipeline code path as CLI, not a divergent
  implementation.

## Implementation Strategy

Work in small, safe milestones. Commit and push after each milestone that
passes its focused checks.

1. Inventory
   - Run `git status --short --branch`.
   - Map current CLI commands, workbench endpoints, and modules used by the
     final path.
   - Run `python -m vulture contextsafe_hsd workbench/backend tests --min-confidence 90`
     and treat findings as review evidence, not an automatic delete list.
   - Write a short deletion/quarantine list before editing.

2. Final pipeline API
   - Create or simplify a single backend function for exact CSV sanitization
     plus LLM sidecar review.
   - Ensure the output CSV has input columns only, with only `text` replaced.
   - Move LLM classification/reasoning/suggestions into manifest/audit.
   - Add progress around slow phases and LLM batches.

3. Remove/quarantine dead runtime paths
   - Delete confirmed unused modules and CLI flags.
   - Move research-only commands behind explicit developer naming if deletion
     would cause too much immediate churn.
   - Keep compatibility wrappers only when tests or docs still need them.

4. Workbench alignment
   - Update backend endpoint(s) to use the final pipeline function.
   - Update frontend controls and result summaries.
   - Remove normal UI affordances for removed paths.
   - Keep output export exact-format by default.

5. Tests and small system checks
   - Prefer fake LLM tests for unit coverage.
   - Use a small CSV batch for live checks, not the full train split.
   - Do not print raw row text in reports.

6. Docs
   - Update `docs/planning/current_status.md`.
   - Update this folder's `plan.md` with what changed and what remains.
   - Update README/usage docs if they reference removed commands or helper-column
     output as the main path.

## Small-Batch Verification

Create a temporary small batch under ignored `data/outputs/` or use an existing
fixture. If using `data/train/train_split.csv`, sample without printing row
text. Suggested sample sizes: 25 to 100 rows.

Minimum checks after each meaningful refactor:

```bash
python -m py_compile $(git ls-files 'contextsafe_hsd/**/*.py' 'workbench/backend/**/*.py')
python -m ruff check contextsafe_hsd workbench/backend tests
python -m pytest tests/test_pipeline.py tests/test_metrics.py tests/test_auto_pipeline.py tests/test_submission.py tests/test_simple_pipeline.py -q
```

Workbench checks when touched:

```bash
python -m pytest tests/test_workbench_csv.py -q
npm --prefix workbench/frontend run build
```

Final small live check should prove:

- output CSV is valid and exact-format;
- row count/order match input;
- original columns are preserved;
- text column is sanitized in place;
- manifest/audit include local LLM classification status, parsed count,
  fallback count, reason tag counts, and validated PII suggestion counts;
- no helper classification columns are appended to output CSV.

If the local LLM endpoint is unavailable, complete fake-runtime tests and
document the live-check blocker clearly. Do not block the code cleanup on a
network/model outage.

## Commit And Push Rules

- Commit and push after each stable milestone.
- Do not commit unrelated existing changes.
- Do not commit `.vscode/` or ignored/generated `data/` outputs.
- Run `git diff --check` before each commit.
- Use clear commit messages such as:
  - `Define final exact pipeline sidecar contract`
  - `Remove unused candidate generation paths`
  - `Align workbench with final CSV pipeline`
  - `Document final pipeline cleanup`

## Definition Of Done

- One documented final pipeline from input CSV to exact output CSV.
- Final output CSV contains input columns only, with selected text replaced.
- Manifest/audit sidecars contain sanitization metrics, target cue preservation
  metrics, LLM classification labels/reasoning aggregates, and PII suggestion
  metadata.
- Workbench runs the same path and exports exact-format CSV by default.
- Legacy/dead code is removed or clearly quarantined.
- Small-batch system check passes.
- Focused tests pass.
- Docs are updated.
- All cleanup commits are pushed.
