# Privacy Tradeoff Ablation Plan

Status: next research direction after current event
Created: 2026-06-18

## Goal

Test whether classifier-guided evidence extraction can become a defensible
privacy/utility method, not just a high-scoring benchmark probe.

Current best direction:

- Use a fine-tuned DeHateBERT HSD classifier to identify rows that still need
  HSD evidence.
- Use token occlusion importance to find which tokens drive the HSD score.
- Preserve the already-protected baseline text for non-HSD rows in the balanced
  candidate.
- Keep only HSD-bearing evidence tokens or short windows around them.
- Run PII cleanup after extraction.

The key research question is whether this still works when the privacy cleanup
is made stricter and when selection is less tuned to one classifier.

## Current Reference Artifacts

Showcase folder:

`data/outputs/tutor_showcase_20260618/`

Main files:

- `00_locked_baseline_train_split_no_simplify_hf_recovered.protected.csv`
- `01_classifier_evidence_one_token.protected.csv`
- `02_classifier_evidence_relaxed_phrase.protected.csv`
- `99_high_risk_gold_label_template_probe.protected.csv`

The gold-label template probe is not a valid unlabeled-test method. Keep it only
as a benchmark failure-mode example.

## Baseline To Compare Against

Locked baseline:

`data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv`

Known private score:

`0.37` / `0.3721`

Current relaxed evidence candidate:

`data/outputs/evidence_tokens_classifier_relaxed_20260618/train_split.evidence_tokens_classifier_relaxed_on_baseline.protected.csv`

Local DeHateBERT diagnostics:

- baseline-positive rows preserved: `374 / 381`
- local accuracy vs `hs`: `0.905546`
- local F1: `0.852503`

## Method To Test Next

Name:

`raw-evidence extraction + final privacy cleanup`

Flow:

1. Start from raw text.
2. Use DeHateBERT to predict HSD rows.
3. Compute token occlusion importance on raw text.
4. Keep important HSD evidence anchors plus a short context window.
5. Preserve predicted non-HSD rows from the locked protected baseline for the
   balanced candidate, or collapse them only for the high-score reference.
6. Run deterministic PII cleanup on the extracted evidence phrase.
7. Re-score the final candidate with DeHateBERT and, if possible, submit one
   candidate to the private scorer.

This matches the tutor suggestion to work from raw data first, but it keeps a
clear final privacy step.

## Reproduction Commands

Compute token importance:

```bash
python scripts/hf_token_importance.py \
  --input data/train/train_split.csv \
  --output data/outputs/dpmlm_sweep_20260617/token_importance_train.csv \
  --text-col text \
  --id-col ID \
  --model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
  --threshold 0.850469 \
  --device cuda
```

Reproduce the aggressive one-token evidence variant:

```bash
python -m contextsafe_hsd.cli evidence-after-baseline \
  --source data/train/train_split.csv \
  --baseline data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/train_split.no_simplify_hf.recovered.protected.csv \
  --importance data/outputs/dpmlm_sweep_20260617/token_importance_train.csv \
  --output data/outputs/evidence_tokens_classifier_20260618/train_split.evidence_tokens_classifier_on_baseline.protected.csv \
  --text-col text \
  --id-col ID \
  --label-col hs \
  --classifier-text-source baseline \
  --hf-hsd-model-path data/outputs/dehatebert_official_kfold_20260617/final_model \
  --hf-hsd-threshold 0.850469 \
  --hf-hsd-device cuda \
  --max-anchors 1 \
  --context-radius 0
```

Reproduce the relaxed phrase evidence variant:

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
  --hf-hsd-device cuda \
  --max-anchors 3 \
  --context-radius 2 \
  --anchor-min-delta 0.03 \
  --anchor-relative-min 0.25
```

## Primary Ablations

### A0: Current Relaxed Phrase Reference

Purpose:

Reproduce the current relaxed phrase candidate exactly.

Settings:

- classifier text: locked baseline
- importance text: raw source
- `max_anchors = 3`
- `anchor_min_delta = 0.03`
- `anchor_relative_min = 0.25`
- `context_radius = 2`
- no extra post-extraction PII scrub beyond the extraction itself

Expected behavior:

Short phrases, usually 3-5 tokens for predicted-HSD rows.

### A1: Raw Evidence Plus Final PII Cleanup

Purpose:

Check whether the current candidate remains strong after a final PII scrub.

Settings:

- same as A0
- after evidence phrase extraction, run deterministic PII cleanup on the output
  phrase

Decision rule:

This is the first variant to submit if local HSD utility barely drops. It is the
cleanest story: raw signal is used to find evidence, then privacy cleanup is
applied to the minimized text.

### A2: Protected-Baseline Evidence Extraction

Purpose:

Test the strictest privacy claim.

Settings:

- classifier text: locked baseline
- importance text: locked baseline
- phrase extraction source: locked baseline
- final PII scrub still enabled

Decision rule:

If this scores close to A1, prefer A2. It avoids copying raw source tokens into
the output.

Risk:

Token importance may get weaker because the baseline already masks or rewrites
some signal.

### A3: Hybrid Raw Anchors, Protected Text Output

Purpose:

Use raw text only to locate HSD anchors, but copy the final phrase from the
protected baseline when token alignment allows it.

Settings:

- classifier text: locked baseline
- importance text: raw source
- anchor positions mapped back to baseline tokens when possible
- final output tokens copied from baseline/protected text, not raw text
- fallback to A1 only when alignment fails

Decision rule:

Good compromise if A2 loses too much utility.

### A4: Positive-Only Evidence, Baseline For Negatives

Purpose:

Test whether collapsing all predicted-negative rows to `Context removed.` is
helping too much or creating scorer artifacts.

Status:

Implemented through `evidence-after-baseline --negative-strategy baseline`.
Use this as the tutor-facing balanced candidate because it demonstrates context
preservation on non-HSD statements and should trade away some private score from
the `~0.83` collapsed-negative artifact toward the requested `~0.70` balance.

Settings:

- predicted-HSD rows use relaxed evidence phrases
- predicted-non-HSD rows keep locked baseline text
- recommended first pass: `--context-radius 3`, `--max-anchors 3`,
  `--anchor-min-delta 0.03`, `--anchor-relative-min 0.25`

Decision rule:

If score stays high, this is more conservative and easier to defend. If score
drops, the privacy gain is coming partly from deleting non-HSD context.

### A5: Neutral Template Variants

Purpose:

Check whether the exact negative-row phrase matters.

Variants:

- `Context removed.`
- `Non-identifying context removed.`
- empty-safe generic phrase such as `General discussion.`
- baseline text for negatives

Decision rule:

Pick the lowest-risk phrase that does not hurt utility.

## Word Survival Knob Sweep

Sweep one dimension at a time first.

### Context Radius

Values:

- `0`: evidence token only
- `1`: one token before and after
- `2`: current relaxed setting
- `3`: more readable phrase
- `5`: sentence-fragment style

Expected tradeoff:

Larger radius improves readability and may preserve HSD better, but leaks more
author/context information.

### Max Anchors

Values:

- `1`: only strongest evidence point
- `2`
- `3`: current setting
- `5`

Expected tradeoff:

More anchors preserve multi-part HSD claims better, but may reconstruct too much
of the source text.

### Anchor Threshold

Values:

- `delta > 0`: very permissive
- `delta >= 0.01`
- `delta >= 0.03`: current extra-anchor setting
- `delta >= 0.05`
- `delta >= 0.10`

Expected tradeoff:

Higher threshold keeps fewer but stronger evidence tokens.

### Relative Anchor Threshold

Values:

- `0.10`
- `0.25`: current setting
- `0.50`
- `0.75`

Expected tradeoff:

Higher values only keep anchors close to the strongest token.

## Utility Checks

For every candidate, record:

- output CSV path
- exact parameter settings
- SHA256 of source, baseline, and output
- local DeHateBERT accuracy, F1, precision, recall
- baseline-positive rows preserved
- final prediction counts
- changed text cell count
- word-count distribution
- examples of shortest, median, and longest HSD outputs
- validation result using `validate-submission`

Local utility is not enough. Submit only a small number of candidates to the
private scorer because overfitting to the local DeHateBERT classifier is a real
risk.

## Privacy Checks

For every candidate, record:

- percentage of rows collapsed to neutral text
- average surviving word count
- maximum surviving word count
- whether final PII scrub ran
- count of residual bracket placeholders such as `[PERSON]`, `[LOCATION]`
- count of raw URLs, handles, emails, phone-like strings
- random sample of HSD rows for manual privacy review
- random sample of non-HSD rows for manual privacy review

Manual review should ask:

- Does this preserve enough HSD evidence to classify?
- Does it leak author identity, location, workplace, contact info, or unique
  story details?
- Does it look like an extraction method rather than fake templating?

## Generalization Checks

The method can overfit in two ways:

1. DeHateBERT chooses evidence tokens that only DeHateBERT likes.
2. The private scorer may reward degenerate cue preservation more than real
   semantic preservation.

To reduce this risk:

- compare DeHateBERT against at least one different local HSD classifier if
  available
- test on a held-out split or a new CSV
- avoid tuning every parameter directly against the private score
- prefer simpler settings if scores are close

## Recommended Next Candidate Order

1. A1: raw evidence phrase plus final PII cleanup.
2. A2: compute/importance/extract from locked baseline text only.
3. A4: keep baseline text for predicted negatives instead of collapsing them.
4. Context radius sweep: `1`, `2`, `3`.
5. Max anchors sweep: `1`, `2`, `3`.

Stop early if local HSD F1 drops sharply or if manual privacy review finds clear
identity leakage.

## Explanation For Tutor

The method is not a manual slur-list filter. It is model-attribution-based
evidence minimization:

- DeHateBERT predicts which rows need HSD evidence.
- Token occlusion identifies which original tokens most affect the HSD score.
- The output keeps only those evidence tokens or small windows around them.
- Everything else is removed.
- A final PII cleanup stage can be applied after extraction.

The main ablation question is where privacy cleanup should happen:

- before attribution,
- after attribution,
- or both.

The likely best tradeoff is raw-text attribution followed by final PII cleanup,
because attribution sees the strongest HSD signal while the final output is
still minimized and scrubbed.
