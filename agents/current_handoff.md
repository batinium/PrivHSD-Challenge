# Current Handoff

Date: 2026-06-11

## Repo State

Repository:

```text
/home/bati/projects/PrivHSD-Challenge
```

Branch:

```text
main
```

Untracked files:

```text
Webinar.txt
```

`Webinar.txt` is untracked and 45,675 bytes; do not commit it unless explicitly
requested. The webinar slide screenshots are outside the repo at:

```text
/mnt/c/Users/noutr/Downloads/Ss
```

Do not commit downloaded datasets, official challenge data, or generated
`data/outputs/` artifacts.

`prompt.md` contains the self-contained continuation prompt for the next model
run/testing phase and is intended to be tracked.

## Read First

1. `docs/challenge_requirements.md`
2. `docs/roadmap.md`
3. `docs/pipeline_design.md`
4. `docs/methodology_justification.md`
5. `agents/task_board.md`
6. `agents/coding_rules.md`

Use `overnight_report.md` for the detailed overnight history and experiment
results. Keep this handoff short.

## Current System

The project is a local text-to-text privatization pipeline for PrivHSD:

```text
CSV text
  -> deterministic privacy detection
  -> typed placeholder privatization
  -> row-preserving CSV with privatized_text
  -> audit JSON and local metrics
  -> optional ablation/classifier reports
```

CLI commands:

```bash
privhsd anonymize
privhsd evaluate
privhsd benchmark-utility
privhsd ablate
privhsd train-classifier
privhsd evaluate-classifier
privhsd predict-classifier
privhsd train-token-action-tagger
privhsd evaluate-author-risk
privhsd hf-model-registry
privhsd evaluate-hf-utility
privhsd rerank-candidates
privhsd dpmlm-spike
privhsd generate-dpmlm-candidates
privhsd create-submission
privhsd validate-submission
privhsd compare-presidio
privhsd generate-llm-candidates
privhsd check-hsd-cues
privhsd prepare-dynahate
```

Core `privhsd anonymize` remains dependency-light and does not require
scikit-learn, external LLM APIs, Presidio, or Hugging Face models.
`--style-scrub` is available as an optional deterministic author-style
normalization pass after privacy masking.
Hugging Face utility probes are optional through `privhsd[hf-utility]`.
The local `.venv` now has optional HF, Presidio/spaCy, DPMLM, and
scikit-learn experiment dependencies installed for bounded runs; these remain
outside core runtime requirements.

## Webinar Correction

The challenge is broader than PII masking.

Goal:

```text
minimize author-identifying signal
maximize hate-speech detection signal
```

Important slide takeaways:

- Authorship identification is itself a classification task and should be made
  harder.
- Presidio was shown as an insufficient baseline, not a solution.
- DPMLM-style rewriting can work, but it is complex and parameter-sensitive.
- Generic LLM prompting scored poorly; LLM use must be specialized,
  constrained, and evaluated.
- Winning the website leaderboard does not automatically win the hackathon.
  Judges also evaluate framing, rights impact, feasibility, transparency,
  limitations, and presentation.

## Completed Milestones

- A01: package, CLI, CSV pipeline, metrics, and tests.
- A04: safer target-group preserve/generalize policy.
- A05/A10: optional scikit-learn utility benchmark.
- A06: official score-log template.
- A07: packaging/install instructions.
- A09: research notes and implementation tasks.
- A11: ablation runner.
- A12: richer metrics and warnings.
- A13: synthetic PII stress fixtures and tests.
- A16: optional local classifier train/evaluate/predict workflow.
- A17: optional local author-risk evaluator with structured no-author skip JSON.
- A18: deterministic style scrubber for casing, spacing, repeated letters,
  punctuation bursts, emoji/symbol bursts, signatures, self-tags, and idiolect
  markers while preserving target/action cues.
- A24/A25: optional Hugging Face model registry and utility evaluator with
  small-sample defaults, score-drift/agreement metrics, large-drop row IDs, and
  structured skips for missing dependencies or failed model loading.
- A19: row-local candidate reranker for balanced, style-scrubbed, privacy,
  target-generalized, and optional rewrite-column candidates, with audit-only
  per-candidate scores and optional author-risk confidence when available.
- A27: bounded DPMLM spike harness with epsilon sweep, protected-cue manifest,
  runtime/blocker reporting, backend import details, and no core dependency.
- A32/A20: protected-token DPMLM candidate generator with
  `FacebookAI/roberta-base`, frozen HSD/privacy/style-risk tokens, per-row
  seeding, validation, and reranking-only output. Current bounded reranking
  selected 0 DPMLM candidates.
- A28: exact-format submission creator/validator with in-place text-column
  privatization via `--replace-text`, helper-column rejection, row/order/ID
  validation, metadata preservation checks, file hashes, git commit, command,
  mode, and metrics in the manifest.
- A08/A22: final pitch/demo outline and human-rights judging narrative in
  `docs/final_pitch_outline.md`.
- A14: optional Presidio comparison baseline with overlap, detector-only counts,
  false-positive risk on HSD cues, runtime, and structured dependency skips.
- A15: optional neural utility evaluator path via the Hugging Face registry and
  `evaluate-hf-utility` command.
- A20: DPMLM spike completed; the adapter works but current real-model
  candidates do not beat deterministic reranking.
- A21/A29: optional local LLM candidate generator for LM Studio/llama.cpp
  OpenAI-compatible endpoints with JSON schema prompting, cue/length checks, and
  reranking-only output. Current local sample run skipped because no endpoint is
  running.
- A26: conservative HSD cue retention checker for target terms, utility cues,
  action terms, and negation/modality terms by row ID.
- A23: official submission checklist in
  `docs/official_submission_checklist.md`.
- A30: bounded Hugging Face utility evaluator runs on
  `data/outputs/dynahate.reranked.csv`; default probes passed sample 25 and
  sample 100, Toxic-BERT passed sample 25, and HateXplain variants produced
  structured inference skips.
- A31: bounded Presidio/spaCy detector comparison on the first 100 and 500
  Dynahate rows; comparison passed but documented false-positive risk and
  dependency cost.
- A32: `dpmlm` 1.1.2 installed/imported after NLTK resources; raw direct
  rewriting is unsafe, protected-token candidate generation is implemented,
  and `FacebookAI/roberta-base` bounded reranking selected no DPMLM candidates.
- A33: bounded local LLM candidate generation and reranking against LM Studio
  at `http://100.120.207.64:1234`; implementation hardened for JSON-schema
  response format/fallback and wrapped JSON parsing. Accepted LLM candidates
  did not beat deterministic reranking.
- A36: optional weak token-action tagger training experiment with
  `train-token-action-tagger`, scikit-learn extra, tests, and a sample-5,000
  Dynahate report.
- A37: filtered Presidio augmentation on `anonymize`, `rerank-candidates`, and
  `create-submission` via `--presidio-augment`; full Dynahate reranking selected
  `presidio_augmented` for 6,085 rows.

Recent commits:

```text
9d69910 Add continuation prompt for model experiments
f6198f6 Add official submission checklist
9625803 Add HSD cue retention checks
9fb1d41 Add local LLM candidate harness
8412b81 Add Presidio comparison baseline
```

## Verification

Latest base suite:

```text
python -m pytest -q
79 passed, 1 skipped
```

Latest optional classifier suite:

```text
.venv/bin/python -m pytest -q
79 passed, 1 skipped
```

Package smoke passed: built a wheel, installed it in `/tmp/privhsd-install-test`,
and verified root plus classifier CLI help.

## Dynahate Summary

Public Dynahate exists locally at `data/public_dev/dynahate.csv` and is ignored
by git.

Dataset:

- rows: 41,144
- labels: 22,175 `hate`, 18,969 `nothate`
- splits: 32,924 train, 4,100 dev, 4,120 test

Latest aggregate experiment results:

| Variant | Residual IDs | Residual quasi IDs | Target retention | Character retention | Local macro-F1 delta | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `balanced` | 3 | 0 | 0.9994 | 0.9953 | -0.0008 | Prior full Dynahate run. |
| `balanced --style-scrub` | 3 | 0 | 0.9994 | 0.9434 | +0.0017 | Stronger style normalization; 77 changed local predictions. |
| `rerank-candidates` | 3 | 0 | 0.9997 | 0.9868 | +0.0019 | Chose `balanced` for 37,506 rows, `style_scrubbed` for 3,615, `privacy` for 23. |
| `rerank-candidates --presidio-augment` | 3 | 0 | 0.9997 | 0.9755 | +0.0048 | Chose `presidio_augmented` for 6,085 rows, `balanced` for 31,821, `style_scrubbed` for 3,219, `privacy` for 19. |
| `create-submission --replace-text --mode balanced` | 3 | 0 | 0.9994 | 0.9953 | n/a | Exact-format validation passed: 41,144 rows, same columns/order, no helper columns. |

Reranked cue check:

- rows with any conservative cue loss: 59
- target-term retention mean: 0.9971
- utility-cue retention mean: 1.0
- action-term retention mean: 0.9995
- negation/modality retention mean: 1.0001

HF utility on `data/outputs/dynahate.reranked.csv`:

- `.venv` environment: `torch` 2.12.0+cpu, `transformers` 5.11.0, CUDA not
  available.
- sample 100 default probes:
  - `facebook/roberta-hate-speech-dynabench-r4-target`: revision
    `391c99ab8b3f65beb77746a2cf6ddf1ddf9817e6`, CPU runtime 36.637s,
    mean delta -0.0005, mean absolute drift 0.0005, agreement 1.0, no large
    utility-drop rows.
  - `cardiffnlp/twitter-roberta-base-hate-latest`: revision
    `cc56585908cbda6d04ba2e1234d911fd1578c9ab`, CPU runtime 41.2954s,
    mean delta -0.0016, mean absolute drift 0.0019, agreement 1.0, no large
    utility-drop rows.
- sample 25 toxicity proxy:
  - `unitary/toxic-bert`: revision
    `4d6c22e74ba2fdd26bc4f7238f50766b045a0d94`, CPU runtime 20.6408s,
    mean delta -0.0, agreement 1.0, no large utility-drop rows.
- HateXplain classifier variants loaded but skipped during inference with
  `tuple index out of range`; rely on `check-hsd-cues` as the local cue
  fallback.

Presidio comparison on `data/public_dev/dynahate.csv` sample 100:

- status: ok
- runtime after setup: 0.4389s
- aggregate: PrivHSD spans 1, Presidio spans 27, overlap 1, Presidio-only 26,
  PrivHSD-only 0, false-positive-risk count 9
- dependency note: Presidio default initialization downloaded
  `en_core_web_lg` 3.8.0, a 400.7 MB spaCy model, after `en_core_web_sm` was
  installed.

Presidio comparison on `data/public_dev/dynahate.csv` sample 500:

- status: ok
- runtime after setup: 1.4907s
- aggregate: PrivHSD spans 8, Presidio spans 174, overlap 6,
  Presidio-only 168, PrivHSD-only 2, false-positive-risk count 52
- verdict: useful detector baseline, too much HSD-cue/target overmasking risk
  for core use.

Filtered Presidio augmentation full Dynahate run:

- commands:
  - `anonymize --presidio-augment`
  - `rerank-candidates --presidio-augment`
- outputs:
  - `data/outputs/dynahate.presidio_augmented.full.csv`
  - `data/outputs/dynahate.presidio_augmented.full.audit.json`
  - `data/outputs/dynahate.reranked_presidio.full.csv`
  - `data/outputs/dynahate.reranked_presidio.full.audit.json`
  - `data/outputs/dynahate.reranked_presidio.full.utility_benchmark.json`
  - `data/outputs/dynahate.reranked_presidio.full.cue_checks.json`
- accepted filtered Presidio spans in direct augmented run: DATE 1,400,
  LOCATION 5,185, PERSON 3,834
- rejected raw Presidio spans: NRP preserved 14,021, transient date 2,315,
  location shape 935, person shape 611, protected cue overlap 148,
  unsupported type 705
- rerank chosen counts: balanced 31,821, presidio_augmented 6,085,
  style_scrubbed 3,219, privacy 19
- local utility benchmark: macro-F1 delta +0.0048, accuracy delta +0.0046,
  prediction agreement 0.9838
- cue check: rows with loss 58, target-term retention 0.9974,
  utility-cue retention 1.0, action-term retention 0.9995,
  negation/modality retention 1.0
- concrete behavior: masks `Amy`, `Steven`, `Mustafa`, `Britain`,
  `Caribbean`, and `the 1950s`; preserves target terms like `Muslims` and
  `Hindus`; rejects false positives like `ngl` and `sl33p`.
- verdict: strongest experimental alternate after `balanced`; still optional
  because Presidio/spaCy is a heavy dependency.

Weak token-action training on `data/public_dev/dynahate.csv` sample 5,000:

- command: `train-token-action-tagger`
- outputs:
  `data/outputs/dynahate.token_action_tagger.sample5000.json` and `.pkl`
- tokens: 67,415
- dev accuracy: 0.9888
- dev macro-F1: 0.8556
- per-action highlights: `PROTECT_HSD` F1 0.9890, `PROTECT_TARGET` F1 0.7810,
  `MASK_IDENTIFIER` F1 0.8000 on two dev examples,
  `GENERALIZE_CONTEXT` F1 0.5823
- verdict: useful as a future detector/reranker feature, not supervised privacy
  truth.

DPMLM bounded evidence:

- installed `dpmlm` 1.1.2 in `.venv`; downloaded NLTK resources to
  `/home/bati/nltk_data`
- `dpmlm-spike` remains the backend/blocker report; raw direct tiny-model probe
  changed protected cues, so raw DPMLM sentence rewrite is unsafe
- new command: `generate-dpmlm-candidates`
- adapter policy: low-level token API, `FacebookAI/roberta-base` by default,
  per-row seeding, frozen target/utility/action/negation cues, stopwords,
  capitalized tokens, repeated-letter tokens, placeholders, and punctuation
- safe-default run:
  `data/outputs/dynahate.dpmlm_candidates.roberta.sample8.eps100.safe2.report.json`
  accepted 0/8 candidates in 3.9847s because no safe rewrite targets remained
- looser min-score-4 run:
  `data/outputs/dynahate.dpmlm_candidates.roberta.min4.sample12.eps100.final.report.json`
  accepted 11/12 candidates in 4.9143s and rejected one no-token-change row
- final rerank:
  `data/outputs/dynahate.dpmlm_reranked.roberta.min4.sample12.eps100.final.audit.json`
  selected `balanced` for 10 rows, `style_scrubbed` for 2 rows, and 0 DPMLM
  candidates
- verdict: adapter works as an optional candidate source, but current evidence
  says not to submit or scale DPMLM.

Local LLM bounded evidence:

- Endpoint: `http://100.120.207.64:1234/v1/chat/completions`
- Available model smoke tests:
  - `openai/gpt-oss-20b`: real sample path works.
  - `mistralai/ministral-3-3b`: synthetic JSON passed, but real sample 3
    accepted 0/3 under conservative checks.
  - `qwen/qwen3-4b-2507`: synthetic JSON passed, but real sample 3 accepted
    0/3 because of length drift or target cue loss.
  - `google/gemma-4-e4b`: synthetic JSON passed, but real sample 3 accepted
    0/3 because of length drift or target cue loss.
  - `zai-org/glm-4.7-flash`: synthetic structured request returned empty
    content.
- `openai/gpt-oss-20b` sample 10 with `--max-length-drift 0.75`: accepted 3,
  rejected 7, runtime 18.2567s.
- Full preserved-shape rerank with `--candidate-col llm_candidate` selected no
  LLM candidates. Chosen counts stayed `balanced` 37,506, `style_scrubbed`
  3,615, `privacy` 23.
- LLM-reranked metrics match deterministic reranked metrics: residual IDs 3,
  residual quasi IDs 0, target-cue retention mean 0.9997, character retention
  0.9868, local macro-F1 delta +0.0019.
- Verdict: local LLM harness is functional, but current model outputs are
  low-yield and should not be scaled or submitted directly.

Generated outputs are under ignored `data/outputs/`.

## Next Work

Follow `docs/roadmap.md`.

Recommended next sequence while official files are unavailable:

1. Review `docs/experiment_verdict.md` for the compact decision table.
2. Use `rerank-candidates --presidio-augment` as the strongest alternate after
   the first `balanced` official submission.
3. A36 follow-up: use the weak token-action tagger as a reranker/scorer feature
   or uncertainty detector, not as a direct anonymizer.
4. Optional A30 extension: run sample 500 HF utility only if CPU runtime,
   model-card review, and cache size are acceptable.
5. DPMLM follow-up: keep it candidate-only; scale only if a better policy or
   official metrics show protected-token DPMLM beating deterministic/reranked
   outputs.
6. A34/A35: run transformer fine-tuning or attention experiments only as
   optional evaluators/rerankers/candidate scorers, then document whether they
   improve measured privacy/HSD tradeoff enough to justify complexity.
7. When official files arrive, return to `create-submission`,
   `validate-submission`, upload, and leaderboard-driven iteration.

Do not start by training a new attention model. Use pretrained models to
measure HSD utility and generate/rerank candidates, then keep anything that
improves the measured privacy/HSD tradeoff.

## Constraints

- Preserve row count, row order, IDs, labels, and metadata.
- Add `privatized_text` by default.
- Do not expose raw official examples in docs, tests, screenshots, or commits.
- Use `balanced` as the first submission mode unless official scores prove
  otherwise.
- Treat external OSS/LLM/DP tools as optional support, not the core default.
