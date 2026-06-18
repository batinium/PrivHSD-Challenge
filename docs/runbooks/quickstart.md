# Quickstart

Status: active
Last verified: 2026-06-18

## Install

```bash
python -m pip install -e '.[dev]'
```

Optional local helpers:

```bash
python -m pip install -e '.[presidio,scrubadub,hf]'
```

## Verify

```bash
python -m ruff check contextsafe_hsd tests
python -m pytest -q
python -m contextsafe_hsd.cli --help
python -m contextsafe_hsd.cli protect --help
cd mobile && npm run lint && npx tsc --noEmit
```

## Protect A CSV

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

This is the locked scored no-simplify mobile/upload path. It keeps deterministic
PII masking, Presidio/scrubadub PII Assist, candidate selection, exact CSV
validation, and language simplification disabled. Cue-safe style scrubbing is
on, and a `style_scrubbed` candidate is generated for every row before
selection. It preserves row order, row count, and all input columns; only the
configured text column is replaced.

## Optional Template Probe After Baseline

If a benchmark run has labels available, the aggressive template probe can be
emitted after the baseline run as a separate CSV:

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
  --template-after-baseline-output OUTPUT.template.protected.csv \
  --template-label-source column \
  --template-label-col hs \
  --progress
```

This does not overwrite `OUTPUT.csv`; it writes
`OUTPUT.template.protected.csv` and a `.manifest.json` sidecar. The method is
deterministic for a given dataset and ID column, but it requires the `hs` label
column. For unlabeled future data, this exact label-guided version is not
reproducible without first predicting labels.

For unlabeled runtime data, predict the label locally:

```bash
python -m contextsafe_hsd.cli template-after-baseline \
  --source INPUT.csv \
  --baseline OUTPUT.csv \
  --output OUTPUT.template.predicted.protected.csv \
  --text-col text \
  --id-col ID \
  --label-source hf-classifier \
  --classifier-text-source baseline \
  --hf-hsd-model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
  --hf-hsd-threshold 0.850469
```

On the locked train baseline, classifying baseline-protected text produced
`accuracy 0.9116`, `F1 0.8633` against `hs`. Classifying original source text
with the same final checkpoint produced `accuracy 0.9073`, `F1 0.8568`. These
are train-split diagnostics; the honest held-out estimate remains the 5-fold
out-of-fold classifier score.

To run it after an already completed baseline:

```bash
python -m contextsafe_hsd.cli template-after-baseline \
  --source INPUT.csv \
  --baseline OUTPUT.csv \
  --output OUTPUT.template.protected.csv \
  --text-col text \
  --label-col hs \
  --id-col ID
```

## Optional Evidence Extraction After Baseline

For the post-event evidence-abstraction showcase, compute token importances and
then run `evidence-after-baseline`. This produces a separate CSV plus manifest,
validation, local HF utility summary, and source-token trace sidecars.

Relaxed phrase setting:

```bash
python -m contextsafe_hsd.cli evidence-after-baseline \
  --source data/train/train_split.csv \
  --baseline data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv \
  --importance data/outputs/dpmlm_sweep_20260617/token_importance_train.csv \
  --output data/outputs/evidence_tokens_classifier_relaxed_20260618/train_split.evidence_tokens_classifier_relaxed_on_baseline.protected.csv \
  --text-col text \
  --id-col ID \
  --label-col hs \
  --classifier-text-source baseline \
  --hf-hsd-model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
  --hf-hsd-threshold 0.850469 \
  --max-anchors 3 \
  --context-radius 2 \
  --anchor-min-delta 0.03 \
  --anchor-relative-min 0.25
```

The locked baseline is not overwritten. The output is experimental
classifier-guided evidence extraction, not a semantic rewrite.

The 2026-06-18 recovered train run on `data/train/train_split.csv` (`1154`
rows) completed in `1251.76s` wall time and wrote a valid CSV to
`data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv`.
That CSV is byte-identical to the saved `train_split.no_simplify.protected`
baseline and re-scored at `0.37` / `0.3721`.

Locked run checks:

- output CSV sha256:
  `531ae6fa663124a5a570929be44bd94dfea7223d99e768a4dcc4bd029e98a12e`
- changed text cells: `799`
- chosen candidates: `balanced` `405`, `balanced_strict_pii` `1`,
  `provider_fusion_augmented` `32`, `style_scrubbed` `715`,
  `style_scrubbed_strict_pii` `1`
- HF classifier counts: `0: 773`, `1: 381`

Use the faster deterministic-only path only for smoke tests; it ran in
`252.33s` on the same data but hurt the score:

```bash
--no-pii-assist \
--no-candidate-selection
```

The fine-tuned HF sidecar classifier parameters are locked as:

```bash
--hsd-classifier hf \
--hf-hsd-model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
--hf-hsd-threshold 0.850469
```

GPT/local LLM sidecars are optional backup/audit extensions; enable them
explicitly only when you want second-pass evidence, not for the locked mobile
upload profile.

## Run The Expo App

```bash
cd mobile
npm install
npm run web
```

The current Expo app contains:

- Admin dashboard for the locked baseline batch and restatement model choice.
- Citizen review deck with swipe decisions over guarded restated evidence.
- Direct-identifier guard for restatements before they enter the review deck.

## Validate

```bash
python -m contextsafe_hsd.cli validate-submission \
  --source INPUT.csv \
  --submission OUTPUT.csv \
  --text-col text \
  --output OUTPUT.validation.json
```

## Profile Incoming Data

```bash
python -m contextsafe_hsd.cli profile-dataset \
  --input INPUT.csv \
  --text-col text \
  --id-col ID \
  --output INPUT.profile.json
```

The profile command reports schema and aggregate counts without printing raw row
text.

## Research: Mini Verifier Evaluation

This command is for local verifier comparison runs. It does not change the
official exact CSV output path.

```bash
python -m contextsafe_hsd.cli mini-verifier-eval \
  --endpoint http://100.120.207.64:1234/v1/chat/completions \
  --timeout-seconds 180 \
  --batch-size 10 \
  --progress
```

Current handoff: the runtime verifier is opt-in sidecar audit evidence for
selected sidecar classifier runs. Do not promote any verifier path to automatic
label changes without a substantially better precision/recall and latency
profile.

## Data Handling

Write generated CSVs, manifests, audits, local run notes, datasets, and model
artifacts under ignored `data/` paths. Do not commit raw sensitive examples.
