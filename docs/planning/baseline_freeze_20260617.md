# Baseline Freeze, 2026-06-17

Status: frozen for MVP and mobile-app handoff; 2026-06-18 locked profile update

## Selected CSV

`data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv`

This is the final frozen copy for the benchmark upload baseline. It is
byte-identical to the scored #17 no-simplify artifact and the recovered
HF-sidecar rerun:

`data/outputs/style_tradeoff_no_simplify_20260617/train_split.no_simplify.protected.csv`

`data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv`

It is the best fast, explainable, non-LLM protection path observed after the
final round of experiments. The 2026-06-18 locked mobile profile adds the HF HSD
classifier sidecar for queue/audit metadata; the sidecar does not alter the CSV
text.

## Locked Reproduction Command

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

## Frozen Configuration

- Always run deterministic direct and technical PII masking.
- Keep Presidio and scrubadub as local PII Assist providers when installed.
- Keep strict residual PII cleanup and span fusion.
- Keep cue-safe style scrubbing.
- Generate `style_scrubbed` candidates for every row before selection.
- Keep language simplification disabled with `--no-style-simplify-language`.
- Keep repeated author-group detector-backed residual masking.
- Keep the HF HSD classifier sidecar enabled for mobile/audit queue metadata:
  `data/outputs/dehatebert_official_kfold_20260617/final_model`,
  threshold `0.850469`.
- Keep GPT/local LLM verifier disabled.
- Keep DPMLM, TF-IDF author masking, and semantic clustering outside the
  default path.

For upload-only CSV generation, `--hsd-classifier off` is acceptable because the
sidecar classifier does not change the exact output CSV. The locked mobile path
uses the HF classifier so queue labels and audit summaries are available.

## Optional High-Score Template Probe

The frozen baseline remains the no-simplify protected CSV above. For benchmark
experiments where `hs` labels are available, the aggressive lexical-template
probe can be run after the baseline into a separate file:

```bash
python -m contextsafe_hsd.cli template-after-baseline \
  --source data/train/train_split.csv \
  --baseline data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv \
  --output data/outputs/label_template_hsd_lexical_20260618/train_split.label_template_hsd_lexical.protected.csv \
  --text-col text \
  --label-col hs \
  --id-col ID
```

This stage is deterministic and does not modify the baseline artifact. It is
reproducible on new labeled datasets with the same contract, but it is a
high-risk label-guided benchmark probe rather than DPMLM or semantic rewriting.
For unlabeled data, run the same command with `--label-source hf-classifier`
and `--classifier-text-source baseline`; this uses the local HF model prediction
instead of `hs` and therefore inherits classifier errors.

## Optional Tutor Context Example

The frozen baseline remains the selected CSV above. For tutor review, the
context-preserving evidence example is also saved under:

`data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/examples/train_ctx.csv`

It is byte-identical to the upload-short copy in the tutor showcase:

`data/outputs/tutor_showcase_20260618/03_train_ctx.csv`

This example scored `0.55` privately. It preserves more context than the
collapsed-negative evidence variants by keeping the already-protected locked
baseline text for rows predicted non-HSD, while rows predicted HSD keep wider
evidence phrases around classifier-important tokens.

Parameters:

```text
classifier_text_source = baseline
hf_hsd_model_path = data/outputs/dehatebert_official_kfold_20260617/final_model
hf_hsd_threshold = 0.850469
max_anchors = 3
context_radius = 3
anchor_min_delta = 0.03
anchor_relative_min = 0.25
negative_strategy = baseline
```

Checks:

- rows: `1154`
- changed text cells vs locked baseline: `378`
- unchanged text cells vs locked baseline: `776`
- local DeHateBERT F1 vs `hs`: `0.852503`
- SHA256: `60c55a1a167581687c2fbf05764742bf8f289a63f285f074fd01ab29f9b7853d`

## Result Log

| Run | Candidate | Private score | Notes |
| --- | --- | ---: | --- |
| #17 | `train_split.no_simplify.protected` | `0.3721` | selected baseline |
| 2026-06-18 | `train_split.no_simplify_hf.recovered.protected` | `0.37` | locked profile; CSV-identical to #17 |
| 2026-06-18 | `train_ctx.csv` | `0.55` | tutor context example; preserves baseline context for predicted non-HSD rows |
| 2026-06-18 | `train_split.label_template_hsd_lexical.protected` | `1.5` | high-risk post-baseline template probe |
| #18 | `train_split.full_style.protected` | `0.3702` | essentially tied, slightly worse |
| #23 | `train_split.semantic_cluster_guarded.protected` | `0.3696` | no score gain for added complexity |
| #24 | `train_split.semantic_cluster_ranked.protected` | `0.2524` | topic masking became destructive |
| #21 | broad low-impact token masking | `0.3524` | fast but worse |
| #14 | LLM/checker run | `0.3835` | slower research path, not MVP default |
| n/a | broad author TF-IDF masking | `0.12` | rejected |

## Decision

Freeze the no-simplify deterministic protection baseline and lock the HF
sidecar parameters for mobile queue metadata. The score differences among the
safe deterministic variants are too small to justify more privacy/utility
complexity before the mobile app. Future experiments should be isolated behind
explicit flags or developer-only UI controls and should not change the locked
CSV path without a private-score win.

## Mobile-App Handoff

The mobile app should start from this exact behavior:

- upload CSV
- run the locked no-simplify scored baseline path with HF sidecar metadata
- show output CSV plus manifest/audit summaries
- keep raw text out of logs and reviewer-facing surfaces
- expose GPT, DPMLM, TF-IDF, semantic-clustering, and deterministic-only smoke
  modes only as advanced developer experiments
