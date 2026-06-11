# Continuation Prompt For Next Agent

You are working in `/home/bati/projects/PrivHSD-Challenge` on branch `main`.

The official challenge files are **not available yet**. Continue with optional
model-backed testing and experiment hardening on the local Dynahate data and
synthetic fixtures. The challenge goal is still to reduce authorship-identifying
signal while preserving hate-speech-detection utility. Do not treat the task as
simple PII redaction.

Start by reading:

1. `docs/roadmap.md`
2. `agents/task_board.md`
3. `agents/current_handoff.md`
4. `docs/pipeline_design.md`
5. `docs/methodology_justification.md`
6. `docs/dp_text_privacy_literature_notes.md`
7. `agents/coding_rules.md`
8. `docs/official_submission_checklist.md`
9. `docs/final_pitch_outline.md`

Initial commands:

```bash
git pull --ff-only
git status --short
python -m pytest -q
if [ -d .venv ]; then .venv/bin/python -m pytest -q; fi
```

Current status:

- Core priority implementation through A29 is complete.
- A26 HSD cue checks are complete.
- Metadata leakage checks are implemented with `check-metadata-leakage`; local
  Dynahate has 0 exact/normalized `id` leaks in original and protected text.
- A14 Presidio comparison harness is complete.
- A23 official submission checklist is complete.
- A30 bounded Hugging Face utility runs are complete on
  `data/outputs/dynahate.reranked.csv`.
- A31 bounded Presidio/spaCy comparison is complete on the first 100 local
  Dynahate rows and a sample-500 extension.
- A32 DPMLM backend investigation and protected-token candidate adapter are
  complete for this pass: `dpmlm` 1.1.2 is installed/importable after NLTK
  resources, `generate-dpmlm-candidates` runs `FacebookAI/roberta-base`, but
  bounded reranking selected 0 DPMLM candidates.
- A33 bounded local LLM candidate generation/reranking is complete against LM
  Studio at `http://100.120.207.64:1234`; current LLM candidates are low-yield
  and did not beat deterministic reranking.
- A36 weak token-action tagger training is complete on a sample-5,000 Dynahate
  run with macro-F1 0.8556 against weak local labels.
- A37 filtered Presidio augmentation is implemented on `anonymize`,
  `rerank-candidates`, and `create-submission` with `--presidio-augment`.
  Full Dynahate reranking selected `presidio_augmented` for 6,085 rows.
- A38 mentor-adjacent DP NLP literature mapping is complete in
  `docs/dp_text_privacy_literature_notes.md`; it supports selective cue
  protection, privacy-pressure allocation, reranking/post-processing, and
  empirical adversarial evaluation rather than direct DPMLM replacement.
- Latest pushed HEAD when this prompt was written: run `git rev-parse --short HEAD`
  to confirm.
- Current full tests should be `82 passed, 1 skipped`.
- Local Dynahate is expected at `data/public_dev/dynahate.csv`; it is ignored by
  git and has columns `id,text,label,source,split,target,type`.
- Generated outputs belong under ignored `data/outputs/`.
- Existing untracked files may include `Webinar.txt`; do not commit it unless
  explicitly requested.

Constraints:

- Core `privhsd anonymize` must remain local, deterministic, and dependency-light.
- Do not make Hugging Face, Presidio, spaCy, DPMLM, LM Studio, llama.cpp, or
  fine-tuning dependencies required for base anonymization.
- Do not commit downloaded datasets, model weights, Hugging Face caches,
  tokenizer caches, spaCy model files, DPMLM artifacts, local LLM outputs with
  raw text, `data/outputs/`, or official/raw examples.
- Preserve row count, row order, IDs, labels, and metadata in every CSV path.
- For official `id,author,text,HS`-style files, run metadata leakage checks on
  `id` and `author`, then run `evaluate-author-risk --author-col author` if
  author labels have repeated rows.
- Use the metric framing: high Utility_protected / Utility_original and low
  Privacy_protected / Privacy_original.
- Any model/LLM/DP output is evidence or a candidate for reranking, not a direct
  product replacement unless it clearly improves the measured privacy/HSD
  tradeoff and remains auditable.

## Next Priority: Remaining Model-Backed Experiment Work

### Optional A30 Extension: Hugging Face Utility Evaluator Runs

The local `.venv` has `torch` 2.12.0+cpu and `transformers` 5.11.0 installed.
Default HF probes passed sample 25 and sample 100 on reranked Dynahate with
negligible drift, 1.0 agreement, and no large utility-drop rows:

- `facebook/roberta-hate-speech-dynabench-r4-target`: sample 100, revision
  `391c99ab8b3f65beb77746a2cf6ddf1ddf9817e6`, CPU runtime 36.637s, mean delta
  -0.0005.
- `cardiffnlp/twitter-roberta-base-hate-latest`: sample 100, revision
  `cc56585908cbda6d04ba2e1234d911fd1578c9ab`, CPU runtime 41.2954s, mean
  delta -0.0016.
- `unitary/toxic-bert`: sample 25, revision
  `4d6c22e74ba2fdd26bc4f7238f50766b045a0d94`, CPU runtime 20.6408s, mean delta
  -0.0.

The two HateXplain classifier variants loaded but produced structured
`model_inference_failed` skips with `tuple index out of range`; keep
`check-hsd-cues` as the reliable cue-retention fallback.

Only scale to sample 500 or full runs if CPU runtime, model-card review, cache
size, and disk budget are acceptable. Reuse the existing command shape:

```bash
python -m privhsd.cli evaluate-hf-utility \
  --input data/outputs/dynahate.reranked.csv \
  --text-col text \
  --privatized-col privatized_text \
  --id-col id \
  --label-col label \
  --sample-size 500 \
  --output data/outputs/dynahate.reranked.hf_utility.sample500.json
```

### A31: Presidio/spaCy Comparison Runs

Sample 100 and sample 500 are complete in `.venv` using Presidio/spaCy.
Sample 100 results:

- PrivHSD spans: 1
- Presidio spans: 27
- overlap: 1
- Presidio-only: 26
- PrivHSD-only: 0
- false-positive-risk count on HSD cues/targets: 9
- runtime after setup: 0.4389s
- dependency cost: Presidio default initialization downloaded
  `en_core_web_lg` 3.8.0, a 400.7 MB spaCy model, even after
  `en_core_web_sm` was installed

Presidio remains a comparison baseline, not the product. Do not integrate it
into core anonymization unless measured privacy/HSD tradeoff gains justify the
false-positive and dependency costs.

Sample 500 results:

- PrivHSD spans: 8
- Presidio spans: 174
- overlap: 6
- Presidio-only: 168
- PrivHSD-only: 2
- false-positive-risk count on HSD cues/targets: 52
- runtime after setup: 1.4907s

Filtered Presidio augmentation is now implemented:

- flags: `--presidio-augment` on `anonymize`, `rerank-candidates`, and
  `create-submission`
- direct augmented full run accepted DATE 1,400, LOCATION 5,185, PERSON 3,834
  and rejected NRP 14,021 plus other risky/noisy spans
- full rerank chose `presidio_augmented` for 6,085 rows, `balanced` for 31,821,
  `style_scrubbed` for 3,219, and `privacy` for 19
- local utility benchmark: macro-F1 delta +0.0048, prediction agreement 0.9838
- cue checks: target-term retention 0.9974, utility-cue retention 1.0,
  58 rows with any conservative cue loss
- concrete behavior: masks `Amy`, `Steven`, `Mustafa`, `Britain`, `Caribbean`,
  and `the 1950s`; preserves target terms like `Muslims` and `Hindus`; rejects
  false positives like `ngl` and `sl33p`

### A33: Local LLM Candidate Generation

Bounded run is complete. The local LLM client now supports LM Studio-compatible
JSON schema response formatting, response-format fallback, wrapped JSON
extraction, and aggregate `status_counts` in reports.

Latest result:

- endpoint: `http://100.120.207.64:1234/v1/chat/completions`
- model: `openai/gpt-oss-20b`
- sample size: 10
- accepted candidates: 3
- rejected by checks: 7
- runtime: 18.2567s
- reranker selected LLM candidates: 0
- output metrics: matched deterministic `rerank-candidates`

Do not scale local LLM generation unless a model produces a much higher
accepted-and-selected rate on bounded samples. Do not use remote paid APIs
unless explicitly authorized.

Example:

```bash
python -m privhsd.cli generate-llm-candidates \
  --input data/public_dev/dynahate.csv \
  --output data/outputs/dynahate.llm_candidates.sample25.csv \
  --text-col text \
  --id-col id \
  --sample-size 25 \
  --endpoint http://127.0.0.1:1234/v1/chat/completions \
  --model local-model \
  --report data/outputs/dynahate.llm_candidates.sample25.report.json

python -m privhsd.cli rerank-candidates \
  --input data/outputs/dynahate.llm_candidates.sample25.csv \
  --output data/outputs/dynahate.llm_reranked.sample25.csv \
  --text-col text \
  --id-col id \
  --candidate-col llm_candidate \
  --audit data/outputs/dynahate.llm_reranked.sample25.audit.json
```

Use the example only for a new model comparison. Compare against deterministic
`rerank-candidates`. Reject raw LLM outputs that lose
target/action/negation/modality cues, drift semantically, or increase privacy
risk.

### A32: Real DPMLM Rewrite Spike

`dpmlm-spike` remains a backend/blocker harness. The implemented rewrite path is
`generate-dpmlm-candidates`, which uses the low-level DPMLM token API rather
than raw sentence rewriting.

Current evidence:

- `dpmlm` 1.1.2 is installed/importable after NLTK resources.
- Raw direct tiny-model DPMLM can change protected HSD cues, so raw sentence
  rewrite is unsafe.
- `generate-dpmlm-candidates` freezes target terms, utility/action cues,
  negation/modality terms, stopwords, capitalized tokens, repeated-letter
  tokens, placeholders, and punctuation.
- Safe default run:
  `data/outputs/dynahate.dpmlm_candidates.roberta.sample8.eps100.safe2.report.json`
  accepted 0/8 candidates in 3.9847s.
- Looser min-score-4 run:
  `data/outputs/dynahate.dpmlm_candidates.roberta.min4.sample12.eps100.final.report.json`
  accepted 11/12 candidates in 4.9143s.
- Reranking those looser candidates selected `balanced` for 10 rows,
  `style_scrubbed` for 2 rows, and 0 DPMLM candidates.

Do **not** integrate DPMLM into core anonymization unless it beats deterministic
or Presidio-reranked outputs on privacy/HSD tradeoff and auditability.

### A36: Weak Token-Action Tagger

`privhsd train-token-action-tagger` is implemented behind
`privhsd[token-actions]`. It trains a scikit-learn token classifier from weak
local detector/cue labels with actions `KEEP`, `MASK_IDENTIFIER`,
`GENERALIZE_CONTEXT`, `PROTECT_TARGET`, `PROTECT_HSD`, and `NORMALIZE_STYLE`.

Sample-5,000 Dynahate result:

- output: `data/outputs/dynahate.token_action_tagger.sample5000.json`
- model: `data/outputs/dynahate.token_action_tagger.sample5000.pkl`
- tokens: 67,415
- dev accuracy: 0.9888
- dev macro-F1: 0.8556
- `PROTECT_HSD` F1: 0.9890
- `PROTECT_TARGET` F1: 0.7810
- `GENERALIZE_CONTEXT` F1: 0.5823

Next use should be as a reranker/scorer feature or uncertainty detector, not as
a direct anonymizer.

### A34/A35: Transformer Fine-Tuning / Attention Experiments

Do not train a new attention mechanism as the first-line anonymizer. If you run
fine-tuning, treat it as optional evidence:

- HSD utility evaluator fine-tuning on original Dynahate train/dev split
- author-risk evaluator only if a dataset with author/user labels is available
- transformer scorer or reranker, not a required anonymizer
- small models and bounded epochs first
- save metrics, not model weights
- do not commit checkpoints or caches

Compare any fine-tuned/attention method against:

- local TF-IDF utility benchmark
- HF utility evaluator
- `evaluate-author-risk` when author labels exist
- `check-hsd-cues`
- residual privacy metrics
- runtime and dependency cost
- feasibility, auditability, rights framing, and limitations

## Already Useful Local Evidence

Full Dynahate aggregate evidence already recorded in docs:

- `balanced`: residual IDs 3, residual quasi IDs 0, target retention 0.9994,
  character retention 0.9953, local macro-F1 delta -0.0008.
- `balanced --style-scrub`: residual IDs 3, residual quasi IDs 0, target
  retention 0.9994, character retention 0.9434, local macro-F1 delta +0.0017.
- `rerank-candidates`: residual IDs 3, residual quasi IDs 0, target retention
  0.9997, character retention 0.9868, local macro-F1 delta +0.0019.
- exact-format balanced submission validation passed locally: 41,144 rows, same
  columns/order, no helper columns.
- reranked cue check: 59 rows with any conservative cue loss; utility-cue
  retention mean 1.0.
- HF utility sample 100 on reranked output: Dynabench/CardiffNLP agreement 1.0,
  negligible mean drift, and no large utility-drop rows.
- Presidio sample 100: 27 Presidio spans, 1 PrivHSD span, 1 overlap,
  9 false-positive-risk spans, and 400.7 MB `en_core_web_lg` dependency cost.
- Presidio sample 500: 174 Presidio spans, 8 PrivHSD spans, 6 overlaps,
  52 false-positive-risk spans.
- Weak token-action tagger sample 5,000: dev macro-F1 0.8556 against weak
  local labels.
- Filtered Presidio rerank full run: 6,085 Presidio candidates selected,
  macro-F1 delta +0.0048, target-term retention 0.9974, utility-cue retention
  1.0.
- DPMLM: protected-token `FacebookAI/roberta-base` candidate adapter works, but
  safe default accepted 0/8 and looser reranking selected 0 DPMLM candidates.
- Local LLM sample 10: `openai/gpt-oss-20b` accepted 3 candidates, rejected 7,
  but reranking selected no LLM candidates; deterministic reranked remains
  stronger.

## Required Updates Before Stopping

Before ending work:

```bash
python -m pytest -q
if [ -d .venv ]; then .venv/bin/python -m pytest -q; fi
git status --short
```

Update:

- `docs/roadmap.md` with aggregate results and blockers
- `agents/task_board.md` task statuses
- `agents/current_handoff.md` exact current state
- `docs/final_pitch_outline.md` if model results materially change the story
- `docs/score_log_template.md` only if submission commands change

Commit and push coherent milestones. Keep `data/outputs/` and all model caches
ignored. Do not stop just because one optional model path fails; record the skip
or blocker and continue to the next bounded experiment.
