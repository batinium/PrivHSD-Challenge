# Coding Rules For Agents

## Scope

Work in this repository only unless explicitly asked. The sibling
`ContextSafe-HSD` project is reference material, not the active codebase.

## Implementation Rules

- Prefer small, testable modules in `privhsd/`.
- Keep CLI behavior stable unless the docs are updated in the same change.
- Keep the default mode as `balanced`.
- Do not make an LLM dependency required for tests or the main CLI.
- Do not add heavyweight dependencies without documenting why.
- Do not overwrite source text unless the user passes `--replace-text`.
- Use typed placeholders, not blank deletion, for privacy transformations.

## Testing Rules

Run:

```bash
python -m pytest -q
```

Add tests when changing:

- span detection
- replacement behavior
- CSV input/output
- audit JSON shape
- metrics
- dataset converters

## Data Rules

- Do not commit downloaded public datasets unless explicitly requested.
- Do not commit official challenge datasets.
- Do not log raw official examples in docs or screenshots.
- Keep generated outputs under `data/outputs/` if local output is needed.

## Documentation Rules

Update `docs/project/pipeline_design.md` when changing:

- CLI arguments
- output columns
- modes
- audit schema
- module responsibilities

Update `docs/archive/agent_notes/task_board.md` when completing or changing a task.

