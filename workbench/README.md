# Privacy Review Workbench

Optional local demo app for ContextSafe-HSD.

```text
workbench/backend/    FastAPI wrapper
workbench/frontend/   React/Vite UI
```

## Run

```bash
python -m pip install -e '.[workbench]'
python launch.py --install
```

Open `http://127.0.0.1:5173`.

## Notes

- Exact CSV export replaces the selected text column in place.
- Local LLM review is sidecar-only and receives cleaned text.
- Platform insight uses explicit CSV labels or local LLM sidecar labels only.
- Cached results and review annotations live under `workbench/.cache/`.
- Use synthetic or consented text for demos.
