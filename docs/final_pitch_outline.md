# Final Pitch Outline

## Claim

PrivHSD should reduce authorship-identifying signal while preserving the
signals needed for hate-speech detection. The system is not a PII scrubber only:
it combines deterministic identifier masking, optional style normalization,
author-risk evaluation, local utility checks, candidate reranking, and
exact-format submission validation.

## Demo Flow

1. Show the CLI help and package tests.
2. Run exact-format creation:

```bash
python -m privhsd.cli create-submission \
  --input INPUT.csv \
  --output data/outputs/SUBMISSION.csv \
  --text-col text \
  --id-col id \
  --replace-text \
  --mode balanced \
  --manifest data/outputs/SUBMISSION.manifest.json
```

3. Show the manifest fields: command, git commit, input/output hashes, mode,
   row count, column preservation, validation, and aggregate metrics.
4. Show local privacy/utility evidence and reranking results without raw text.
5. Show optional evaluator behavior: author-risk skips when no author column is
   present, HF utility gives bounded model-backed drift evidence when installed,
   raw Presidio is dependency-heavy and false-positive-prone on HSD cues,
   filtered Presidio can safely feed reranking, and DPMLM is candidate-only
   because bounded real-model reranking did not select it.
6. For methodology questions, point to `docs/methodology_justification.md`:
   lexicons are justified by challenge labels, observed audit failures, and
   target-identity/stylometry literature rather than arbitrary word lists.

## Evidence Table

| Variant | Residual IDs | Residual quasi IDs | Target retention | Character retention | Local macro-F1 delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| `balanced` | 3 | 0 | 0.9994 | 0.9953 | -0.0008 |
| `balanced --style-scrub` | 3 | 0 | 0.9994 | 0.9434 | +0.0017 |
| `rerank-candidates` | 3 | 0 | 0.9997 | 0.9868 | +0.0019 |
| `rerank-candidates --presidio-augment` | 3 | 0 | 0.9997 | 0.9755 | +0.0048 |

Exact-format balanced submission validation passed on local Dynahate: 41,144
rows, same columns/order, no helper columns.

## Model-Backed Evidence

- HF utility on reranked sample 100: Dynabench and CardiffNLP probes both had
  1.0 agreement, negligible mean score drift, and no large utility-drop rows.
- Toxic-BERT sample 25 also had 1.0 agreement and no large utility-drop rows,
  but remains a toxicity proxy rather than an HSD-specific evaluator.
- HateXplain classifier variants produced structured inference skips in the
  current Transformers stack, so conservative local cue checks remain the
  reliable fallback.
- Presidio sample 100 found more spans than PrivHSD, but 9 of 27 Presidio spans
  were flagged as false-positive risk on HSD cues/targets and setup pulled a
  400.7 MB spaCy model.
- Filtered Presidio augmentation rejects `NRP`/protected-cue overlaps and feeds
  only likely names, locations, and durable dates into reranking. Full Dynahate
  reranking selected the Presidio candidate for 6,085 rows and improved local
  macro-F1 delta to +0.0048.
- Local LLM candidate generation works through LM Studio after JSON-schema
  compatibility hardening, but `openai/gpt-oss-20b` accepted only 3/10 sample
  candidates and reranking selected none of them over deterministic candidates.
- DPMLM now has a protected-token candidate generator with
  `FacebookAI/roberta-base`; the safe default accepted 0/8 first-sample rows,
  while a looser sample accepted 11/12 but reranking selected 0 DPMLM
  candidates.

## Rights Framing

- Privacy: protect people from author attribution and direct/quasi identifiers,
  not just obvious names or handles.
- Free expression: preserve target/action/negation/modality cues so protective
  moderation tools can still detect hate speech.
- Non-discrimination: preserve target-group evidence for HSD utility by default
  and generalize targets only in explicit privacy modes.
- Transparency: deterministic default, typed placeholders, audit JSON, manifests,
  hashes, and row-level warning categories.
- Human oversight: reports identify residual risks and utility drops by row ID
  without exposing raw text, so reviewers can inspect sensitive failures in a
  controlled environment.

## Limitations

- Local metrics are proxies, not official leaderboard scores.
- Style scrubbing reduces visible author style but cannot prove anonymity.
- Author-risk evaluation requires an author column and optional scikit-learn.
- Hugging Face utility probes require optional model dependencies, large local
  caches, and license review before full runs.
- Raw Presidio is not the product; filtered Presidio is optional and carries a
  substantial spaCy model dependency.
- Local LLM output is candidate-only; current bounded runs are too low-yield to
  justify scaling or direct submission.
- DPMLM is not integrated into the submission path because the audited
  protected-token adapter did not beat deterministic reranking in bounded local
  tests.
- Exact-format validation proves shape and metadata preservation; it does not
  certify privacy or fairness by itself.

## Recommended Submission Path

Use `balanced` exact-format output first unless official scores show a better
tradeoff. Keep `rerank-candidates --presidio-augment` as the strongest local
alternate, then submit only after exact-format validation and manifest review
pass.
