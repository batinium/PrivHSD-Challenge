# Overnight Progress Report

Date: 2026-06-11

Repository:

```text
/home/bati/projects/PrivHSD-Challenge
```

Current branch:

```text
main
```

Current pushed HEAD:

```text
f98522a Record Dynahate experiment summaries
```

## Executive Summary

The project has progressed from an initial fresh package into a runnable local
PrivHSD pipeline with deterministic text privatization, CSV batch processing,
audit JSON, local privacy/utility metrics, ablation reports, optional
scikit-learn utility and classifier workflows, synthetic PII stress tests,
Dynahate experiment outputs, packaging checks, and handoff documentation.

The core anonymizer remains local and dependency-light. It does not require LLM
APIs, external services, or scikit-learn for `privhsd anonymize`.

The most recent overnight work completed the requested priority sequence:

- A13: synthetic PII stress fixtures and tests.
- A16: optional local baseline classifier train/evaluate/predict pipeline.
- A04: safer target-group preserve/generalize policy.
- A06: official score-log template.
- Full local Dynahate anonymizer, metrics, classifier, prediction, and ablation
  experiments.
- Package wheel/install smoke test.
- Updated docs, task board, and handoff notes.

## Current Product Shape

The repository now implements this local workflow:

```text
CSV with text
  -> deterministic privacy span detection
  -> typed placeholder privatization
  -> row-preserving CSV with privatized_text
  -> machine-readable audit JSON
  -> local privacy/utility proxy metrics
  -> multi-mode ablation reports
  -> optional local classifier train/evaluate/predict reports
```

The primary package is:

```text
privhsd
```

Main modules:

- `privhsd.pipeline`: single-text privatization API.
- `privhsd.detectors`: deterministic regex/context span detectors.
- `privhsd.csv_pipeline`: CSV read/write, batch privatization, audit JSON, and
  CSV evaluation.
- `privhsd.metrics`: local privacy/utility proxy metrics and warning rollups.
- `privhsd.utility_benchmark`: optional scikit-learn utility-delta benchmark.
- `privhsd.ablation`: multi-mode anonymizer ablation runner.
- `privhsd.classifier`: optional scikit-learn baseline classifier
  train/evaluate/predict workflows.
- `privhsd.datasets`: Dynahate download/normalization helper.
- `privhsd.cli`: command-line interface.

Available CLI commands:

```bash
privhsd anonymize
privhsd evaluate
privhsd benchmark-utility
privhsd ablate
privhsd train-classifier
privhsd evaluate-classifier
privhsd predict-classifier
privhsd prepare-dynahate
```

## Implementation Milestones

### A01: Initial Pipeline

Completed. The repo has a working Python package and CLI for privacy-preserving
text privatization. It supports CSV input, row-preserving output, typed
placeholders, audit JSON, and local evaluation.

Key behavior:

- Preserves row count and row order.
- Preserves IDs, labels, and metadata columns.
- Adds `privatized_text` by default.
- Only overwrites the source text column if `--replace-text` is explicitly used.
- Uses typed placeholders rather than deletion.

### A05/A10: Local Utility Benchmark

Completed. `privhsd benchmark-utility` trains a lightweight TF-IDF + logistic
regression classifier on original-text training data and compares predictions on
original versus privatized text.

Reported fields include:

- original and privatized accuracy
- original and privatized macro-F1
- prediction agreement
- changed prediction count
- label recall deltas
- confidence drift

This benchmark is explicitly documented as a local proxy, not an official
PrivHSD evaluator.

### A09: Research and Roadmap

Completed. `docs/research_oss_tech.md` records academic and open-source
research notes, including:

- privacy-preserving NLP and text anonymization themes
- OSS shortlist
- local/offline technology recommendations
- integration roadmap
- evaluation and ablation plan
- risks and fallback options

The research converted into follow-up task-board items A10 through A16.

### A11: Ablation Runner

Completed. `privhsd ablate` compares deterministic privatization variants in a
single machine-readable report.

Implemented variants:

- `identity`: no privatization.
- `regex_only`: direct regex detectors only.
- `balanced`: default anonymizer.
- `privacy`: target-generalizing privacy mode.
- `balanced_with_targets`: balanced mode with target generalization enabled.

The ablation report includes aggregate proxy metrics, per-row metadata without
raw text, optional per-variant CSVs, and optional local utility benchmark
summaries when scikit-learn is available.

### A12: Richer Metrics and Warnings

Completed. Metrics now include local explainability fields beyond the original
privacy gain and utility retention proxies.

Added row-level and aggregate fields include:

- mask density
- placeholder density
- placeholder counts by type
- residual identifier count
- residual direct identifier count
- residual quasi-identifier count
- residual counts by entity type
- quasi-identifier flags
- target cue retention
- target category retention
- target term retention
- privacy warning counts
- over-masking warning counts
- rows with warnings

Warning examples:

- `residual_identifier_detected`
- `residual_direct_identifier_detected`
- `residual_quasi_identifier_detected`
- `residual_quasi_identifier_combination`
- `high_placeholder_density`
- `high_mask_density`
- `low_character_utility_retention`
- `target_cue_loss`

### A13: Synthetic PII Stress Fixtures and Tests

Completed in commit:

```text
1e29e3a Add synthetic PII stress fixtures
```

Added committed synthetic-only fixtures:

```text
tests/fixtures/synthetic_pii_stress.csv
tests/fixtures/synthetic_pii_residual_metrics.csv
```

Coverage includes:

- noisy handles
- emails
- phone numbers
- URLs
- IP addresses
- dates
- names
- locations
- schools and organizations
- IDs
- aliases
- direct-plus-quasi identifier combinations

Added tests prove:

- row order is preserved
- labels and metadata are preserved
- expected fields are masked
- residual metric warnings are reported where expected
- ablation behavior works on the synthetic fixture

Detector coverage was also improved with:

- `[ALIAS]` placeholder support
- explicit alias context patterns such as `alias`, `aka`, `known as`, and
  `goes by`
- stronger hyphenated/compound ID matching

### A16: Local Baseline Classifier Pipeline

Completed in commit:

```text
b9254c7 Add local classifier workflows
```

Added:

```text
privhsd/classifier.py
tests/test_classifier.py
```

New CLI commands:

```bash
privhsd train-classifier
privhsd evaluate-classifier
privhsd predict-classifier
```

The classifier is optional through:

```bash
python -m pip install '.[classifier]'
```

It uses:

- `TfidfVectorizer`
- `LogisticRegression`
- stratified train/dev split
- pickle model artifact

Classifier JSON metrics include:

- accuracy
- macro-F1
- per-label precision, recall, F1, and support
- confusion matrix
- confusion counts
- prediction counts
- label counts
- split configuration
- local-baseline warning

Prediction CSV output preserves:

- row count
- row order
- IDs
- labels if present
- metadata columns

It appends:

```text
predicted_label
predicted_confidence
```

Default outputs are under ignored `data/outputs/`.

### A04: Target-Group Preserve/Generalize Policy

Completed in commit:

```text
dff8fb2 Improve target group generalization policy
```

Policy behavior:

- `utility` and `balanced` preserve target-group terms by default for
  downstream hate-speech utility.
- `privacy` and `--generalize-targets` generalize known target-group terms into
  `[TARGET_GROUP:category]` placeholders.
- Broad gender terms are context-gated before generalization.

Broad gender terms affected:

```text
woman, women, man, men, girl, girls, boy, boys
```

These are preserved in neutral contexts and generalized only near hostile or
exclusionary cues such as:

```text
do not belong, should leave, deport, exclude, hate, worthless
```

This reduces over-masking risk while still supporting target generalization in
explicitly hostile contexts.

### A06: Official Score Log Template

Completed in commit:

```text
75eaf8d Add official score log template
```

Added:

```text
docs/score_log_template.md
```

The template records:

- submission metadata
- git commit and branch
- reproducible commands
- anonymizer mode and target policy
- local metrics
- optional classifier metrics
- official leaderboard result fields
- audit notes
- follow-up items

It explicitly instructs users not to paste raw challenge examples into the log.

## Documentation Updates

Updated documentation:

- `readme.md`
- `docs/README.md`
- `docs/pipeline_design.md`
- `docs/quickstart.md`
- `docs/packaging.md`
- `docs/score_log_template.md`
- `agents/task_board.md`
- `agents/current_handoff.md`

Key docs now describe:

- current module map
- CLI contract
- anonymizer modes
- target-group policy
- synthetic fixture coverage
- optional benchmark extra
- optional classifier extra
- classifier commands
- package/install commands
- official score-log process
- Dynahate experiment results

## Dataset State

The public Dynahate dataset is available locally under ignored paths:

```text
data/public_dev/dynahate_raw.csv
data/public_dev/dynahate.csv
```

Normalized dataset schema:

```text
id, text, label, source, split, target, type
```

Row count:

```text
41,144
```

Label counts:

| Label | Count |
| --- | ---: |
| hate | 22,175 |
| nothate | 18,969 |

Split counts:

| Split | Count |
| --- | ---: |
| train | 32,924 |
| dev | 4,100 |
| test | 4,120 |

Dataset contents are ignored by git and were not committed.

## Dynahate Experiment Results

Generated outputs are under ignored `data/outputs/`.

Main commands run:

```bash
.venv/bin/python -m privhsd.cli anonymize \
  --input data/public_dev/dynahate.csv \
  --output data/outputs/dynahate.balanced.privatized.csv \
  --text-col text \
  --id-col id \
  --audit data/outputs/dynahate.balanced.audit.json \
  --mode balanced

.venv/bin/python -m privhsd.cli evaluate \
  --input data/outputs/dynahate.balanced.privatized.csv \
  --text-col text \
  --privatized-col privatized_text \
  --output data/outputs/dynahate.balanced.metrics.json

.venv/bin/python -m privhsd.cli train-classifier \
  --input data/public_dev/dynahate.csv \
  --text-col text \
  --label-col label \
  --id-col id \
  --model data/outputs/dynahate.classifier.pkl \
  --output data/outputs/dynahate.classifier.train.json \
  --test-size 0.25 \
  --random-state 13

.venv/bin/python -m privhsd.cli evaluate-classifier \
  --input data/public_dev/dynahate.csv \
  --model data/outputs/dynahate.classifier.pkl \
  --text-col text \
  --label-col label \
  --id-col id \
  --output data/outputs/dynahate.classifier.evaluate_original.json

.venv/bin/python -m privhsd.cli evaluate-classifier \
  --input data/outputs/dynahate.balanced.privatized.csv \
  --model data/outputs/dynahate.classifier.pkl \
  --text-col privatized_text \
  --label-col label \
  --id-col id \
  --output data/outputs/dynahate.classifier.evaluate_privatized.json

.venv/bin/python -m privhsd.cli predict-classifier \
  --input data/outputs/dynahate.balanced.privatized.csv \
  --model data/outputs/dynahate.classifier.pkl \
  --text-col privatized_text \
  --id-col id \
  --label-col label \
  --output data/outputs/dynahate.classifier.predictions_on_privatized.csv

.venv/bin/python -m privhsd.cli ablate \
  --input data/public_dev/dynahate.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/dynahate.ablation.json \
  > data/outputs/dynahate.ablation.stdout.json
```

### Balanced Anonymizer Summary

| Metric | Value |
| --- | ---: |
| Row count | 41,144 |
| Privacy gain mean | 0.0489 |
| Placeholder count total | 2,315 |
| Residual identifier count | 3 |
| Residual direct identifier count | 3 |
| Residual quasi-identifier count | 0 |
| Target cue retention mean | 0.9994 |
| Character utility retention mean | 0.9953 |
| Rows with warnings | 125 |

Residual identifiers were all direct `USER` detections.

### Local Classifier Summary

Training:

| Metric | Value |
| --- | ---: |
| Train rows | 30,858 |
| Dev rows | 10,286 |
| Dev accuracy | 0.6101 |
| Dev macro-F1 | 0.6098 |

Full original versus privatized evaluation:

| Metric | Original Text | Privatized Text | Delta |
| --- | ---: | ---: | ---: |
| Accuracy | 0.7765 | 0.7757 | -0.0008 |
| Macro-F1 | 0.7764 | 0.7756 | -0.0008 |

Prediction CSV:

| Field | Value |
| --- | ---: |
| Row count | 41,144 |
| Predicted `hate` | 19,905 |
| Predicted `nothate` | 21,239 |

The prediction CSV preserved input rows and added `predicted_label` and
`predicted_confidence`.

### Ablation Summary

| Variant | Changed Rows | Privacy Gain Mean | Residual IDs | Target Cue Retention | Character Retention |
| --- | ---: | ---: | ---: | ---: | ---: |
| identity | 0 | 0.0000 | 2,315 | 1.0000 | 1.0000 |
| regex_only | 167 | 0.0038 | 2,123 | 1.0000 | 0.9996 |
| balanced | 2,015 | 0.0489 | 3 | 0.9994 | 0.9953 |
| privacy | 9,022 | 0.0489 | 3 | 0.9997 | 0.9565 |
| balanced_with_targets | 9,022 | 0.0489 | 3 | 0.9997 | 0.9565 |

Interpretation:

- `identity` is useful as a no-privacy baseline.
- `regex_only` leaves many quasi-identifiers and context identifiers.
- `balanced` gives strong target-cue retention with much lower residual
  identifier count.
- `privacy` and `balanced_with_targets` produce more changes because target
  mentions are generalized, with lower character retention.

## Verification and Packaging

Base test suite:

```bash
python -m pytest -q
```

Latest result:

```text
22 passed, 3 skipped
```

Optional classifier environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[classifier]'
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
```

Latest optional result:

```text
24 passed, 1 skipped
```

Wheel/install smoke:

```bash
python -m pip wheel . -w /tmp/privhsd-wheelhouse --no-deps --no-cache-dir
python -m venv /tmp/privhsd-install-test
/tmp/privhsd-install-test/bin/pip install --no-index --find-links /tmp/privhsd-wheelhouse privhsd
/tmp/privhsd-install-test/bin/privhsd --help
/tmp/privhsd-install-test/bin/privhsd train-classifier --help
/tmp/privhsd-install-test/bin/privhsd predict-classifier --help
```

Result:

```text
wheel built successfully; package installed successfully; CLI help worked
```

## Git History

Recent relevant commits:

| Commit | Summary |
| --- | --- |
| `f98522a` | Record Dynahate experiment summaries |
| `75eaf8d` | Add official score log template |
| `dff8fb2` | Improve target group generalization policy |
| `b9254c7` | Add local classifier workflows |
| `1e29e3a` | Add synthetic PII stress fixtures |
| `20f1e9a` | Add ablation runner and richer metrics |
| `bb0dd3f` | Add research notes and utility benchmark |
| `26ede61` | Harden pip package setup |
| `2176711` | Handle lowercase Dynahate CSV headers |
| `d6b1201` | Build initial PrivHSD privatization pipeline |

All recent milestone commits were pushed to `origin/main`.

## Current Task Board State

Done:

- A01: create fresh package, CLI, CSV pipeline, metrics, and tests.
- A04: improve target-group handling with a safe preserve/generalize policy.
- A05: add stronger local utility proxy.
- A06: add score log template.
- A07: add packaging/install instructions.
- A09: run research and convert findings into tasks.
- A10: add local scikit-learn utility benchmark.
- A11: add ablation runner.
- A12: expand deterministic metrics and warnings.
- A13: add synthetic PII stress fixtures and tests.
- A16: add local baseline classifier pipeline.

Still todo:

- A02: official-dataset schema adapter once starter kit arrives.
- A03: UI after anonymizer/classifier pipeline is stable.
- A08: final pitch outline and demo script.
- A14: optional Presidio/spaCy detector comparison.
- A15: optional local neural utility evaluators after model-license checks.

## Working Tree and Generated Files

Current untracked files before this report was written:

```text
Webinar.txt
prompt.md
```

`Webinar.txt` is intentionally untracked noisy transcript material.
`prompt.md` is the overnight-agent instruction file and was intentionally left
untracked.

Generated local outputs are ignored under:

```text
data/outputs/
```

Current generated output size at the last check:

```text
1.4G
```

Notable generated files include:

- `data/outputs/dynahate.balanced.privatized.csv`
- `data/outputs/dynahate.balanced.audit.json`
- `data/outputs/dynahate.balanced.metrics.json`
- `data/outputs/dynahate.classifier.pkl`
- `data/outputs/dynahate.classifier.train.json`
- `data/outputs/dynahate.classifier.evaluate_original.json`
- `data/outputs/dynahate.classifier.evaluate_privatized.json`
- `data/outputs/dynahate.classifier.predictions_on_privatized.csv`
- `data/outputs/dynahate.ablation.json`

These should not be committed unless a deliberately tiny synthetic output is
created for tests.

## Important Constraints Preserved

- Core anonymizer works without external LLM APIs.
- Core anonymizer works without required scikit-learn dependencies.
- Official/raw challenge examples were not committed or copied into docs.
- Public downloaded datasets remain ignored.
- Generated data outputs remain ignored.
- CSV row count, row order, IDs, labels, and metadata are preserved.
- `balanced` remains the recommended first submission mode.
- Typed placeholders are used instead of deletion.
- Classifier and benchmark outputs are documented as local baselines, not
  official evaluator scores.

## Recommended Next Steps

1. Add A08 final pitch outline and demo script.
2. Consider A14 optional Presidio/spaCy comparison behind an extra or separate
   command, without replacing the deterministic default.
3. Consider A15 optional local neural utility evaluators only after model
   license checks.
4. Add A02 official dataset schema adapter when starter kit or official schema
   arrives.
5. Build A03 UI last, after the CLI and artifact contracts remain stable.

For the hackathon submission path, the most practical next work is A08: turn
the current pipeline, Dynahate metrics, ablation comparison, and score-log
template into a concise pitch/demo narrative.
