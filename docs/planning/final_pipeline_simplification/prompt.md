# Prompt: Presentation Cleanup Pass

You are the next Codex agent in `/home/bati/projects/PrivHSD-Challenge`.
Continue unattended until the repository is presentation-ready: small enough for
the user to explain, centered on the final exact CSV pipeline, verified,
documented, committed, and pushed. Do not stop at a proposal unless there is a
real blocker.

## Context

The final MVP pipeline is already implemented, verified, documented, committed,
and pushed. Do not re-open the product design unless tests prove it is broken.
Your job is to remove visible spaghetti so the repo can be handed in and
explained clearly.

The prompt file you are reading is the handoff file the user asked to rewrite.
Related status lives in:

- `docs/planning/final_pipeline_simplification/plan.md`
- `docs/planning/current_status.md`
- `docs/reference/pipeline.md`
- `docs/reference/cli.md`

## Final Public Story

The public story should be one command and one explainable backend path:

```text
input CSV
  -> deterministic PII sanitization
  -> Presidio/scrubadub PII Assist
  -> span fusion, residual cleanup, and candidate selection
  -> HSD target/action/negation/quote/counterspeech cue safeguards
  -> local LLM sidecar review on cleaned text only
  -> exact-format output CSV with only the selected text column replaced
  -> manifest/audit sidecars with metrics, labels, reasons, diagnostics, and suggestions
```

Documented command:

```bash
python -m contextsafe_hsd.cli protect \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --llm-review local-llm \
  --local-llm-endpoint http://100.120.207.64:1234/v1/chat/completions \
  --local-llm-model openai/gpt-oss-20b \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json
```

## Non-Negotiable Contract

- Output CSV preserves input row order, row count, and columns exactly.
- Only the selected text column is replaced.
- No classification/helper columns are appended to the final output CSV.
- LLM labels, reason tags, suggestions, provider diagnostics, metrics, and
  warnings go to manifest/audit sidecars only.
- Row-level sanitization is the privacy authority.
- Author-group masking/checking remains off by default.
- HSD target/action/negation/quote/counterspeech cues must be preserved.
- The local LLM must not rewrite whole comments.
- Normal logs and reports must not print raw row text.
- Default to CPU where possible.
- Do not commit generated `data/` outputs or `.vscode/`.

## What To Keep

Keep only code that supports the final story or a compact demo:

- `contextsafe_hsd/simple_pipeline.py`
- `contextsafe_hsd/cli.py`, but with a small public command surface
- `contextsafe_hsd/auto/`
- `contextsafe_hsd/detectors.py`
- `contextsafe_hsd/pipeline.py`
- `contextsafe_hsd/metrics.py`
- `contextsafe_hsd/context.py`
- `contextsafe_hsd/cue_checks.py`
- `contextsafe_hsd/rationale_checks.py`
- `contextsafe_hsd/row_ids.py`
- `contextsafe_hsd/submission.py` if still needed for validation helpers
- `contextsafe_hsd/span_providers/base.py`
- `contextsafe_hsd/span_providers/deterministic.py`
- `contextsafe_hsd/span_providers/fusion.py`
- `contextsafe_hsd/span_providers/presidio.py`
- `contextsafe_hsd/span_providers/scrubadub_provider.py`
- `contextsafe_hsd/models/local_llm_hsd_review_runtime.py`
- Workbench backend/frontend only if keeping the demo UI
- Tests that protect the final exact CSV path, PII Assist fallback, cue
  preservation, local LLM fake runtime, sidecar contracts, and workbench final
  export

## Remove Aggressively

The user explicitly prefers future reimplementation over explaining unused
spaghetti. Delete or move out of the public package anything not needed for the
final path.

Strong deletion candidates:

- Research/analysis CLI commands:
  - `anonymize`
  - `sanitize-classify`
  - `create-submission`
  - `rerank-candidates`
  - `ablate`
  - `benchmark-utility`
  - `evaluate-author-risk`
  - `semantic-triage-report`
  - `source-regression-report`
  - `benchmark-lm-context`
  - `train-classifier`
  - `evaluate-classifier`
  - `predict-classifier`
  - dataset prep commands
- Research/analysis modules if no longer imported by final tests:
  - `contextsafe_hsd/ablation.py`
  - `contextsafe_hsd/classifier.py`
  - `contextsafe_hsd/utility_benchmark.py`
  - `contextsafe_hsd/hf_utility.py`
  - `contextsafe_hsd/models/hsd_advisory_runtime.py`
  - `contextsafe_hsd/lm_context_benchmark.py`
  - `contextsafe_hsd/presidio_compare.py`
  - `contextsafe_hsd/presidio_augment.py`
  - `contextsafe_hsd/rerank.py` if final candidate selection no longer imports it
  - `contextsafe_hsd/semantic_triage.py`
  - `contextsafe_hsd/source_report.py`
  - dataset preparation modules if not needed for hand-in
- Provider internals not part of the public story:
  - `contextsafe_hsd/span_providers/gliner.py` if not imported by final path
- Legacy tests for removed behavior:
  - `tests/test_ablation.py`
  - `tests/test_classifier.py`
  - `tests/test_utility_benchmark.py`
  - `tests/test_lm_context_benchmark.py`
  - `tests/test_presidio_compare.py`
  - `tests/test_presidio_augment.py`
  - `tests/test_rerank.py` if `rerank.py` is removed
  - `tests/test_semantic_triage.py`
  - `tests/test_source_report.py`
  - dataset prep tests if dataset prep commands are removed
- Old planning/research/challenge docs that mention removed methods as active
  work. Either delete them or move them under an obvious archive folder outside
  the main explanation path.
- Top-level/scripts that are not part of the final hand-in demo, including
  synthetic generators, config searches, and one-off experiment runners.

## CLI Goal

Make `python -m contextsafe_hsd.cli --help` look explainable.

Target public commands:

- `protect`
- `validate-submission`
- optionally `profile-dataset`

Everything else should be removed, moved to a clearly named developer module,
or hidden behind a non-public entry point. Prefer deletion unless it directly
helps the hand-in.

## Docs Goal

The hand-in docs should be short and aligned:

- Root `README.md`: what the project does, how to run the final command, how to
  run tests, and how the code is organized.
- `docs/reference/pipeline.md`: final pipeline architecture only.
- `docs/reference/data_contract.md`: exact CSV contract.
- `docs/reference/providers_and_models.md`: deterministic, Presidio,
  scrubadub, local LLM review only.
- `docs/runbooks/quickstart.md`: one final command plus small-batch smoke.
- `docs/runbooks/workbench.md`: only if workbench is retained.
- `docs/planning/current_status.md`: final verification summary.

Archive/delete old planning and research docs that make the active repo look
undecided.

## Implementation Strategy

1. Run `git status --short --branch`.
2. Inventory imports and CLI commands:
   - `python -m contextsafe_hsd.cli --help`
   - `rg "add_parser|elif args.command" contextsafe_hsd/cli.py`
   - `rg "import .*ablation|import .*rerank|hf_utility|hsd_advisory|gliner"`
3. Remove one deletion group at a time:
   - public CLI surface
   - unused modules
   - corresponding tests
   - stale docs/scripts
4. After each group, run focused checks and commit/push.
5. Keep the final checks green:

```bash
python -m ruff check contextsafe_hsd workbench/backend tests
python -m pytest -q
npm --prefix workbench/frontend run build
```

6. Run a small final smoke with 25-100 rows. Do not print raw row text.

## Final Smoke Requirements

Prove and document:

- output CSV is valid;
- row count and order match input;
- columns match input exactly;
- only the selected text column is replaced;
- manifest/audit include local LLM status, parse count, fallback count, reason
  tag counts, and validated PII suggestion counts;
- no helper classification columns are appended.

## Commit Rules

- Run `git status` before editing and before committing.
- Run `git diff --check` before each commit.
- Do not commit `.vscode/` or generated `data/`.
- Use small, clear commits.
- Push each stable milestone.

## Definition Of Done

- `python -m contextsafe_hsd.cli --help` shows a small, explainable public CLI.
- The repo has one obvious final pipeline path.
- Removed/research code is deleted or moved out of the normal explanation path.
- Tests protect only current final behavior and compact supporting utilities.
- Docs no longer make legacy experiments look active.
- Required checks pass.
- Small-batch final smoke passes.
- All commits are pushed.
