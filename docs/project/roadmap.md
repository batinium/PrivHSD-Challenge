# Roadmap

Date: 2026-06-12

## Mission

Reduce author-identifying signal in HSD datasets while preserving the cues that
make hate-speech detection and human review meaningful. This is broader than
PII redaction and narrower than moderation: the system transforms data and
produces evidence, not legal decisions.

## Current Baseline

`balanced` is still the first official candidate:

- deterministic and local;
- exact-format output with row, ID, label, and metadata preservation;
- target terms preserved by default;
- strong source-aware local evidence;
- low dependency footprint and easy explanation to judges.

On `data/public_dev/recommended_merged.csv`, the latest balanced run produced:

| Rows | Changed text cells | Identifier detections | Direct IDs | Quasi IDs | Target cue retention | Utility cue retention | Character retention |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 159,668 | 26,941 | 40,304 -> 5 | 33,032 -> 4 | 7,272 -> 1 | 0.9999 | 0.9999 | 0.9721 |

Use this as the regression benchmark until official data arrives.

## Current Model Evidence

The transformer path is now real, but it is advisory:

| Model path | Data | Metric | Result | Decision |
| --- | --- | --- | ---: | --- |
| RoBERTa token policy | 30k action-balanced weak labels | dev macro F1 | 0.9061 | Good advisory model. |
| RoBERTa grouped K-fold | 5 folds, grouped by text | macro F1 mean/std | 0.8977 / 0.0152 | Stable enough to trust as evidence. |
| RoBERTa on TweetEval external | unseen hate/offensive data | macro F1 | 0.8581 | Generalizes, weaker on `PROTECT_TARGET`. |
| HateBERT on TweetEval external | same | `PROTECT_TARGET` F1 | 0.7964 | Better target protection than RoBERTa alone. |
| Equal RoBERTa + HateBERT ensemble | same | macro F1 / `PROTECT_TARGET` F1 | 0.8837 / 0.8143 | Best current token-policy evidence. |

The ensemble aligns model probabilities back to original regex token spans
before averaging, so different subword tokenizers can vote on the same spans.

## Near-Term Priorities

1. Official baseline: profile official files, create `balanced`, validate exact
   format, run source regression, submit.
2. Official alternate: submit `rerank-candidates --presidio-augment` only if
   local reports and official feedback show privacy gain without cue loss.
3. Token-policy integration: use ensemble predictions as an advisory candidate
   or reranker feature, not as direct output.
4. External target-rich data: add unseen datasets only when their labels and
   schema are inspected. Avoid duplicates of existing sources and do not treat
   local temp downloads as unseen evidence until overlap checks pass.
5. Author-risk evaluation: run only when official data has repeated author,
   user, account, or handle values. Unique row IDs are not author labels.
6. Demo website: build a small local/on-prem web interface for NGO/civilian
   workflows after the CLI path is stable.

## What To Improve Next

### Reduce Overfitting

- Keep grouped K-fold splits by normalized text or duplicate group.
- Keep `action_source_balanced` sampling so rare actions and rare sources are
  present in training.
- Add token distribution reporting before training: action counts, source
  counts, target-term counts, label counts, and duplicate overlap.
- Prefer external target-rich evaluation before increasing model size.
- Tune class weights and thresholds per action, especially `PROTECT_TARGET`,
  `GENERALIZE_CONTEXT`, and `REVIEW`.

### Improve `PROTECT_TARGET`

- Normalize datasets with explicit target fields into the shared schema.
- Treat target metadata and target lexicons as weak supervision for
  `PROTECT_TARGET`.
- Evaluate external data by target class, not only global macro F1.
- Keep target terms protected by default in the deterministic layer; neural
  models should learn that policy, not override it.

### Synthetic Stress Generation

- Use `scripts/generate_lm_studio_stress_cases.py` to batch-generate local
  synthetic stress rows through LM Studio.
- Example smoke command:

```bash
python scripts/generate_lm_studio_stress_cases.py \
  --endpoint http://172.21.96.1:1234/v1/chat/completions \
  --model gemma-4-e4b-uncensored-hauhaucs-aggressive \
  --batches 1 \
  --cases-per-batch 2 \
  --use-presidio
```

- Treat generated rows as coverage probes first, not trusted training data.
- Track missing expected privacy spans and missing expected target spans from
  the script report.
- Promote generated examples into training only after dedupe, label validation,
  source balancing, and token-action distribution checks.
- Avoid committing generated raw examples; keep JSONL and reports under ignored
  `data/outputs/`.
- Use `docs/project/evaluation_checklist.md` as the durable test matrix for
  manual examples, generated stress cases, and demo rehearsals.

### Improve Winning Odds

- Show that the system preserves civil-liberties context: counterspeech,
  quotation, public-interest reporting, and vulnerable-group targeting.
- Bring an interactive demo, not only a CSV pipeline.
- Use the model story carefully: "we fine-tuned transformers to learn token
  protection policy, then kept deterministic audit controls around them."
- Keep raw text private in the demo; show before/after only on synthetic or
  user-entered examples.

## Demo Website Direction

Build a simple "Privacy Review Workbench" that can run locally or on an NGO's
server:

- paste text or upload a CSV;
- see privatized text with typed placeholders;
- inspect why each span was changed or protected;
- view target/action/negation cue retention;
- see a risk gauge for identifiers, style, and HSD cue drift;
- export an anonymized CSV plus manifest and audit report;
- queue uncertain rows for human review without exposing raw text in logs.

The pitch value is clear: civilians, NGOs, journalists, and researchers can
share harmful-content datasets more safely without erasing evidence needed to
understand hate.

## Do Not Spend Time On

- Broad target generalization as the default submission.
- Raw Presidio replacement.
- Direct LLM rewriting without validation and reranking.
- Treating unique IDs as author labels.
- Duplicated external datasets that are already in the merged training bundle.
- More markdown run diaries. Record experiments in ignored JSON artifacts and
  keep only durable conclusions in `experiment_verdict.md`.
