# Roadmap

Status: active
Owner area: future engineering plan
Last verified: 2026-06-13
Primary code: all workstreams

This roadmap contains future work only. Current evidence lives in
`docs/planning/current_status.md`; stable architecture lives in
`docs/reference/pipeline.md`.

## Phase A: Performance And Fast Metrics

Tasks:

- Keep fast metrics separate from deep metrics.
- Ensure `create-submission` defaults to fast metrics.
- Avoid expensive target-variant, spaced-token, external profanity, and
  semantic scans in the default exact path.
- Add or maintain performance tests for official-style datasets.

Acceptance:

- Focused tests pass.
- Full test suite passes.
- Exact-format four-column regression passes.
- Exact submission stays practical on the local testing datasets.

## Phase B: Auto Context And Provider Lifecycle

Tasks:

- Keep provider/model discovery in `privhsd/auto/`.
- Load providers/models once per run.
- Record provider/model statuses.
- Maintain fake provider/model tests proving one load per run.

Acceptance:

- Missing optional dependency does not fail exact submission.
- Available providers initialize once per run.
- Available token-policy artifacts are detected and batched, not loaded per row.

## Phase C: Row Routing And Candidate Selection

Tasks:

- Compute cheap row features.
- Route only risky rows to optional providers/models.
- Fuse spans and generate candidates.
- Rerank and select the least destructive safe candidate.
- Fall back to baseline on uncertainty/errors.
- Implement the PII provider and edge-case plan in
  `docs/planning/pii_provider_edge_case_plan.md`: obfuscated email detection,
  reported-person contexts, short-name threat cue preservation, conservative
  alias handling, and provider benchmarks.
- Implement the privacy span model integration plan in
  `docs/planning/privacy_span_model_integration_plan.md`: expose GLiNER model
  selection, add a PII GLiNER profile, batch provider inference, benchmark
  `nvidia/gliner-PII`, and keep `openai/privacy-filter` as a secondary
  optional provider.

Acceptance:

- Auto mode preserves exact CSV shape.
- Auto masks at least as many direct identifiers as balanced on fixtures.
- Auto does not reduce target/action/negation retention on fixtures.
- Audits explain decisions without raw text.

## Phase D: Token-Policy Runtime

Tasks:

- Keep token-policy ensemble as an advisory provider.
- Batch inference.
- Convert token actions to provider evidence and candidate support.
- Gate final text through fusion and reranking.

Acceptance:

- Existing token-policy tests pass.
- Runtime load-count tests pass.
- Missing model artifacts produce safe fallback.

## Phase E: Workbench Auto UX

Tasks:

- Keep CSV auto mode as the default workbench path.
- Show provider/model status.
- Make exact-format vs helper-column output explicit.
- Download CSV, audit JSON, and manifest.
- Avoid raw-text logs.

Acceptance:

- Backend workbench CSV tests pass.
- Frontend production build passes.
- Four-column CSV round trip works through the API.

## Phase F: Deep Evaluation And Research Paths

Tasks:

- Add deep metrics and benchmark reports under ignored `data/outputs/`.
- Implement the public dataset evaluation handoff in
  `docs/planning/public_dataset_evaluation_integration_plan.md`: PII
  gold-span adapters, character span precision/recall, HateXplain destructive
  interference, HateCheck functionality drift, Jigsaw identity slices, and
  GLiNER provider replacement benchmarks.
- Add semantic drift scorers where dependencies exist.
- Implement the external utility-probe plan in
  `docs/planning/utility_probe_integration_plan.md`: registry metadata,
  Cardiff multiclass target drift, binary advisory ensemble, Detoxify
  toxicity-bias audit, continuous Measuring Hate Speech scores, MUDES toxic
  spans, and HateXplain rationale runtime.
- Add weak supervision and metadata privacy reports.
- Keep DPMLM, SanText, and LLM candidates behind reranking.

Acceptance:

- Deep reports are opt-in.
- Basic exact-format submission remains fast.
- Official path stays local-only and exact-format.
