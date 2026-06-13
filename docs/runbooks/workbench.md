# Workbench Runbook

Status: active
Owner area: workbench
Last verified: 2026-06-13
Primary code: `workbench/backend/`, `workbench/frontend/`, `launch.py`

The workbench is a local FastAPI + React demo around the existing `privhsd`
APIs. It is separate from the pipeline package.

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

- Paste-text mode processes text in memory.
- CSV upload mode defaults to `auto` with fast metrics.
- Replace-text CSV output preserves the original schema.
- Helper-column CSV output adds `privatized_text` for local audit only.
- Provider/model status is visible but the user should not need to manually
  choose providers.
- The app must not call external APIs or write raw text logs.

## Verification

```bash
python -m pytest tests/test_workbench_csv.py -q
cd workbench/frontend && npm run build
```

See also `workbench/README.md` for local app-specific notes.
