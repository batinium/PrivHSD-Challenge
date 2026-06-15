# Parallel Agent Workstreams

Status: active
Owner area: coordination
Last verified: 2026-06-14
Primary code: repository-wide

Use this file before starting a multi-agent pass. Each agent should choose one
workstream, update only that workstream's primary code/docs unless coordination
is needed, and leave a short handoff note in the relevant planning or run note.
The current product shape is one pipeline with multiple entry points, not
competing pipeline forks.

## Coordination Rules

1. Pick a workstream and stay inside its boundary.
2. Update the authoritative doc for that workstream, not every related doc.
3. If a change crosses boundaries, update both owners' docs with only the
   contract-level information each side needs.
4. Put commands and operational recipes in `docs/runbooks/`.
5. Put stable architecture and interfaces in `docs/reference/`.
6. Put current status, risks, and future work in `docs/planning/`.
7. Keep raw rows, generated reports, model weights, and run logs under ignored
   `data/` paths.
8. Do not paste sensitive examples into markdown, issues, commits, or chat.

## Workstream Map

| Workstream | Primary code | Primary docs | Verification |
| --- | --- | --- | --- |
| CSV contract and submission | `contextsafe_hsd/csv_pipeline.py`, `contextsafe_hsd/submission.py`, `contextsafe_hsd/` | `docs/reference/data_contract.md`, `docs/runbooks/official_submission.md` | `tests/test_csv_pipeline.py`, `tests/test_submission.py`, `tests/test_public_api.py` |
| Auto orchestration | `contextsafe_hsd/auto/`, `contextsafe_hsd/span_providers/`, `contextsafe_hsd/models/` | `docs/reference/pipeline.md`, `docs/reference/providers_and_models.md` | `tests/test_auto_pipeline.py`, `tests/test_span_providers.py`, `tests/test_simple_pipeline.py` |
| Deterministic masking and style | `contextsafe_hsd/detectors.py`, `contextsafe_hsd/pipeline.py`, `contextsafe_hsd/style.py`, `contextsafe_hsd/resources/` | `docs/reference/pipeline.md`, `docs/reference/evaluation.md`, `docs/planning/pii_provider_edge_case_plan.md` | `tests/test_pipeline.py`, `tests/test_style_scrubber.py`, `tests/test_synthetic_pii_stress.py` |
| Metrics and evaluation | `contextsafe_hsd/metrics.py`, `contextsafe_hsd/cue_checks.py`, `contextsafe_hsd/source_report.py`, `contextsafe_hsd/author_risk.py`, `contextsafe_hsd/semantic_triage.py`, `contextsafe_hsd/metadata_leakage.py` | `docs/reference/evaluation.md`, `docs/planning/current_status.md` | `tests/test_metrics.py`, `tests/test_cue_checks.py`, `tests/test_source_report.py`, `tests/test_author_risk.py` |
| Author-aware group privacy | `contextsafe_hsd/contribution_bounding.py`, `contextsafe_hsd/author_risk.py`, `contextsafe_hsd/rerank.py`, future authorship-obfuscation runtimes under `contextsafe_hsd/models/` | `docs/planning/author_aware_group_privacy_plan.md`, `docs/reference/evaluation.md`, `docs/reference/data_contract.md` | `tests/test_contribution_bounding.py`, `tests/test_author_risk.py`, `tests/test_rerank.py` |
| Local LLM sidecar review | `contextsafe_hsd/models/local_llm_hsd_review_runtime.py`, `contextsafe_hsd/simple_pipeline.py`, `contextsafe_hsd/auto/` | `docs/reference/providers_and_models.md`, `docs/reference/pipeline.md` | `tests/test_local_llm_hsd_review_runtime.py`, `tests/test_local_llm_hsd_suggestions.py`, `tests/test_simple_pipeline.py` |
| Candidate selection and reranking | `contextsafe_hsd/rerank.py`, `contextsafe_hsd/auto/engine.py` | `docs/reference/pipeline.md`, `docs/reference/providers_and_models.md` | `tests/test_rerank.py`, `tests/test_auto_pipeline.py` |
| Workbench | `workbench/backend/`, `workbench/frontend/`, `launch.py` | `docs/runbooks/workbench.md`, `workbench/README.md` | `tests/test_workbench_csv.py`, `cd workbench/frontend && npm run build` |
| Challenge, pitch, and governance | `docs/challenge/`, `docs/research/`, `docs/planning/` | `docs/challenge/`, `docs/research/methodology.md`, `docs/research/legal_governance.md` | Link check plus manual review |

## Cross-Boundary Contracts

- Submission changes must preserve the exact CSV contract in
  `docs/reference/data_contract.md`.
- `create-submission` is the exact-format upload path and requires
  `--replace-text`; `sanitize-classify` is an enriched local triage path that
  appends advisory HSD columns and is not exact-format.
- Provider/model changes must keep optional components local-only by default
  and record missing dependencies/artifacts instead of failing exact output.
- Evaluation changes must separate fast exact-submission metrics from sampled
  or deep audit metrics.
- Workbench changes must not introduce raw-text logging or external API calls.
- Token-policy changes must remain advisory unless a reranking/audit path
  accepts the candidate.

## Handoff Note Template

```md
Workstream:
Changed:
Verification:
Remaining risks:
Touched docs:
Touched tests:
```
