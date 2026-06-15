# Privacy Review Workbench

Thin local demo app for ContextSafe-HSD. It is intentionally separate from the
main pipeline package:

```text
workbench/backend/    FastAPI wrapper around contextsafe_hsd APIs
workbench/frontend/   React/Vite UI
```

The active operational runbook is
[`docs/runbooks/workbench.md`](../docs/runbooks/workbench.md).

## Run Locally

From the repository root:

```bash
micromamba run -n contextsafe-hsd -e PYTHONNOUSERSITE=1 python launch.py --install
```

If the `contextsafe-hsd` environment is already active, either manually with
`micromamba activate contextsafe-hsd` or automatically through `direnv`, use:

```bash
python launch.py --install
```

After dependencies are installed once, use:

```bash
micromamba run -n contextsafe-hsd -e PYTHONNOUSERSITE=1 python launch.py
```

Backend reload mode is opt-in for development:

```bash
micromamba run -n contextsafe-hsd -e PYTHONNOUSERSITE=1 python launch.py --reload
```

Open `http://127.0.0.1:5173`.

Manual launch is also supported:

```bash
micromamba run -n contextsafe-hsd -e PYTHONNOUSERSITE=1 python -m pip install -e '.[workbench]'
micromamba run -n contextsafe-hsd -e PYTHONNOUSERSITE=1 python -m uvicorn workbench.backend.app:app \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
```

In a second shell:

```bash
micromamba run -n contextsafe-hsd npm install --prefix workbench/frontend
micromamba run -n contextsafe-hsd npm --prefix workbench/frontend run dev
```

## Data Handling

The dashboard processes CSV text locally and returns aggregate metrics,
protected previews, and raw-text-free insight statistics. For demonstration
flow, processed CSV results are cached under `workbench/.cache/csv_results/`
using a hash of the uploaded CSV and the active processing options. The cache is
local-only and intended for repeat demos; delete `workbench/.cache/` to clear it.
Use synthetic or consented text for public demos.

Run CSV starts a local background job and the UI polls row/phase progress from
the backend. Matching cached uploads return immediately without rerunning the
pipeline.

Human review annotations are stored under `workbench/.cache/reviews/` by result
cache key. They contain case IDs, reviewer status, and structured feedback
labels for HSD decision, harm risk, masking quality, PII feedback, context
feedback, and target-category correction. Raw CSV text is not written to review
annotation files.

CSV uploads are processed through the auto pipeline with fast metrics and
local-only optional model behavior. When "Replace text column" is enabled, the
downloaded CSV preserves the original schema and writes the privatized text back
into the selected text column. When it is disabled, the backend adds a
`privatized_text` helper column for local audit only.

## Highlighting

- Orange spans are masked identifiers or quasi-identifiers.
- Green spans are protected HSD target cues. They are detected and preserved in
  `balanced` mode so downstream HSD review still sees the legally relevant
  target evidence.

## Detection Layers

- Deterministic rules and small lexicons run for every CSV row.
- Auto mode reports the active dashboard path: deterministic baseline,
  Presidio/scrubadub PII assist, candidate selection, exact-format export, and
  optional sidecar-only local LLM review.
- GLiNER public controls were removed from the workbench runtime.
- Filtered Presidio adds broader NER spans for likely names, locations, and
  durable dates, then rejects protected HSD cues and noisy spans.
- HSD advisory uses the registered hate-speech classifiers to score the
  original and chosen protected candidate for each row, then rejects candidate
  rewrites that lose too much hatred-detection signal. Platform insight uses
  CSV post-classification labels when present; otherwise it uses these real
  pipeline HSD advisory scores. It is not auto-moderation.
