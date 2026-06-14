# Evaluation Reference

Status: active
Owner area: metrics, reports, regression gates
Last verified: 2026-06-14
Primary code: `privhsd/metrics.py`, `privhsd/cue_checks.py`,
`privhsd/source_report.py`, `privhsd/author_risk.py`,
`privhsd/semantic_triage.py`

This is the authoritative evaluation reference. Keep current results in
`docs/planning/current_status.md`.

## Metric Depth

Exact submissions default to `--metric-depth fast`.

| Depth | Use | Expected behavior |
| --- | --- | --- |
| `fast` | Default exact submissions and progress summaries | Use fast target-cue counting and avoid the deeper target/profanity-style scans on every row. |
| `sampled` | Local audit | Run deep checks on a bounded prefix sample, currently the first 100 rows by default, and fast checks afterward. |
| `deep` | Explicit local audit | Enable the deeper target-term scan for every row. |

Deep metrics must not block basic exact-format submission creation.

## Required Gates

Run these before upload or before declaring a pipeline change ready:

```bash
python -m pytest tests/test_pipeline.py tests/test_csv_pipeline.py tests/test_submission.py tests/test_auto_pipeline.py tests/test_simple_pipeline.py -q
python -m privhsd.cli validate-submission \
  --source INPUT.csv \
  --submission OUTPUT.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/OUTPUT.validation.json
```

When metadata columns exist, add source-aware regression:

```bash
python -m privhsd.cli source-regression-report \
  --original INPUT.csv \
  --protected OUTPUT.csv \
  --original-text-col text \
  --protected-text-col text \
  --id-col id \
  --group-col source \
  --group-col label \
  --group-col split \
  --output data/outputs/OUTPUT.source_regression.json
```

When repeated author/user IDs exist, add author-risk evaluation. Do not treat
unique row IDs as author labels.

## What To Record

Durable docs may record:

- command shape;
- commit hash;
- aggregate metrics;
- validation status;
- provider/model status;
- row IDs for review queues;
- limitations and skipped checks.

Durable docs must not record raw official examples or generated sensitive rows.

## Regression Focus

For meaningful pipeline changes, check:

- exact-format validation;
- direct/quasi identifier counts before and after;
- target/action/negation/modality cue retention;
- source/label/split slice regressions;
- candidate selection counts;
- runtime and provider/model load counts;
- author-risk metrics when repeated author IDs exist;
- external/unseen token-policy results when token-policy behavior changes.

## Configuration Search Protocol

Use this sequence when choosing the trusted single CSV pipeline:

1. Establish the deterministic `balanced` baseline.
2. Compare routed auto variants with providers disabled, providers only,
   token-policy only, full auto without HSD selection, and full auto with HSD
   selection.
3. Score every saved output with the same HSD advisory ensemble.
4. Choose on privacy first, then HSD decision stability, then overmasking and
   character utility. Do not choose a lower-residual config if it destroys HSD
   decisions.
5. Run the selected official command end to end through
   `create-submission --replace-text`, then validate row count, column contract,
   manifest validity, provider/model load counts where auto ran, identifier
   residuals, and cue retention.
6. Optionally mirror the same configuration through `sanitize-classify` for
   local enriched analysis of HSD advisory score drift. Do not upload that CSV,
   because it appends prediction columns.

Latest recorded local 3,830-row TweetEval unseen enriched-analysis run used
the default `sanitize-classify` path: deterministic baseline, Presidio,
scrubadub, token-policy ensemble, and two-model RoBERTa HSD advisory
selection. This was not an exact-format upload because `sanitize-classify`
appends prediction columns. Final manifest summary:

- validation: passed, 3,830 input rows -> 3,830 output rows;
- residual direct identifiers: 1 detector hit after 4,205 before;
- residual quasi identifiers: 0;
- target cue retention mean: 1.0062;
- utility cue retention mean: 1.0048;
- character utility retention mean: 0.8512;
- HSD decision agreement: 0.9802, with 76 decision changes;
- HSD positive/negative counts: 1,971 / 1,859.

## External Utility Probes

Optional external HSD/toxicity probes are research and audit evidence, not
official moderation decisions. The detailed implementation handoff for adding
probe kinds, Cardiff multiclass target drift, an HSD advisory ensemble,
continuous hate-score probes, toxicity-bias probes, and generated span/rationale
probes lives in
`docs/planning/utility_probe_integration_plan.md`.

## Public Dataset Benchmarks

Public dataset adapters and deep benchmark reports are opt-in audit workflows,
not official exact-submission requirements. The detailed implementation handoff
for PII gold-span datasets, character-level span metrics, HateXplain
destructive-interference ratios, HateCheck functionality reports, Jigsaw
identity-slice drift, and GLiNER provider replacement benchmarks lives in
`docs/planning/public_dataset_evaluation_integration_plan.md`.
