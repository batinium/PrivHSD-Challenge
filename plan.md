# Glimo HSD Packaging and Hugging Face Release Plan

This plan is written as a handoff for a fresh Codex session. The repo was saved before this plan was created. Latest checkpoint at the time of writing:

```text
f8171fa Checkpoint reviewer tutorial flow
```

The working tree was clean before `plan.md` was added.

## Goal

Turn the current Glimo / PrivHSD backend pipeline into a reusable Python package and publish the custom DeHateBERT checkpoint on Hugging Face.

The intended external user experience:

```python
from glimo_hsd import PipelineConfig, process_csv

result = process_csv(
    "input.csv",
    config=PipelineConfig(
        text_col="text",
        label_col="hs",
        model_id="batinium/glimo-dehatebert-privhsd",
        restatement_backend="qwen",
        final_scrub=True,
    ),
)

print(result.restated_csv)
print(result.audit_csv)
```

CLI equivalent:

```bash
glimo-hsd process input.csv \
  --text-col text \
  --label-col hs \
  --out outputs/run_001 \
  --model-id batinium/glimo-dehatebert-privhsd \
  --final-scrub
```

## Non-Goals

- Do not package model weights inside the PyPI package.
- Do not publish raw challenge data or uploaded admin CSVs.
- Do not make the mobile app depend on the package directly.
- Do not require a local LLM for classification-only use.
- Do not break the existing admin/backend flow while extracting the package API.

## Recommended Naming

Distribution name:

```text
glimo-hsd
```

Import namespace:

```python
import glimo_hsd
```

Low-risk migration option:

- Keep existing `contextsafe_hsd` internals initially.
- Add `src/glimo_hsd/` as the stable public wrapper namespace.
- Move internals only after tests prove parity.

## Expected Deliverables

1. Python package installable with `pip install glimo-hsd`.
2. Stable library API for full pipeline and individual steps.
3. CLI command named `glimo-hsd`.
4. Deterministic output directory with cached step outputs.
5. `manifest.json` for every run.
6. Hugging Face model repo for the custom DeHateBERT checkpoint.
7. Model card with Apache-2.0 license, challenge context, limitations, and usage.
8. Examples for labeled CSV, unlabeled CSV, classification-only, and full restatement.
9. Tests proving package API matches current backend behavior.

## Public API

Expose these from `glimo_hsd.__init__`:

```python
from glimo_hsd.config import PipelineConfig
from glimo_hsd.pipeline import process_csv
from glimo_hsd.results import PipelineResult, StepResult
from glimo_hsd.steps import (
    scrub_csv,
    classify_csv,
    generate_token_importances,
    restate_csv,
    audit_restatements,
    final_scrub_csv,
)
```

Core objects:

```python
PipelineConfig
PipelineResult
StepResult
ModelConfig
RestatementConfig
AuditConfig
```

`PipelineResult` should expose file paths rather than loading everything into memory:

```python
result.source_csv
result.scrubbed_csv
result.predictions_csv
result.importances_csv
result.restatement_input_csv
result.restated_csv
result.audit_csv
result.manifest_json
result.output_dir
```

## Package Structure

Target structure:

```text
src/glimo_hsd/
  __init__.py
  config.py
  pipeline.py
  results.py
  io.py
  cli.py

  steps/
    __init__.py
    pii.py
    classify.py
    token_importance.py
    restate.py
    deviation_audit.py
    final_scrub.py

  models/
    __init__.py
    dehatebert.py
    registry.py

  backends/
    __init__.py
    qwen.py
    hf_transformers.py
    local_http.py

  schemas/
    __init__.py
    columns.py
    manifest.py
```

If moving code is too risky for the first pass, create wrapper modules in `src/glimo_hsd/` that call current `contextsafe_hsd` functions.

## Dependency Strategy

Use optional extras in `pyproject.toml`.

Suggested extras:

```text
glimo-hsd              lightweight core, CSV/schema/config utilities
glimo-hsd[hf]          transformers, torch, huggingface-hub
glimo-hsd[llm]         local LLM/restatement dependencies
glimo-hsd[api]         Flask/FastAPI backend dependencies
glimo-hsd[dev]         pytest, ruff, mypy, build, twine
glimo-hsd[all]         all runtime extras
```

Model weights should be loaded from:

```text
batinium/glimo-dehatebert-privhsd
```

or from a local model directory.

## CLI Plan

Add console entry point:

```toml
[project.scripts]
glimo-hsd = "glimo_hsd.cli:main"
```

Commands:

```bash
glimo-hsd process input.csv --text-col text --out outputs/run
glimo-hsd scrub input.csv --text-col text --out outputs/scrubbed.csv
glimo-hsd classify input.csv --text-col text --out outputs/predictions.csv
glimo-hsd importances input.csv --text-col text --out outputs/importances.csv
glimo-hsd restate input.csv --text-col text --label-col hs --out outputs/restated.csv
glimo-hsd audit original.csv restated.csv --out outputs/audit.csv
```

Minimum viable CLI is only:

```bash
glimo-hsd process
```

Step commands can be added after the full process command works.

## Caching and Manifest

Every pipeline run should create:

```text
output_dir/
  source.csv
  scrubbed.csv
  dehatebert_predictions.csv
  token_importances.csv
  restatement_input.csv
  restated.csv
  final_scrubbed.csv
  deviation_audit.csv
  manifest.json
```

`manifest.json` should include:

```json
{
  "pipeline_version": "0.1.0",
  "input_hash": "...",
  "config_hash": "...",
  "created_at": "...",
  "source_path": "...",
  "text_col": "text",
  "label_col": "hs",
  "model_id": "batinium/glimo-dehatebert-privhsd",
  "model_revision": null,
  "steps": {
    "pii_scrub": {"status": "complete", "path": "scrubbed.csv"},
    "classification": {"status": "complete", "path": "dehatebert_predictions.csv"},
    "token_importance": {"status": "complete", "path": "token_importances.csv"},
    "restatement": {"status": "complete", "path": "restated.csv"},
    "final_scrub": {"status": "complete", "path": "final_scrubbed.csv"},
    "deviation_audit": {"status": "complete", "path": "deviation_audit.csv"}
  }
}
```

Cache key should include:

```text
input file hash
text column
label column
model id
model revision
threshold
prompt version
PII config
restatement backend
final scrub flag
package version
```

Admin outputs should include:

```text
pipeline_run_id
row_hash
source_hash
```

Citizen-facing reviewer exports can stay minimal unless lookup requires the hashes.

## Labeled and Unlabeled CSV Behavior

Current backend already supports this behavior and package API should preserve it:

- If a label column exists, use it for restatement prompt conditioning.
- If no label column exists, classify first with DeHateBERT.
- Materialize predicted labels into an internal restatement input CSV.
- Preserve the uploaded/source schema in public restatement outputs where possible.

Expected label names to recognize:

```text
hs
label
hate
is_hate
predicted_hate
hs_predicted
```

## Restatement Backend Strategy

Do not hardcode Qwen as the only possible backend.

Use a backend abstraction:

```python
RestatementBackend
QwenRestatementBackend
LocalHttpRestatementBackend
NoopRestatementBackend
```

For package MVP:

- Provide a local command/backend wrapper for the current Qwen flow.
- Allow skipping restatement with `restatement_backend="none"`.
- Keep prompt versioning explicit.

Example config:

```python
PipelineConfig(
    restatement_backend="qwen",
    restatement_model="qwen3.5:4b",
    prompt_version="descriptive_v2",
)
```

## Hugging Face Model Release

Publish the custom DeHateBERT model as a separate model repo:

```text
batinium/glimo-dehatebert-privhsd
```

Recommended contents:

```text
README.md
config.json
model.safetensors
tokenizer.json
tokenizer_config.json
special_tokens_map.json
vocab.txt or merges files, depending on tokenizer
label_mapping.json
eval_metrics.json
training_args.json, only if safe
```

Model card requirements:

- License: Apache-2.0
- Developed during the PrivHSD Challenge
- Base model name and license
- Task: hate speech / harmful speech classification
- Intended use: research, moderation assistance, admin triage, pipeline scoring
- Not intended use: fully automated enforcement without human review
- Data statement: do not disclose private/raw samples
- Metrics: include validation/test metrics if available
- Threshold: document default decision threshold
- Limitations: false positives, false negatives, dialect bias, contextual ambiguity
- Safety note: classifier and restatement outputs require human/admin review

Suggested tags:

```text
text-classification
hate-speech-detection
transformers
pytorch
apache-2.0
privhsd
glimo
```

Upload commands later:

```bash
hf auth whoami
hf repos create batinium/glimo-dehatebert-privhsd --type model --exist-ok
hf upload batinium/glimo-dehatebert-privhsd path/to/exported_model --type model
```

If the model folder is large:

```bash
hf upload-large-folder batinium/glimo-dehatebert-privhsd path/to/exported_model --type model
```

## PyPI Release Plan

Use TestPyPI first.

Build:

```bash
python -m pip install -U build twine
python -m build
twine check dist/*
```

Upload to TestPyPI:

```bash
twine upload --repository testpypi dist/*
```

Install check:

```bash
python -m venv /tmp/glimo-test
/tmp/glimo-test/bin/pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple glimo-hsd
/tmp/glimo-test/bin/python -c "import glimo_hsd; print(glimo_hsd.__version__)"
```

Then publish to PyPI:

```bash
twine upload dist/*
```

## Implementation Phases

### Phase 0: Safety Check

- Confirm `git status --short --branch` is clean.
- Do not commit `data/admin_uploads/`, `data/outputs/`, model artifacts, or raw datasets.
- Run baseline tests before packaging changes.

Baseline commands:

```bash
python -m ruff check contextsafe_hsd tests scripts
python -m pytest -q
cd mobile && npm run lint
cd mobile && npx tsc --noEmit
```

### Phase 1: Add Package Skeleton

- Add `src/glimo_hsd/`.
- Add `glimo_hsd.__init__`.
- Add config/result dataclasses.
- Add wrapper around current backend bundle function.
- Add minimal `pyproject.toml` packaging metadata if not already suitable.

### Phase 2: Extract Stable Pipeline Function

Create:

```python
process_csv(input_csv: str | Path, config: PipelineConfig) -> PipelineResult
```

This should call the same backend code used by the admin upload/job flow.

Acceptance:

- Existing admin API still works.
- New library call creates the same output files as backend bundle.

### Phase 3: Add Step Wrappers

Expose individual step wrappers:

```python
scrub_csv
classify_csv
generate_token_importances
restate_csv
audit_restatements
final_scrub_csv
```

Acceptance:

- Each step can be called independently.
- Full pipeline still uses the same step functions.

### Phase 4: Add CLI

Implement `glimo-hsd process` first.

Required options:

```text
input_csv
--text-col
--label-col
--out
--model-id
--model-revision
--threshold
--restatement-backend
--final-scrub
--force
```

Acceptance:

- CLI can process a labeled CSV.
- CLI can process an unlabeled CSV by classifying first.
- CLI reuses cached outputs unless config/input changes.

### Phase 5: Model Loader Cleanup

Add a single DeHateBERT loader that accepts:

```text
HF model id
HF revision
local model path
device
batch size
threshold
```

Acceptance:

- Works with local checkpoint.
- Works with HF model id after upload.
- Does not require model weights in repo or PyPI wheel.

### Phase 6: Hugging Face Export

Create an export script:

```bash
python scripts/export_dehatebert_for_hf.py \
  --checkpoint path/to/checkpoint \
  --out dist/hf/glimo-dehatebert-privhsd
```

Script should write:

```text
model.safetensors
config.json
tokenizer files
label_mapping.json
eval_metrics.json
README.md
```

Acceptance:

- `transformers.pipeline("text-classification", model=local_export_dir)` works locally.

### Phase 7: Docs and Examples

Add:

```text
docs/python_package.md
examples/process_labeled_csv.py
examples/process_unlabeled_csv.py
examples/classify_only.py
examples/audit_restatements.py
```

README should include:

- Install
- Full pipeline example
- CLI example
- Hugging Face model example
- Output schema
- Safety limitations

### Phase 8: Tests

Add tests for:

- `PipelineConfig` defaults.
- Full `process_csv` with labeled CSV.
- Full `process_csv` with unlabeled CSV.
- Cache reuse.
- Output manifest.
- CLI smoke test.
- Result paths.
- No raw upload/cache data committed.

Test command:

```bash
python -m pytest -q
```

### Phase 9: Release

- Build wheel and sdist.
- Test install in clean venv.
- Upload model to Hugging Face.
- Update package default model id to HF repo.
- Upload package to TestPyPI.
- Verify install from TestPyPI.
- Upload package to PyPI.
- Tag GitHub release.

Suggested tag:

```text
v0.1.0
```

## Risks and Handling

### Heavy Dependencies

Keep `torch`, `transformers`, and LLM dependencies optional. The base package should import without loading model frameworks.

### Private Data

Never publish:

- uploaded admin CSVs
- challenge raw data if license/privacy is unclear
- generated outputs containing original user text
- local caches

### Restatement Backend

Restatement may depend on a local Qwen setup. Package should allow:

```python
restatement_backend="none"
```

This makes classification and audit tooling usable even without local LLM access.

### Semantic Drift

Deviation audit is not a guarantee. Documentation should describe it as an automated warning layer for admin review.

### Model Bias

HF model card must clearly state that classifier output is for triage and research, not final enforcement.

## First Implementation Task for New Session

Start with this sequence:

```bash
git status --short --branch
python -m ruff check contextsafe_hsd tests scripts
python -m pytest -q
```

Then inspect the current backend bundle entry points:

```bash
rg "bundle|Pipeline|restatement|dehatebert|token_importance|manifest" contextsafe_hsd scripts tests
```

Create `src/glimo_hsd/` wrappers around existing behavior first. Do not move large chunks until the wrapper API is tested.

Minimum first PR/commit should add:

- `src/glimo_hsd/__init__.py`
- `src/glimo_hsd/config.py`
- `src/glimo_hsd/results.py`
- `src/glimo_hsd/pipeline.py`
- `src/glimo_hsd/cli.py`
- tests for `process_csv`
- package metadata updates

Acceptance for first commit:

```bash
python -m ruff check contextsafe_hsd glimo_hsd tests scripts
python -m pytest -q
python -m build
```

If `src/` layout is used, adjust ruff/test commands accordingly.

