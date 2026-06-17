# Current Status

Status: active
Last verified: 2026-06-17

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
  --llm-verifier local-llm \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json
```

`--llm-review off --llm-verifier off` is supported for offline exact runs. The
AI-audits-AI sidecar verifier is default-on for local LLM runs and reviews main
positive labels. It records disagreement and uncertainty in the sidecars only;
it does not change labels or CSV text.

## Optional Verifier And Evaluation

The second verifier is retained as a default-on `protect` sidecar safeguard. The
model-comparison workflow remains isolated as an evaluation command:

```bash
python -m contextsafe_hsd.cli mini-verifier-eval \
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
`docs/planning/mini_verifier_eval/prompt.md`.

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
- `openai/gpt-oss-20b` was tested as a same-model verifier prompt on
  2026-06-17. The normal classifier batches correctly at 10 rows through
  tool-calling; a batch-size check on 80 balanced rows found batch `10` had
  recall `0.7750` vs batch `1` recall `0.7000`, so batching was not the recall
  problem in that check. Verifier prompts must also use tool-calling; JSON
  schema response-format batches collapsed to the first item. Full 460-row
  tool-call verifier tests still damaged too many true positives:
  `current_tool` rescued 14 FP and damaged 19 TP, while
  `human_review_router_tool` rescued 72 FP and damaged 73 TP.
- Current recommendation: keep the verifier in the default runtime only as a
  sidecar audit safeguard. Do not promote a small-model override or routine
  routed adjudication path without a much better precision/recall and latency
  profile.

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
- optional local LLM second verifier for sidecar-only audit evidence
- isolated mini verifier evaluation CLI for model comparison
- exact CSV validation
- author-group masking off by default
- optional workbench demo

## Citizen Validation Dashboard

The workbench review queue now supports a citizen-validation conversion layer:

- LLM restatements are generated from protected text only. The frontend enables
  the citizen restatement path by default for local LLM CSV processing; the API
  still supports disabling it for offline/exact runs.
- The restatement is the primary civilian-facing evidence for the hate-speech
  vote; masked protected text is not shown in the citizen jury view, and raw
  text is not retained in review annotations.
- Optional semantic similarity uses a local sentence-transformers embedding
  model to compare original text with the LLM restatement and stores only the
  score/status.
- Citizen votes are stored as structured `final_hsd_label` review labels:
  `confirmed_hatred`, `not_hatred`, or `uncertain`.
- Processed dashboard results are cached by CSV hash plus all relevant runtime
  options, including local LLM review, restatement, and embedding models. The
  portal can list and reload recent processed results without rerunning these
  stages.

## Handoff 2026-06-17

Completed:

- Renamed the mini verifier evaluation module and docs away from the old
  experimental naming: `contextsafe_hsd/mini_verifier.py`,
  `tests/test_mini_verifier.py`, and `docs/planning/mini_verifier_eval/`.
- Removed the one-off Qwen comparison script.
- Added `contextsafe_hsd/models/local_llm_hsd_verifier_runtime.py` and wired
  `protect` so `--llm-verifier local-llm` is the default sidecar verifier for
  local LLM review runs. It reviews only main-model positive rows and never
  changes CSV text or labels.
- Ran the verifier-enabled pipeline on `data/train/train_split.csv`.
  Artifacts are under
  `data/outputs/train_split_verifier_enabled_20260617_050133/`:
  `train_split.protected.csv`, `protect_result.json`, and `audit.json`.
- Validation passed with exact columns preserved:
  `ID, author, text, hs`; 1,154 source rows and 1,154 output rows.
- Main classifier result on that run: 1,154 parsed rows, 20 fallbacks,
  predictions `691` negative and `463` positive.
- Verifier result on that run: 463 reviewed positives, 429 agree,
  21 disagree, 13 uncertain, 34 human-review candidates, and label overrides
  disabled.
- Updated the workbench into a Zero-Trust Citizen Jury flow: civilian-facing
  queue uses `citizen_evidence` from LLM restatement, removes legacy reviewer wording,
  hides masked/raw text from the review UI, records structured citizen votes,
  includes verifier metadata, and uses European Council-style blue/gold colors.
- Updated the workbench CSV cache key/version so processed results include
  verifier, restatement, and semantic-model options.
- Confirmed `launch.py` starts both backend and frontend on alternate ports and
  shuts down cleanly.
- Cleaned temporary files: Python bytecode, `.pytest_cache`, `.ruff_cache`,
  frontend `dist/`, and the duplicate run `cli_stdout.json`.

Checks passed:

```bash
python -m pytest -q
python -m ruff check contextsafe_hsd tests workbench/backend
npm --prefix workbench/frontend run build
python launch.py --help
python launch.py --backend-port 8011 --frontend-port 5181
```

Left for next session:

- The portal revision is implemented and tested, but the live
  `sentence-transformers/all-MiniLM-L6-v2` semantic embedding download/check was
  interrupted before completion. The code path is wired; run it once in a
  network-ready environment to warm the model cache and confirm live scoring.
- Review the uncommitted diff and decide whether to commit all verifier,
  workbench, docs, and test changes together or split into separate commits.
- If more model work is desired, keep it under ignored `data/outputs/` and do
  not change the sidecar-only verifier contract without a new full metric run.

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
