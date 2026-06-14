# Privacy Review Workbench

Thin local demo app for ContextSafe-HSD. It is intentionally separate from the
main pipeline package:

```text
workbench/backend/    FastAPI wrapper around privhsd APIs
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

The backend processes pasted text in memory and returns aggregate metrics,
offsets, placeholders, and warnings. It does not write raw text, logs, CSVs, or
reports. Use synthetic or consented text for public demos.

Paste-text mode defaults to deterministic `balanced` privatization. CSV uploads
are processed in memory and default to `auto` with fast metrics and local-only
optional model behavior. When "Replace text column" is enabled, the downloaded
CSV preserves the original schema and writes the privatized text back into the
selected text column. When it is disabled, the backend adds a
`privatized_text` helper column for local audit only.

## Highlighting

- Orange spans are masked identifiers or quasi-identifiers.
- Green spans are protected HSD target cues. They are detected and preserved in
  `balanced` mode so downstream HSD review still sees the legally relevant
  target evidence.

## Detection Layers

- Deterministic rules and small lexicons run for every CSV row.
- Auto mode reports status for Presidio, scrubadub, GLiNER, token-policy,
  semantic, local LLM, and HSD advisory components from installed local
  dependencies and artifacts. Available providers/models used by the current
  engine are lazy-loaded only for routed rows. Missing optional components are
  shown as skipped/missing and fall back to the deterministic candidate.
- Filtered Presidio adds broader NER spans for likely names, locations, and
  durable dates, then rejects protected HSD cues and noisy spans.
- RoBERTa + HateBERT token-policy ensemble is advisory guidance. It predicts
  token actions such as `MASK_IDENTIFIER`, `PROTECT_TARGET`, and `PROTECT_HSD`;
  auto mode batches model rows and never uses token-policy output as a direct
  rewrite.
- LLM guidance is last-resort routing advice only. The workbench does not call
  a local LLM automatically.
