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
5. `agents/coding_rules.md`
6. `docs/official_submission_checklist.md`
7. `docs/final_pitch_outline.md`

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
- A14 Presidio comparison harness is complete.
- A23 official submission checklist is complete.
- Latest pushed HEAD when this prompt was written: run `git rev-parse --short HEAD`
  to confirm.
- Current full tests should be `59 passed, 1 skipped`.
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
- Use the metric framing: high Utility_protected / Utility_original and low
  Privacy_protected / Privacy_original.
- Any model/LLM/DP output is evidence or a candidate for reranking, not a direct
  product replacement unless it clearly improves the measured privacy/HSD
  tradeoff and remains auditable.

## Next Priority: Model-Backed Experiment Runs

### A30: Hugging Face Utility Evaluator Runs

Install optional dependencies in an isolated environment if practical:

```bash
python -m pip install '.[hf-utility]'
```

Then run bounded samples first:

```bash
python -m privhsd.cli hf-model-registry \
  --output data/outputs/hf_model_registry.json

python -m privhsd.cli evaluate-hf-utility \
  --input data/outputs/dynahate.reranked.csv \
  --text-col text \
  --privatized-col privatized_text \
  --id-col id \
  --label-col label \
  --sample-size 25 \
  --output data/outputs/dynahate.reranked.hf_utility.sample25.json
```

Models to try, one at a time first:

- `facebook/roberta-hate-speech-dynabench-r4-target`
- `cardiffnlp/twitter-roberta-base-hate-latest`
- `Hate-speech-CNERG/bert-base-uncased-hatexplain`
- `Hate-speech-CNERG/bert-base-uncased-hatexplain-rationale-two`
- `unitary/toxic-bert`

Record:

- model ID and revision if available
- device
- runtime
- sample size
- score drift
- agreement
- large utility-drop row IDs
- memory/runtime blockers

Scale to sample sizes 100, 500, then full only if runtime and memory are
reasonable. If model loading fails, keep the structured skip report.

### A31: Presidio/spaCy Comparison Runs

Install optional dependencies only for this comparison:

```bash
python -m pip install '.[presidio]'
python -m spacy download en_core_web_lg || python -m spacy download en_core_web_sm
```

Run bounded comparisons:

```bash
python -m privhsd.cli compare-presidio \
  --input data/public_dev/dynahate.csv \
  --text-col text \
  --id-col id \
  --sample-size 100 \
  --output data/outputs/dynahate.presidio_compare.sample100.json
```

Record:

- Presidio-only count
- PrivHSD-only count
- overlap count
- false-positive risk on target/action cues
- runtime
- dependency and model-size costs

Presidio remains a comparison baseline, not the product.

### A33: Local LLM Candidate Generation

Only run if a local LM Studio or llama.cpp OpenAI-compatible endpoint is
available. Do not use remote paid APIs unless explicitly authorized.

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

Compare against deterministic `rerank-candidates`. Reject raw LLM outputs that
lose target/action/negation/modality cues, drift semantically, or increase
privacy risk.

### A32: Real DPMLM Rewrite Spike

Current `dpmlm-spike` is a blocker/report harness because no local DPMLM backend
was installed. Investigate a maintained backend or reproducible adapter.

Only run actual rewrites if all are true:

- bounded sample first, such as 10 or 25 rows
- epsilon sweep includes 25 and 50
- HSD cue tokens, target groups, negation, and threat/action terms can be
  protected/frozen or reliably restored
- output is row-local
- determinism/reproducibility is documented
- runtime is recorded

Do **not** integrate DPMLM into core anonymization unless it beats deterministic
style/reranked outputs on privacy/HSD tradeoff and auditability.

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
