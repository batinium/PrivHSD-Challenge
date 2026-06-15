# Presentation Cleanup Plan

Status: ready for next agent
Owner area: hand-in readability, public CLI cleanup, dead-code deletion
Last updated: 2026-06-15
Primary prompt: `docs/planning/final_pipeline_simplification/prompt.md`

## Decision

The final exact CSV pipeline is complete. The next pass is not product design;
it is presentation cleanup. The user needs to hand in and explain this repo,
so the repository should expose one clear pipeline and avoid making old
experiments look like supported product code.

## Final Pipeline To Preserve

```text
input CSV
  -> deterministic PII sanitization
  -> Presidio/scrubadub PII Assist
  -> span fusion, residual cleanup, and candidate selection
  -> HSD cue-retention safeguards
  -> local LLM sidecar review on cleaned text
  -> exact-format output CSV
  -> manifest/audit sidecars
```

Public command:

```bash
python -m contextsafe_hsd.cli protect \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --preset exact \
  --llm-review local-llm \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json
```

## Already Done

- `run_final_csv_pipeline` and `build_final_pipeline_rows` provide the shared
  exact CSV backend.
- `protect --preset exact|audit` uses the final backend.
- Local LLM review is sidecar-only for labels, reason tags, and validated PII
  suggestions.
- Workbench CSV export defaults to exact-format output through the same backend.
- Removed abandoned DPMLM/local-LLM rewrite candidates.
- Removed token-policy runtime paths, CLI commands, workbench controls, runbook,
  and legacy tests.
- Removed GLiNER public knobs from CLI/workbench.
- Quarantined legacy HF advisory surfaces from the public CLI/workbench story.
- Final verification passed on 2026-06-15:
  - `python -m ruff check contextsafe_hsd workbench/backend tests`
  - `python -m pytest -q`: 266 passed, 1 skipped
  - `npm --prefix workbench/frontend run build`
- Live 25-row local LLM smoke passed with exact columns, no helper columns,
  local LLM status `ok`, parse count 25, and fallback count 0.

## Why Another Pass Is Needed

The code works, but the repo still looks too broad for hand-in. The top-level
CLI still exposes many commands that are not part of the final story, and there
are still modules/tests/docs for research and analysis workflows. Reviewers
will see that as spaghetti unless it is deleted or moved out of the public
surface.

## Public Surface Target

Keep visible:

- `protect`
- `validate-submission`
- optional `profile-dataset`

Remove or hide from `contextsafe_hsd.cli --help`:

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

## Strong Deletion Candidates

Delete these if imports/tests confirm the final path does not need them:

- `contextsafe_hsd/ablation.py`
- `contextsafe_hsd/classifier.py`
- `contextsafe_hsd/utility_benchmark.py`
- `contextsafe_hsd/hf_utility.py`
- `contextsafe_hsd/models/hsd_advisory_runtime.py`
- `contextsafe_hsd/lm_context_benchmark.py`
- `contextsafe_hsd/presidio_compare.py`
- `contextsafe_hsd/presidio_augment.py`
- `contextsafe_hsd/rerank.py`
- `contextsafe_hsd/semantic_triage.py`
- `contextsafe_hsd/source_report.py`
- `contextsafe_hsd/span_providers/gliner.py`
- dataset preparation modules if hand-in does not need regeneration
- synthetic/config-search/experiment scripts not needed for the demo

Delete matching tests when the feature is intentionally removed. Do not keep
legacy tests just to preserve legacy behavior.

## Docs Cleanup Target

Keep the explanation path short:

- `README.md`
- `docs/runbooks/quickstart.md`
- `docs/runbooks/workbench.md` if the workbench stays
- `docs/reference/data_contract.md`
- `docs/reference/pipeline.md`
- `docs/reference/providers_and_models.md`
- `docs/planning/current_status.md`

Archive or delete old research/planning/challenge docs that make removed
methods look active.

## Verification

Required checks after final cleanup:

```bash
python -m ruff check contextsafe_hsd workbench/backend tests
python -m pytest -q
npm --prefix workbench/frontend run build
```

Final smoke:

- sample 25-100 rows without printing raw text;
- run `protect --preset exact --llm-review local-llm`;
- verify exact CSV shape, selected text replacement only, sidecar LLM status,
  parse/fallback counts, reason tag counts, PII suggestion counts, and no
  appended helper columns.

## Handoff Notes

- Current local LLM endpoint: `http://100.120.207.64:1234/v1/chat/completions`
- Current local LLM model: `openai/gpt-oss-20b`
- Do not commit `.vscode/` or generated `data/` outputs.
- Prefer deletion over preserving unused research paths. The user is willing
  to let future agents reimplement old tools if they are ever needed.
