# Current Status

Status: active
Last verified: 2026-06-16

ContextSafe-HSD is now reduced to the final exact CSV pipeline plus a compact
optional workbench demo.

## Public Runtime

- `protect`
- `validate-submission`
- `profile-dataset`

The final command is:

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

`--llm-review off` is supported for offline exact runs.

## Research-Only Verifier Ablation

The mini 4B verifier ablation is implemented as an isolated research command,
not part of the public hand-in runtime:

```bash
python -m contextsafe_hsd.cli mini-4b-verifier-ablation \
  --endpoint http://100.120.207.64:1234/v1/chat/completions \
  --timeout-seconds 180 \
  --batch-size 10 \
  --progress
```

Current result:

- Best safer small candidate: `qwen/qwen3-4b`
- Full-sample positive-verifier follow-up completed as a research artifact
- Do not promote recall-router, combined-router, or uncensored-probe behavior to
  the default runtime yet

The detailed handoff is in
`docs/planning/mini_4b_verifier_ablation/prompt.md`.

Full-sample follow-up on 2026-06-16:

- `qwen/qwen3-4b` completed the full direct + positive-verifier comparison.
  Positive verifier precision improved from `0.6065` to `0.7009`, but recall
  fell from `0.7644` to `0.4493`; do not use it for automatic label changes.
- `qwen/qwen3.5-9b` and `google/gemma-4-12b` were attempted as positive
  verifier-only reviewers on the 460 main-positive rows. Both exceeded the
  practical wait window in the current LM Studio setup and were recorded as
  `aborted_impractical_latency` under ignored `data/outputs/` artifacts.
- `qwen/qwen3.5-9b` was rerun on 2026-06-17 with temperature `0` and Qwen
  thinking disabled. The run completed on 460 main-positive rows with precision
  `0.6235`, recall `0.5808`, F1 `0.6014`, and `0` observed reasoning tokens.
  It rescued 53 false positives but damaged 67 true positives.
- Current recommendation: keep verifier models as offline/council audit
  evidence only. Do not promote a small-model override or routine routed
  adjudication path without a much better precision/recall and latency profile.

## Cleanup Completed

Removed from the public package:

- reranker module and tests
- classifier module and tests
- HSD advisory runtime
- GLiNER provider
- semantic triage, source reports, utility benchmarks
- dataset prep helpers and scripts
- generated experiment artifacts

Retained:

- deterministic row-level sanitization
- Presidio/scrubadub PII Assist
- span fusion and residual cleanup
- cue safeguards
- local LLM sidecar review
- isolated mini 4B verifier ablation CLI for research only
- exact CSV validation
- author-group masking off by default
- optional workbench demo

## Citizen Validation Dashboard

The workbench review queue now supports a citizen-validation conversion layer:

- LLM restatements are generated from protected text only when explicitly
  enabled in the CSV dashboard request.
- The restatement is the primary civilian-facing evidence for the hate-speech
  vote; protected text remains available as masked evidence, and raw text is not
  retained in review annotations.
- Optional semantic similarity uses a local sentence-transformers embedding
  model to compare original text with the LLM restatement and stores only the
  score/status.
- Citizen votes are stored as structured `final_hsd_label` review labels:
  `confirmed_hatred`, `not_hatred`, or `uncertain`.
- Processed dashboard results are cached by CSV hash plus all relevant runtime
  options, including local LLM review, restatement, and embedding models. The
  portal can list and reload recent processed results without rerunning these
  stages.

## Verification To Keep Current

```bash
python -m ruff check contextsafe_hsd tests workbench/backend
python -m pytest -q
npm --prefix workbench/frontend run build
```

Run a small smoke before hand-in:

```bash
python -m contextsafe_hsd.cli protect \
  --input /tmp/contextsafe-smoke/input.csv \
  --output /tmp/contextsafe-smoke/output.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --llm-review off \
  --manifest /tmp/contextsafe-smoke/output.manifest.json \
  --audit /tmp/contextsafe-smoke/output.audit.json
```

Then validate:

```bash
python -m contextsafe_hsd.cli validate-submission \
  --source /tmp/contextsafe-smoke/input.csv \
  --submission /tmp/contextsafe-smoke/output.csv \
  --text-col text
```

Generated smoke files belong under `/tmp` or ignored `data/` paths.
