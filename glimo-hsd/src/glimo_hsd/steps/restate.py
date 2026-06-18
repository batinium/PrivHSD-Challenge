"""Restatement CSV step."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..backends import LocalHttpRestatementBackend, NoopRestatementBackend
from ..config import RestatementConfig
from ..io import CsvError, read_csv, sha256_file, write_csv
from ..results import StepResult


def _backend(config: RestatementConfig):
    if config.backend == "none":
        return NoopRestatementBackend()
    return LocalHttpRestatementBackend(
        endpoint=config.endpoint,
        model=config.model,
        temperature=config.temperature,
        top_p=config.top_p,
        max_tokens=config.max_tokens,
        timeout_seconds=config.timeout_seconds,
        max_retries=config.max_retries,
    )


def restate_csv(
    input_csv: str | Path,
    output_csv: str | Path,
    *,
    annotated_csv: str | Path | None = None,
    text_col: str = "text",
    label_col: str = "hs",
    id_col: str | None = None,
    config: RestatementConfig | None = None,
    output_fieldnames: list[str] | None = None,
) -> StepResult:
    restatement_config = config or RestatementConfig()
    rows, fieldnames = read_csv(input_csv)
    if text_col not in fieldnames:
        raise CsvError(f"missing text column {text_col!r}")
    if label_col not in fieldnames:
        raise CsvError(f"missing label column {label_col!r}")
    public_fieldnames = output_fieldnames or fieldnames
    backend = _backend(restatement_config)
    restated_rows: list[dict[str, Any]] = []
    annotated_rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    for offset in range(0, len(rows), restatement_config.batch_size):
        batch = rows[offset : offset + restatement_config.batch_size]
        try:
            restatements = backend.restate_batch(
                batch,
                text_col=text_col,
                label_col=label_col,
                id_col=id_col,
            )
            statuses = ["ok"] * len(restatements)
            errors = [""] * len(restatements)
        except Exception as exc:
            if not restatement_config.allow_fallback:
                raise
            restatements = [str(row.get(text_col, "") or "") for row in batch]
            statuses = ["ok_fallback"] * len(batch)
            errors = [f"{type(exc).__name__}: {exc}"] * len(batch)
        for row, restatement, status, message in zip(
            batch,
            restatements,
            statuses,
            errors,
            strict=True,
        ):
            status_counts[status] = status_counts.get(status, 0) + 1
            out = dict(row)
            out[text_col] = restatement
            restated_rows.append(
                {field: out.get(field, "") for field in public_fieldnames}
            )
            annotated_rows.append(
                {
                    **row,
                    "backend_restatement": restatement,
                    "backend_restatement_final": restatement,
                    "restatement_status": status,
                    "restatement_error": message,
                }
            )
    output_path = Path(output_csv)
    write_csv(output_path, restated_rows, public_fieldnames)
    annotated_path = (
        Path(annotated_csv)
        if annotated_csv
        else output_path.with_suffix(".annotated.csv")
    )
    write_csv(
        annotated_path,
        annotated_rows,
        [
            *fieldnames,
            "backend_restatement",
            "backend_restatement_final",
            "restatement_status",
            "restatement_error",
        ],
    )
    return StepResult(
        name="restatement",
        status="complete",
        path=output_path,
        metadata={
            "backend": restatement_config.backend,
            "model": getattr(backend, "model", None),
            "endpoint": getattr(backend, "endpoint", None),
            "annotated_csv": str(annotated_path),
            "row_count": len(restated_rows),
            "status_counts": dict(sorted(status_counts.items())),
            "sha256": sha256_file(output_path),
        },
    )
