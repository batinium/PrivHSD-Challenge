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
   present, HF utility skips cleanly when dependencies are absent, and DPMLM is
   reported as a blocked spike rather than silently entering the core pipeline.

## Evidence Table

| Variant | Residual IDs | Residual quasi IDs | Target retention | Character retention | Local macro-F1 delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| `balanced` | 3 | 0 | 0.9994 | 0.9953 | -0.0008 |
| `balanced --style-scrub` | 3 | 0 | 0.9994 | 0.9434 | +0.0017 |
| `rerank-candidates` | 3 | 0 | 0.9997 | 0.9868 | +0.0019 |

Exact-format balanced submission validation passed on local Dynahate: 41,144
rows, same columns/order, no helper columns.

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
- Hugging Face utility probes require optional model dependencies and license
  review before full runs.
- DPMLM is not integrated because no supported local backend is available and no
  audited adapter has proven cue protection, determinism, and runtime quality.
- Exact-format validation proves shape and metadata preservation; it does not
  certify privacy or fairness by itself.

## Recommended Submission Path

Use `balanced` exact-format output first unless official scores show a better
tradeoff. Keep `rerank-candidates` as the strongest local tradeoff candidate for
additional author-style pressure, then submit only after exact-format validation
and manifest review pass.
