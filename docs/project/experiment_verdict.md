# Experiment Verdict

Date: 2026-06-12

Raw generated outputs, model weights, and row-level reports remain under
ignored `data/outputs/`. This file keeps only durable conclusions that affect
the submission or presentation strategy.

## Current Decision Table

| Path | Latest evidence | Utility result | Privacy/authorship result | Cost | Verdict |
| --- | --- | --- | --- | --- | --- |
| `balanced` exact-format | Merged public bundle: 159,668 rows, validation passed, 26,941 changed text cells. | Target and utility cue retention both 0.9999; character retention 0.9721. | Identifier detections 40,304 -> 5; direct IDs 33,032 -> 4; quasi IDs 7,272 -> 1. | Local deterministic CPU path. | First official submission candidate. |
| Source-aware regression | Merged bundle grouped by source/label/split/platform/type. | Action cue retention 0.9991; negation/modality retention 0.9989; rationale preservation 47,729/47,740 spans. | Exposes risky slices and row IDs without raw text. | CPU report. | Required before tuning or pitching. |
| `rerank-candidates` | Full Dynahate run selected `balanced` for 37,506 rows, `style_scrubbed` for 3,615, `privacy` for 23. | Local macro-F1 delta +0.0019; cue checks stable. | More style pressure on selected rows; residual IDs still 3, quasi IDs 0. | Local deterministic, slower than baseline. | Strong deterministic alternate. |
| `rerank-candidates --presidio-augment` | Full Dynahate run selected filtered Presidio candidate for 6,085 rows. | Local macro-F1 delta +0.0048; utility-cue retention 1.0; target retention 0.9974. | Adds names/locations/durable dates while rejecting `NRP` and target/action overlaps. | Optional Presidio/spaCy dependency. | Strongest local alternate after baseline. |
| RoBERTa token policy | 30k action-balanced weak labels, CUDA, one epoch. | Dev accuracy 0.9739; macro F1 0.9061. | Learns action policy, not private identities. `PROTECT_TARGET` F1 0.8665 on dev. | Transformer dependency; about 160s for this run. | Good advisory model and presentation evidence. |
| RoBERTa grouped K-fold | 5 grouped folds, action-balanced sampling. | Macro F1 mean 0.8977, std 0.0152. | Duplicate text overlap across folds: 0. | About 155s per fold on CUDA. | Stronger anti-overfit evidence. |
| HateBERT token policy | Same training recipe, hate-domain base model. | On external TweetEval, macro F1 0.8254. | Better `PROTECT_TARGET` F1 than RoBERTa on TweetEval: 0.7964. | Transformer dependency. | Useful ensemble member. |
| RoBERTa + HateBERT ensemble | External TweetEval hate/offensive test. | Accuracy 0.9879; macro F1 0.8837. | `PROTECT_TARGET` F1 0.8143; `PROTECT_HSD` F1 0.9808; `MASK_IDENTIFIER` F1 0.9638. | 78.6s evaluation. | Best current token-policy result. |
| Local LLM candidates | Qwen 3 candidate runs accepted some rewrites but reranking selected very few. | Strict validation prevented cue loss. | Candidate-only; not reliable enough for direct output. | Local LM Studio dependency and latency. | Keep as selective review/candidate path only. |
| DPMLM candidates | Protected-token adapter implemented; strict defaults accepted 0/8, looser run accepted 11/12 but reranker selected 0. | Did not beat deterministic alternatives. | Freezes targets/actions/negation/style cues. | Optional heavy dependencies. | Do not use for first submission. |

## Replicable Token-Policy Recipe

1. Normalize public training data into `data/public_dev/recommended_merged.csv`.
2. Inspect source, label, target, and missing-label distributions.
3. Train RoBERTa with `--sample-strategy action_source_balanced`,
   `--sample-size 30000`, `--max-length 192`, `--epochs 1`, `--batch-size 32`,
   and `--device cuda`.
4. Train grouped K-folds with `--fold-count 5` and `--fold-index 0..4`.
5. Train HateBERT with the same action-balanced recipe.
6. Normalize external unseen data into the shared schema.
7. Evaluate RoBERTa, HateBERT, and equal-weight ensemble on the external file.
8. Prefer equal weights unless a held-out external set proves a different
   weighting improves macro F1 and `PROTECT_TARGET` without hurting identifiers.

## Current Submission Rule

Submit `balanced` first. Use `rerank-candidates --presidio-augment` as the main
alternate if official privacy feedback is weak. Use the token-policy ensemble
as evidence and advisory reranker support until an audited candidate path
improves official scores.
