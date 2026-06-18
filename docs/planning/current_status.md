# Current Status

Status: locked MVP profile selected
Last verified: 2026-06-18

ContextSafe-HSD is now reduced to the final exact CSV pipeline plus an Expo
mobile/web review app. The current competition direction is deterministic
privacy protection plus classifier-friendly utility preservation, with a
fine-tuned local HF classifier as the scalable HSD sidecar and GPT/local LLM
kept as backup/audit tooling.

## Locked MVP Profile

The competition baseline is locked for the mobile-application handoff. The
protected CSV for upload remains the final copied artifact:

`data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv`

It is byte-identical to the scored #17 artifact and the recovered HF-sidecar
rerun:

`data/outputs/style_tradeoff_no_simplify_20260617/train_split.no_simplify.protected.csv`

`data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv`

The corresponding locked mobile/audit command is:

```bash
python -m contextsafe_hsd.cli protect \
  --input data/train/train_split.csv \
  --output data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --hsd-classifier hf \
  --hf-hsd-model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
  --hf-hsd-threshold 0.850469 \
  --llm-verifier off \
  --pii-assist \
  --candidate-selection \
  --no-style-simplify-language \
  --manifest data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/manifest.json \
  --audit data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/audit.json \
  --progress
```

Frozen behavior:

- deterministic direct/technical PII masking stays on
- Presidio and scrubadub PII Assist stay enabled when installed
- strict residual PII cleanup stays on
- cue-safe style scrubbing stays on
- `style_scrubbed` candidates are generated for every row before selection
- language simplification stays off
- author-group detector-backed residual masking stays on
- HF HSD classifier sidecar stays on for mobile/audit queue metadata
- GPT/local LLM verifier, DPMLM, TF-IDF masking, and semantic clustering stay
  out of the default path

Private leaderboard context:

| Run | Candidate | Score | Decision |
| --- | --- | ---: | --- |
| #17 | `train_split.no_simplify.protected` | `0.3721` | frozen MVP |
| 2026-06-18 | `train_split.no_simplify_hf.recovered.protected` | `0.37` | locked profile; CSV-identical to #17 |
| #18 | `train_split.full_style.protected` | `0.3702` | no gain |
| #23 | `train_split.semantic_cluster_guarded.protected` | `0.3696` | no gain, more complexity |
| #24 | `train_split.semantic_cluster_ranked.protected` | `0.2524` | too destructive |
| #21 | broad low-impact token masking | `0.3524` | worse than baseline |
| #14 | LLM/checker run | `0.3835` | research only, too slow for MVP |

The lock decision is to preserve the explainable no-simplify path, keep the HF
sidecar for mobile queue metadata, and move product work to the mobile
application. Experiments remain useful notes, but they should not be promoted
without a clear private-score gain.

## Public Runtime

- `protect`
- `validate-submission`
- `profile-dataset`

The current locked scored mobile/upload command is:

```bash
python -m contextsafe_hsd.cli protect \
  --input INPUT.csv \
  --output OUTPUT.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --hsd-classifier hf \
  --hf-hsd-model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
  --hf-hsd-threshold 0.850469 \
  --llm-verifier off \
  --pii-assist \
  --candidate-selection \
  --no-style-simplify-language \
  --manifest OUTPUT.manifest.json \
  --audit OUTPUT.audit.json \
  --progress
```

This is the selected MVP path for mobile upload generation. It keeps PII Assist
and candidate selection enabled, generates a `style_scrubbed` candidate for
every row, disables language simplification, runs the HF sidecar classifier, and
keeps the verifier off. The 2026-06-18 recovered run on
`data/train/train_split.csv` (`1154` rows) completed in `1251.76s`, produced a
valid CSV with `799` changed text cells, and matches the saved
`train_split.no_simplify.protected` baseline, which scored `0.37` / `0.3721`.

Use `--no-pii-assist --no-candidate-selection` only for deterministic-only smoke
tests; that path was faster but hurt the score.

The sidecar verifier is available for positive labels from a selected sidecar
classifier; it records disagreement and uncertainty in the sidecars only and
does not change labels or CSV text.

Current score context:

- Current locked scored run reported `0.37` and is CSV-identical to the #17
  `0.3721` artifact.
- The older `0.3835` LLM/checker run remains research-only because it is too
  slow and complex for the MVP mobile path.
- Best current supervised classifier: `Hate-speech-CNERG/dehatebert-mono-english`
  fine-tuned on the official train split with 5-fold OOF validation.
  OOF best F1 is `0.8289` at threshold `0.850469`; the final checkpoint is
  `data/outputs/dehatebert_official_kfold_20260617/final_model`.
- Other checked supervised runs did not beat that single model:
  HateXplain BERT OOF best F1 `0.8200`, RoBERTa-large `0.8228`,
  DeHateBERT with 6% warmup `0.8279`, and a DeHateBERT/HateXplain OOF
  ensemble only reached `0.8295`.
- Public merged data alone and a 5k public-data augmentation screen hurt
  official-fold validation, so external data should be teacher-filtered or
  curriculum-trained before using it in the primary model.
- The challenge objective is
  `TO = Utility_protected / Utility_original - Privacy_protected / Privacy_original`.
- Higher is better, so the next default direction is to remove direct and
  stylistic re-identification cues while preserving HSD semantics rather than
  rewriting comments broadly.

## Optional Verifier And Evaluation

The second verifier is retained as an opt-in `protect` sidecar safeguard. The
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
- Current recommendation: keep the verifier only as an optional sidecar audit
  safeguard. Do not promote a small-model override or routine
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
- optional local LLM sidecar review
- optional local LLM second verifier for sidecar-only audit evidence
- isolated mini verifier evaluation CLI for model comparison
- exact CSV validation
- cue-safe style scrubbing and conservative author-group masking on by default
- Expo mobile/web review app

## Expo Mobile/Web Review App

The legacy FastAPI/Vite workbench has been removed. The new product surface is
`mobile/`, an Expo app with two MVP screens:

- Admin dashboard for the locked baseline batch, output CSV path, restatement
  model selection, and restatement leakage guard state.
- Citizen swipe review deck that shows guarded restatements only and records
  `confirmed_hatred`, `not_hatred`, or `uncertain` decisions.

The current Expo app uses seeded data from the locked baseline while the backend
contract is built. Reviewer-facing surfaces must not expose raw source text.
Restatements must pass a direct-identifier guard before entering the deck.

## Handoff 2026-06-17

Completed:

- Renamed the mini verifier evaluation module and docs away from the old
  experimental naming: `contextsafe_hsd/mini_verifier.py`,
  `tests/test_mini_verifier.py`, and `docs/planning/mini_verifier_eval/`.
- Removed the one-off Qwen comparison script.
- Added `contextsafe_hsd/models/local_llm_hsd_verifier_runtime.py`; it is now
  opt-in with `--llm-verifier local-llm` for selected sidecar classifier runs.
  It reviews only main-model positive rows and never changes CSV text or labels.
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
- Removed the legacy workbench app, workbench launcher, and workbench tests.
- Added the Expo `mobile/` app with admin and citizen swipe review screens.
- Added an in-app restatement leakage guard for direct identifiers.
- Cleaned temporary files: Python bytecode, `.pytest_cache`, `.ruff_cache`,
  frontend `dist/`, and the duplicate run `cli_stdout.json`.

Checks passed:

```bash
python -m pytest -q
python -m ruff check contextsafe_hsd tests
cd mobile && npm run lint && npx tsc --noEmit
```

Left for next session:

- Replace the seeded mobile data with a real protected CSV + audit import API.
- Wire admin-selected restatement model calls behind a backend that never sends
  raw source text to citizen screens.
- If more model work is desired, keep it under ignored `data/outputs/` and do
  not change the sidecar-only verifier contract without a new full metric run.

## Verification To Keep Current

```bash
python -m ruff check contextsafe_hsd tests
python -m pytest -q
cd mobile && npm run lint && npx tsc --noEmit
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
