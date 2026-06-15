# Workbench Runbook

Status: active
Last verified: 2026-06-15

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
- Local LLM HSD review is sidecar-only.
- Platform insight uses explicit CSV labels or local LLM sidecar labels only.
- The workbench does not fabricate classifier votes.
- Review cache files contain case IDs and structured labels, not raw CSV text.
- Raw author/user IDs are not used as review case IDs.

## Verify

```bash
python -m pytest tests/test_workbench_csv.py -q
npm --prefix workbench/frontend run build
```
