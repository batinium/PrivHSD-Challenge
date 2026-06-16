# Mini 4B Verifier Ablation Results And Next Step

Status: completed mini ablation, ready for full-sample comparison
Last verified: 2026-06-16

This note supersedes the original run prompt. The mini ablation was implemented
as a research-only CLI path and run against LM Studio. The output is promising
enough to show as a council-facing improvement direction, but not strong enough
to promote as the default runtime without a larger comparison.

## What Was Implemented

Research command:

```bash
python -m contextsafe_hsd.cli mini-4b-verifier-ablation \
  --endpoint http://100.120.207.64:1234/v1/chat/completions \
  --timeout-seconds 180 \
  --batch-size 10 \
  --progress
```

Implementation:

- `contextsafe_hsd/mini_verifier_ablation.py`
- CLI subcommand: `mini-4b-verifier-ablation`
- Tests: `tests/test_mini_verifier_ablation.py`

Artifacts are ignored and live under:

```text
data/outputs/mini_4b_verifier_ablation/
```

Generated files:

- `models_seen.json`
- `eval_set_160.csv`
- `candidate_screen_results.json`
- `shortlist_results.json`
- `adjudication_results.json`
- `recommendation.md`

## Fixed Eval Set

The ablation used a deterministic 160-row error-enriched set:

- `FP60`: 60 false positives from the prior full 20B run
- `FN60`: 60 false negatives from the prior full 20B run
- `TP20`: 20 true positives from the prior full 20B run
- `TN20`: 20 true negatives from the prior full 20B run

Baseline on this eval set is intentionally harsh because it is built from known
errors plus controls:

- Accuracy: `0.2500`
- Precision: `0.2500`
- Recall: `0.2500`
- F1: `0.2500`

Do not present these as full-dataset metrics. Present them as a targeted stress
test of known error modes.

## Models Screened

LM Studio inventory included all planned small candidates plus the exploratory
uncensored/aggressive probe.

Screened default candidates:

- `qwen/qwen3-4b-2507`
- `qwen3.5-4b`
- `qwen/qwen3-4b`
- `shieldgemma-2-4b-it`
- `google/gemma-3n-e4b`
- `mistralai/ministral-3-3b`

Stopped/excluded:

- `nvidia/nemotron-3-nano-4b`: excluded for latency under the stop condition.

Exploratory probe:

- `gemma-4-e4b-uncensored-hauhaucs-aggressive`

The uncensored probe had the best direct F1 on this mini set (`0.5190`), but it
remains exploratory only. Do not select it as the default production dependency
without manual safety inspection.

## Result Summary

Best non-probe small model:

- `qwen/qwen3-4b`

Direct small-model classifier on the 160-row mini set:

- Accuracy: `0.5000`
- Precision: `0.5000`
- Recall: `0.4000`
- F1: `0.4444`
- Confusion: TP `32`, TN `48`, FP `32`, FN `48`

Positive-verifier route for `qwen/qwen3-4b`:

- Routed rows: `48 / 160`
- Estimated eval-set overhead: `30.0%`
- FP rescue rate: `60.0%`
- FN rescue rate: `0.0%`
- TP disagree risk: `15.0%`
- TN route risk: `0.0%`
- Selection score: `0.7408`

Positive-verifier rows adjudicated by `openai/gpt-oss-20b`:

- Adjudicated rows: `48`
- Parse success: `46 / 48` (`0.9583`)
- Elapsed: `289.3s`
- Average: `6.027s` per routed row
- Final metrics on the 160-row mini set:
  - Accuracy: `0.3875`
  - Precision: `0.2353`
  - Recall: `0.1000`
  - F1: `0.1404`

The routed-to-20B adjudication prompt did not improve this mini set. The small
model's direct signal was more promising than the current 20B adjudication path.

## Strategy Decision

Use `qwen/qwen3-4b` as the model to test next.

Do not promote any strategy to the default runtime yet.

Recommended next comparison:

1. Keep the existing `openai/gpt-oss-20b` full-run output as baseline.
2. Run a larger full-sample comparison with `qwen/qwen3-4b`.
3. Compare at least these variants:
   - small-model direct labels as a measurement-only upper bound
   - positive verifier direct flip as a measurement-only upper bound
   - positive verifier routed to a revised adjudication prompt
4. Treat recall-router and combined-router variants as secondary. In the mini
   set they routed too many TN controls and lost the overhead argument.

Production-like recommendation if the larger comparison holds:

- Use the small model first only for predicted-positive rows.
- Do not route all cue-bearing negatives yet.
- Do not let the small model silently change the output CSV.
- Keep all classifier/verifier decisions in sidecars until council review
  accepts the tradeoff.

## Can This Be Run Now?

Yes for reproducing the completed mini ablation. Use the command in
`Commands For Reproducing The Mini Run`.

No for the larger full-sample comparison as a single turnkey command. That next
step still needs either:

- a new full-comparison runner, or
- an extension of `mini-4b-verifier-ablation` that accepts a full eval set and
  restricts evaluation to `qwen/qwen3-4b`.

If handing this file to Codex or another engineer, the requested task is:

```text
Implement the full-sample qwen/qwen3-4b verifier comparison described here,
write all artifacts under data/outputs/qwen3_4b_verifier_full_comparison/,
and do not change the official protect runtime unless the comparison report
shows a clear council-ready precision gain without unacceptable recall loss.
```

Minimum implementation requirements for the next runner:

- Reuse the prior `openai/gpt-oss-20b` full-run artifact as the main-model
  baseline.
- Evaluate `qwen/qwen3-4b` on cleaned text only.
- Produce direct small-model labels for measurement only.
- Produce positive-verifier decisions for rows where the main model predicted
  `true`.
- Compute direct-flip upper-bound metrics for positive verification.
- Optionally test revised 20B adjudication only on positive-verifier routed
  rows.
- Write a `comparison.md` with the report columns listed below.
- Keep generated artifacts ignored under `data/outputs/`.

## Council-Facing Framing

Safe summary:

```text
We added a small local verifier experiment around the main local LLM reviewer.
On a targeted set of known mistakes, Qwen 3-4B showed a useful signal for
identifying likely false positives at much lower cost than re-running the full
20B model. The result is not production-switched yet: the next step is a larger
full-sample comparison to measure whether the verifier improves precision
without damaging recall.
```

What is promising:

- A 4B local model parsed reliably and produced stable structured decisions.
- `qwen/qwen3-4b` was the best safer small candidate.
- The positive-verifier route targets the current main weakness: low precision.
- It can be kept sidecar-only, so it does not risk breaking exact CSV output.

What is not solved:

- Recall recovery remains unstable.
- Broad recall/combined routing routed too many TN controls in the mini set.
- The current 20B adjudication prompt underperformed after routing.
- The uncensored probe needs manual inspection before it can be considered.

## Next Full-Sample Run Plan

The next run should produce a comparison table, not alter the official output
path yet.

Suggested artifacts:

```text
data/outputs/qwen3_4b_verifier_full_comparison/
  models_seen.json
  sample_or_full_eval_set.csv
  qwen3_4b_direct_results.json
  qwen3_4b_positive_verifier_results.json
  adjudication_prompt_variant_results.json
  comparison.md
```

Suggested report columns:

- strategy
- rows evaluated
- routed rows
- parse success
- elapsed seconds
- seconds per row
- accuracy
- balanced accuracy
- precision
- recall
- F1
- TP/TN/FP/FN
- FP rescued
- TP damaged
- FN rescued
- TN routed

Decision thresholds for a council-ready pilot:

- Precision improves meaningfully over the current 20B sidecar baseline.
- Recall drop is small or explainable.
- Routed-row overhead is clearly below a full second 20B pass.
- Parse success is at least `95%`.
- Manual spot-checks do not show systematic over-labeling of quotes,
  counterspeech, political criticism, or non-identity profanity.

## Commands For Reproducing The Mini Run

Default staged run:

```bash
python -m contextsafe_hsd.cli mini-4b-verifier-ablation \
  --endpoint http://100.120.207.64:1234/v1/chat/completions \
  --timeout-seconds 180 \
  --batch-size 10 \
  --progress
```

Responsive-candidate run used after excluding Nemotron latency:

```bash
python -m contextsafe_hsd.cli mini-4b-verifier-ablation \
  --endpoint http://100.120.207.64:1234/v1/chat/completions \
  --timeout-seconds 180 \
  --batch-size 10 \
  --progress \
  --candidate qwen/qwen3-4b-2507 \
  --candidate qwen3.5-4b \
  --candidate qwen/qwen3-4b \
  --candidate shieldgemma-2-4b-it \
  --candidate google/gemma-3n-e4b \
  --candidate mistralai/ministral-3-3b
```

The generated `recommendation.md` is the concise result report. This planning
file is the handoff for the larger comparison.
