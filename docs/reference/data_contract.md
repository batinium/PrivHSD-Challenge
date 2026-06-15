# Data Contract

Status: active
Last verified: 2026-06-15

This is the exact CSV contract for `protect`.

## Exact Output Rules

- Input is a CSV with a selected text column.
- Output preserves row count and row order.
- Output preserves column names and column order exactly.
- Only the selected text column is replaced.
- Every non-text value is preserved byte-for-byte.
- No helper, classification, score, suggestion, or audit columns are appended.
- Manifest, audit, validation, and review data are sidecars.
- Sidecars must not contain raw original row text.

Example:

```text
source,ID,text,hs
train,1,Email alex@example.test because Muslims should leave.,1
```

must remain:

```text
source,ID,text,hs
train,1,Email [EMAIL] because Muslims should leave.,1
```

## Validation

```bash
python -m contextsafe_hsd.cli validate-submission \
  --source INPUT.csv \
  --submission OUTPUT.csv \
  --text-col text \
  --output OUTPUT.validation.json
```

Use `--id-col` only for a privacy-safe stable key present in both files. Do not
use raw author, username, handle, or account columns as review IDs.

Validation failure blocks hand-in even when privacy metrics look good.

## Sidecars

The final pipeline may write:

- `OUTPUT.manifest.json`: aggregate stage, provider, model, validation, and
  local LLM review status.
- `OUTPUT.audit.json`: row-level raw-text-free audit details.
- `OUTPUT.validation.json`: explicit exact-shape validation report.

Local LLM HSD labels, reason tags, parse/fallback counts, and residual PII
suggestions belong in these sidecars only.
