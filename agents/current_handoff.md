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
4. `agents/task_board.md`
5. `agents/coding_rules.md`

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
privhsd evaluate-author-risk
privhsd hf-model-registry
privhsd evaluate-hf-utility
privhsd rerank-candidates
privhsd dpmlm-spike
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
The local `.venv` now has optional HF and Presidio/spaCy dependencies installed
for experiment runs; these remain outside core runtime requirements.

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
  runtime/blocker reporting, and no core dependency. Current local environment
  has no supported DPMLM backend installed.
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
- A20: blocked by no supported local DPMLM backend. The A27 spike harness
  records this blocker with epsilon/report structure.
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
- A31: bounded Presidio/spaCy detector comparison on the first 100 Dynahate
  rows; comparison passed but documented false-positive risk and dependency
  cost.

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
59 passed, 1 skipped
```

Latest optional classifier suite:

```text
.venv/bin/python -m pytest -q
59 passed, 1 skipped
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

Local LLM endpoint check:

- `curl --max-time 2 http://127.0.0.1:1234/v1/models` failed with connection
  refused, so A33 remains blocked until LM Studio or llama.cpp is running.

Generated outputs are under ignored `data/outputs/`.

## Next Work

Follow `docs/roadmap.md`.

Recommended next sequence while official files are unavailable:

1. Optional A30 extension: run sample 500 HF utility only if CPU runtime,
   model-card review, and cache size are acceptable.
2. A33: if LM Studio or llama.cpp endpoint is available, run
   `generate-llm-candidates`, then rerank with `rerank-candidates`.
3. A32: investigate a real DPMLM backend/adapter only if cue-token protection
   and determinism can be audited.
4. A34/A35: run transformer fine-tuning or attention experiments only as
   optional evaluators/rerankers/candidate scorers, then document whether they
   improve measured privacy/HSD tradeoff enough to justify complexity.
5. When official files arrive, return to `create-submission`,
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
