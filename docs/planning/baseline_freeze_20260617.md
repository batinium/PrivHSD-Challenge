# Baseline Freeze, 2026-06-17

Status: frozen for MVP and mobile-app handoff

## Selected CSV

`data/outputs/frozen_final_baseline_20260617/train_split.frozen_baseline.protected.csv`

This is the final frozen copy for the benchmark upload baseline. It is
byte-identical to the scored #17 no-simplify artifact:

`data/outputs/style_tradeoff_no_simplify_20260617/train_split.no_simplify.protected.csv`

It is the best fast, explainable, non-LLM path observed after the final round
of experiments.

## Reproduction Command

```bash
python -m contextsafe_hsd.cli protect \
  --input data/train/train_split.csv \
  --output data/outputs/frozen_final_baseline_20260617/train_split.frozen_baseline.protected.csv \
  --text-col text \
  --id-col ID \
  --preset exact \
  --hsd-classifier off \
  --llm-verifier off \
  --no-style-simplify-language \
  --manifest data/outputs/frozen_final_baseline_20260617/protect_result.json \
  --audit data/outputs/frozen_final_baseline_20260617/audit.json \
  --progress
```

## Frozen Configuration

- Always run deterministic direct and technical PII masking.
- Keep Presidio and scrubadub as local PII Assist providers when installed.
- Keep strict residual PII cleanup and span fusion.
- Keep cue-safe style scrubbing.
- Keep language simplification disabled with `--no-style-simplify-language`.
- Keep repeated author-group detector-backed residual masking.
- Keep GPT/local LLM verifier disabled.
- Keep DPMLM, TF-IDF author masking, and semantic clustering outside the
  default path.

For upload CSV generation, `--hsd-classifier off` is acceptable because the
sidecar classifier does not change the exact output CSV. Use the HF classifier
only when local audit evidence is needed.

## Result Log

| Run | Candidate | Private score | Notes |
| --- | --- | ---: | --- |
| #17 | `train_split.no_simplify.protected` | `0.3721` | selected baseline |
| #18 | `train_split.full_style.protected` | `0.3702` | essentially tied, slightly worse |
| #23 | `train_split.semantic_cluster_guarded.protected` | `0.3696` | no score gain for added complexity |
| #24 | `train_split.semantic_cluster_ranked.protected` | `0.2524` | topic masking became destructive |
| #21 | broad low-impact token masking | `0.3524` | fast but worse |
| #14 | LLM/checker run | `0.3835` | slower research path, not MVP default |
| n/a | broad author TF-IDF masking | `0.12` | rejected |

## Decision

Freeze the no-simplify deterministic baseline. The score differences among the
safe deterministic variants are too small to justify more privacy/utility
complexity before the mobile app. Future experiments should be isolated behind
explicit flags or developer-only UI controls and should not change the default
CSV path without a private-score win.

## Mobile-App Handoff

The mobile app should start from this exact behavior:

- upload CSV
- run the frozen baseline path
- show output CSV plus manifest/audit summaries
- keep raw text out of logs and reviewer-facing surfaces
- expose experimental GPT, DPMLM, TF-IDF, and semantic-clustering modes only as
  advanced developer experiments
