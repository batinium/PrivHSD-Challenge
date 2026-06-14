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
python launch.py --install
```

After dependencies are installed once, use:

```bash
python launch.py
```

Backend reload mode is opt-in for development:

```bash
python launch.py --reload
```

Open `http://127.0.0.1:5173`.

Manual launch is also supported:

```bash
.venv/bin/python -m pip install -r workbench/backend/requirements.txt
.venv/bin/python -m uvicorn workbench.backend.app:app \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
```

In a second shell:

```bash
cd workbench/frontend
npm install
npm run dev
```

## Data Handling

The dashboard processes CSV text locally and returns aggregate metrics,
protected previews, and raw-text-free insight statistics. For demonstration
flow, processed CSV results are cached under `workbench/.cache/csv_results/`
using a hash of the uploaded CSV and the active processing options. The cache is
local-only and intended for repeat demos; delete `workbench/.cache/` to clear it.
Use synthetic or consented text for public demos.

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
  Presidio/scrubadub PII assist, token-policy candidate evidence when local
  artifacts are present, and HSD advisory preservation checks.
- GLiNER is not shown in the dashboard unless an explicit local GLiNER model is
  configured for a research run.
- Filtered Presidio adds broader NER spans for likely names, locations, and
  durable dates, then rejects protected HSD cues and noisy spans.
- RoBERTa + HateBERT token-policy ensemble is advisory guidance. It predicts
  token actions such as `MASK_IDENTIFIER`, `PROTECT_TARGET`, and `PROTECT_HSD`;
  auto mode batches model rows and never uses token-policy output as a direct
  rewrite.
- HSD advisory uses the registered hate-speech classifiers to score the
  original and chosen protected candidate for each row, then rejects candidate
  rewrites that lose too much hatred-detection signal. Platform insight uses
  CSV post-classification labels when present; otherwise it uses these real
  pipeline HSD advisory scores. It is not auto-moderation.
