# Workbench Runbook

Status: active
Owner area: workbench
Last verified: 2026-06-14
Primary code: `workbench/backend/`, `workbench/frontend/`, `launch.py`

The workbench is a local FastAPI + React dashboard around the CSV auto pipeline.
It is separate from the pipeline package.

## Run Locally

From the repository root:

```bash
python launch.py --install
```

After dependencies are installed once:

```bash
python launch.py
```

Backend reload mode is opt-in:

```bash
python launch.py --reload
```

Open `http://127.0.0.1:5173`.

## Expected Behavior

- The dashboard exposes CSV auto mode only.
- CSV upload mode runs with fast metrics and local-only optional model behavior.
- Replace-text CSV output preserves the original schema.
- Helper-column CSV output adds `privatized_text` for local audit only.
- Provider/model status is derived from the active auto run. The dashboard does
  not expose manual provider or mode selection.
- Platform insight aggregates post-classification hatred labels and target-group
  statistics without retaining raw text in the report.
- The app must not call external APIs or write raw text logs.

## Verification

```bash
python -m pytest tests/test_workbench_csv.py -q
cd workbench/frontend && npm run build
```

See also `workbench/README.md` for local app-specific notes.
