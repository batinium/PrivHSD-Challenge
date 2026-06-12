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
6. For methodology questions, point to `docs/project/methodology_justification.md`:
   lexicons are justified by challenge labels, observed audit failures, and
   target-identity/stylometry literature rather than arbitrary word lists.
7. For DPMLM and mentor-literature questions, point to
   `docs/research/dp_text_privacy_literature_notes.md`: the literature supports
   selective privacy pressure, protected utility cues, post-processing,
   reranking, and adversarial privacy evaluation rather than blindly replacing
   the pipeline with DPMLM.

## Evidence Table

| Variant | Residual IDs | Residual quasi IDs | Target retention | Character retention | Local macro-F1 delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| `balanced` | 3 | 0 | 0.9994 | 0.9953 | -0.0008 |
| `balanced --style-scrub` | 3 | 0 | 0.9994 | 0.9434 | +0.0017 |
| `rerank-candidates` | 3 | 0 | 0.9997 | 0.9868 | +0.0019 |
| `rerank-candidates --presidio-augment` | 3 | 0 | 0.9997 | 0.9755 | +0.0048 |

Exact-format balanced submission validation passed on local Dynahate: 41,144
rows, same columns/order, no helper columns.

Merged public bundle evidence: `balanced` exact-format validation passed on
159,668 rows with 26,941 changed text cells, identifiers 40,304 -> 5, direct
identifiers 33,032 -> 4, quasi identifiers 7,272 -> 1, target cue retention
0.9999, utility cue retention 0.9999, and character retention 0.9721.

Source-aware regression on the merged bundle adds hard-slice evidence beyond
global averages: action cue retention 0.9991, negation/modality retention
0.9989, 139 utility-loss rows, 203 context-loss rows, and 11 rationale-loss
rows. Rationale preservation was 47,729/47,740 spans, or 0.9998 retention,
with HateXplain token ranges and Toxic Spans character ranges parsed
separately.

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
  compatibility hardening. The current path can send source/label metadata to
  protect contextual cues and rejects candidates with target, utility, action,
  or negation/modality cue loss before reranking. A Qwen 3
  `qwen/qwen3-4b-2507` stratified 80-row run accepted 43 candidates and
  rejected 37 by checks; reranking selected Qwen for only 1/80 rows, while the
  final reranked sample had zero residual identifiers and zero conservative HSD
  cue-loss rows. This supports Qwen as an optional candidate source, not as a
  direct submission path.
- Local LM context-labeler benchmarking is implemented separately from rewrite
  generation. Initial localhost/Tailscale checks produced structured blockers;
  the link-local endpoint later timed out from WSL, and the working gateway was
  `http://172.21.96.1:1234`. Parser hardening improved format compliance, but
  the measured context-labeler results are not good enough to integrate:
  `mistralai/ministral-3-3b` parsed 100/100 rows with p50 latency 1.1017s, but
  deterministic-tag agreement was only 0.1525 and it produced 9 maskable cue
  violations. The faster `liquid/lfm2-1.2b` sample20 had agreement 0.0625 and
  3 maskable cue violations. Keep LM context labels exploratory only.
- DPMLM now has a protected-token candidate generator with
  `FacebookAI/roberta-base`; the safe default accepted 0/8 first-sample rows,
  while a looser sample accepted 11/12 but reranking selected 0 DPMLM
  candidates.

## Rights Framing

- Privacy: protect people from author attribution and direct/quasi identifiers,
  not just obvious names or handles.
- Free expression: the tool does not treat offense, insult, vulgarity,
  political disagreement, satire, counterspeech, or public-interest reporting as
  hate speech on its own.
- Non-discrimination: preserve target-group evidence for HSD utility by default
  and generalize targets only in explicit privacy modes, because under-detection
  against vulnerable or historically targeted groups can itself be a rights
  failure.
- Transparency: deterministic default, typed placeholders, audit JSON, manifests,
  hashes, and row-level warning categories.
- Proportionality: preserve target/action/negation/modality cues so any
  downstream review can distinguish hate, counterspeech, quotation, satire, and
  lawful criticism before imposing consequences.
- Human oversight: reports identify residual risks, missing context, high-risk
  protected-group targeting, and utility drops by row ID without exposing raw
  text, so reviewers can inspect sensitive failures in a controlled environment.

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
