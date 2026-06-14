# Data Contract

Status: active
Owner area: CSV contract and submission
Last verified: 2026-06-13
Primary code: `privhsd/csv_pipeline.py`, `privhsd/submission.py`,
`contextsafe_hsd/`

This is the authoritative contract for exact-format outputs. Any agent changing
CSV reading, writing, submission creation, validation, or public API wrappers
must check this file.

## Exact-Format Contract

The official path must satisfy all of these rules before upload:

- Input is a CSV with at least one text column.
- Output has the same row count and row order.
- Output preserves every non-text column exactly unless an explicit local audit
  mode is selected.
- Exact-format output replaces the selected text column in place.
- Column order is unchanged.
- IDs, labels, source/split columns, author IDs, and other metadata are
  preserved byte-for-byte.
- A four-column input such as `source,author_id,text,is_hate_speech` must
  produce exactly those four columns, in that order, when `--replace-text` is
  used.
- Local audit output may add `privatized_text`, audit JSON, or manifest files,
  but this must be opt-in and must never be used as the exact official upload.
- Manifest files record command, commit, hashes, mode, metric depth,
  provider/model status, validation status, aggregate metrics, and warnings.
- Raw official examples, generated sensitive rows, provider/model outputs, and
  detailed reports stay under ignored `data/` paths.

## Allowed Output Modes

| Mode | Shape | Intended use |
| --- | --- | --- |
| `create-submission --replace-text` | Exact input schema with selected text replaced | Official upload candidate |
| `sanitize-classify` | Original columns preserved, selected text replaced, HSD prediction columns appended | Local enriched analysis/unseen-data triage |
| `anonymize --replace-text` | Exact input schema with selected text replaced | Local compatibility path |
| `anonymize` without replace | Adds helper output column | Local audit only |
| Workbench replace-text CSV | Exact input schema with selected text replaced | Demo/download candidate |
| Workbench helper-column CSV | Adds `privatized_text` | Local audit only |

## Validation Gate

Every exact candidate should be followed by:

```bash
python -m privhsd.cli validate-submission \
  --source INPUT.csv \
  --submission OUTPUT.csv \
  --text-col text \
  --id-col id \
  --output data/outputs/OUTPUT.validation.json
```

Validation failure blocks upload, even if local privacy or utility metrics look
good.

## Ownership Notes

- Do not change the exact CSV contract from a provider/model workstream.
- If challenge rules allow row filtering, document that as a runbook exception;
  do not silently relax this contract.
- `bound-contributions` can preserve schema among retained rows, but it drops
  rows and is therefore not an exact-format submission path by default.
- `sanitize-classify` is intentionally not exact-format because it adds
  prediction columns. Use `create-submission --replace-text` for uploads.
