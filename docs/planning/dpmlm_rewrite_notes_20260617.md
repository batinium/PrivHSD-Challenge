# DP-MLM Rewrite Notes, 2026-06-17

This note records the DP-MLM experiment and the current implementation state so
the work can be resumed later without reconstructing the chat history.

## What Changed

- Added an experimental `dpmlm_rewriter` model path to the auto pipeline.
- Added `contextsafe_hsd.models.dpmlm_rewrite_runtime.DpmlmRewriteRuntime`.
- Added CLI flags under `contextsafe-hsd protect`:
  - `--allow-model-download`
  - `--dpmlm-rewrite`
  - `--dpmlm-model-path`
  - `--dpmlm-device`
  - `--dpmlm-epsilon`
  - `--dpmlm-max-rewrite-tokens`
  - `--dpmlm-min-eligible-score`
  - `--dpmlm-top-k`
  - `--dpmlm-max-length`
  - `--dpmlm-random-seed`
  - `--dpmlm-min-row-style-risk`
- DP-MLM is lazy-loaded only when enabled and needed.
- DP-MLM candidates are inserted into the normal candidate ladder and scored
  before final selection. They are not applied after the final row has already
  been selected.
- DP-MLM candidates inherit the current best base candidate:
  `provider_fusion_augmented` if present, otherwise `style_scrubbed`, otherwise
  `balanced`.

## Candidate Selection

The final selector still uses deterministic scoring, not the HSD classifier, for
these upload CSV runs.

Candidate scoring considers:

- direct identifier reduction
- quasi identifier reduction
- accepted provider span count
- style-risk reduction
- target cue retention
- utility cue retention
- character retention
- length drift

Non-baseline candidates are hard-rejected for:

- target cue loss
- utility cue loss
- direct identifier increase
- new identifier signal
- excessive length drift

The winning candidate must beat the `balanced` baseline score. Otherwise the row
falls back to `balanced`.

## Provider Routing

Provider scan is not proof that deterministic masking found exact residual PII.
It is a cheap risk route that says an independent detector may be useful.

Rows are routed to Presidio/scrubadub when the deterministic profile finds:

- residual direct identifiers after baseline masking
- residual quasi identifiers after baseline masking
- person-name ambiguity in the original text
- quasi-location/context ambiguity in the original text

Provider spans become a separate candidate and still must win through the same
candidate scorer.

## DP-MLM Guardrails

The initial broad DP-MLM approach was too permissive because generic long words
could become eligible for masked-LM replacement. That created semantically bad
substitutions.

Current implementation is more conservative:

- DP-MLM only runs on rows whose deterministic style risk is at least
  `dpmlm_min_row_style_risk` (default `1`).
- Eligible tokens are restricted to explicit style markers and repeated-letter
  tokens.
- Replacements must pass cue retention, character retention, and length drift
  checks before they become candidates.
- Replacements must also be lexically similar to the original token after
  repeated-letter normalization. This prevents unrelated substitutions such as a
  repeated-letter interjection becoming an unrelated short word.

## Generated CSVs

Broad DP-MLM experiment:

`data/outputs/dpmlm_light_20260617/train_split.dpmlm_light.protected.csv`

- Valid exact-format CSV.
- 806 changed text cells.
- Privacy gain mean: `0.2111`.
- Character retention mean: `0.8376`.
- DP-MLM chosen on 23 rows.
- Generated before the final lexical-similarity guard.
- Use only as an ablation, not as the recommended submission.

Targeted DP-MLM experiment:

`data/outputs/dpmlm_targeted_20260617/train_split.dpmlm_targeted.protected.csv`

- Valid exact-format CSV.
- 805 changed text cells.
- Privacy gain mean: `0.2111`.
- Character retention mean: `0.8357`.
- DP-MLM chosen on 1 row.
- Generated before the final lexical-similarity guard.
- Also use only as an ablation unless regenerated with the current guarded code.

## Recommendation

For a serious leaderboard upload, prefer the deterministic style-tradeoff CSVs
until scorer results show DP-MLM helps:

- `data/outputs/style_tradeoff_no_simplify_20260617/train_split.no_simplify.protected.csv`
- `data/outputs/style_tradeoff_full_20260617/train_split.full_style.protected.csv`

DP-MLM is implemented and test-covered, but the generated DP-MLM CSVs should be
treated as experiments. If revisiting this, regenerate after the lexical
similarity guard and compare scorer results against the deterministic files.

## Verification

After the final guard patch:

- Full test suite passed: `204 passed`.
- The generated broad and targeted DP-MLM CSVs both validate structurally.
- The generated CSVs are not representative of the final guarded DP-MLM logic
  because they were produced before the last replacement-similarity patch.
