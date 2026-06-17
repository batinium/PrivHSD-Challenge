# Workbench Runbook

Status: active
Last verified: 2026-06-17

The workbench is an optional local FastAPI + React demo around the final CSV
pipeline.

## Run

```bash
python -m pip install -e '.[workbench]'
python launch.py --install
```

Open `http://127.0.0.1:5173`.

Backend and frontend can also be run separately:

```bash
python -m uvicorn workbench.backend.app:app --host 127.0.0.1 --port 8000 --reload
npm install --prefix workbench/frontend
npm --prefix workbench/frontend run dev
```

## Expected Behavior

- CSV upload defaults to replacing the selected text column in place.
- Downloaded exact CSV preserves the original schema.
- Helper-column output is local audit only.
- Local LLM HSD review is sidecar-only, with the second verifier enabled by
  default as audit metadata for positive labels.
- Platform insight uses explicit CSV labels or local LLM sidecar labels only.
- The workbench does not fabricate classifier votes.
- Review cache files contain case IDs and structured labels, not raw CSV text.
- Processed CSV results are cached under `workbench/.cache/csv_results/`.
  The cache key includes the CSV hash, masking options, local LLM review
  settings, citizen restatement model, and semantic embedding model.
- The portal can list recent processed results and load one directly without
  re-uploading the CSV or rerunning local LLM / embedding stages.
- Raw author/user IDs are not used as review case IDs.
- Citizen validation generates search-proof LLM restatements from protected text
  only. Civilians see the restated evidence, not raw text or masked protected
  text.
- When enabled, semantic similarity compares original text to the citizen
  restatement with a local sentence-transformers embedding model and stores only
  the score/status, not raw text. Low-similarity restatements fall back to
  redacted evidence and record the fallback reason.

## Verify

```bash
python -m pytest tests/test_workbench_csv.py -q
npm --prefix workbench/frontend run build
```
