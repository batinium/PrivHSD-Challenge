"""Exact-format CSV validation helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from typing import Any

from .csv_pipeline import read_csv, write_json
from .row_ids import report_row_id, safe_value_summary


class SubmissionError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def validate_text_columns(fieldnames: list[str], text_cols: list[str]) -> None:
    if not text_cols:
        raise SubmissionError("at least one --text-col is required")
    missing = [column for column in text_cols if column not in fieldnames]
    if missing:
        raise SubmissionError(f"missing text column(s): {', '.join(missing)}")


def validation_report(
    source_path: Path,
    submission_path: Path,
    *,
    text_cols: list[str],
    id_col: str | None = None,
    allow_helper_columns: bool = False,
) -> dict[str, Any]:
    source_rows, source_fields = read_csv(source_path)
    submission_rows, submission_fields = read_csv(submission_path)
    validate_text_columns(source_fields, text_cols)
    validate_text_columns(submission_fields, text_cols)
    if id_col and id_col not in source_fields:
        raise SubmissionError(f"{source_path}: missing id column {id_col!r}")
    if id_col and id_col not in submission_fields:
        raise SubmissionError(f"{submission_path}: missing id column {id_col!r}")

    issues: list[dict[str, Any]] = []
    helper_columns = [column for column in submission_fields if column not in source_fields]
    missing_columns = [column for column in source_fields if column not in submission_fields]
    if missing_columns:
        issues.append({"code": "missing_columns", "columns": missing_columns})
    if helper_columns and not allow_helper_columns:
        issues.append({"code": "helper_columns_present", "columns": helper_columns})
    if not allow_helper_columns and submission_fields != source_fields:
        issues.append(
            {
                "code": "column_order_mismatch",
                "source_columns": source_fields,
                "submission_columns": submission_fields,
            }
        )
    if len(source_rows) != len(submission_rows):
        issues.append(
            {
                "code": "row_count_mismatch",
                "source_row_count": len(source_rows),
                "submission_row_count": len(submission_rows),
            }
        )

    compared_rows = min(len(source_rows), len(submission_rows))
    id_mismatches = []
    metadata_mismatches = []
    changed_text_cells = 0
    unchanged_text_cells = 0
    metadata_cols = [
        column
        for column in source_fields
        if column not in set(text_cols) and column in submission_fields
    ]
    for index in range(compared_rows):
        source_row = source_rows[index]
        submission_row = submission_rows[index]
        if id_col and source_row.get(id_col) != submission_row.get(id_col):
            id_mismatches.append(
                {
                    "row_index": index + 1,
                    "source_id": safe_value_summary(source_row.get(id_col)),
                    "submission_id": safe_value_summary(submission_row.get(id_col)),
                }
            )
        for column in metadata_cols:
            if source_row.get(column) != submission_row.get(column):
                metadata_mismatches.append(
                    {
                        "row_index": index + 1,
                        "row_id": report_row_id(
                            source_row,
                            row_index=index + 1,
                            id_col=id_col,
                        ),
                        "column": column,
                    }
                )
        for column in text_cols:
            if source_row.get(column, "") == submission_row.get(column, ""):
                unchanged_text_cells += 1
            else:
                changed_text_cells += 1
    if id_mismatches:
        issues.append(
            {
                "code": "id_order_mismatch",
                "count": len(id_mismatches),
                "examples": id_mismatches[:20],
            }
        )
    if metadata_mismatches:
        issues.append(
            {
                "code": "metadata_mismatch",
                "count": len(metadata_mismatches),
                "examples": metadata_mismatches[:20],
            }
        )

    return {
        "source": str(source_path),
        "submission": str(submission_path),
        "valid": not issues,
        "text_cols": text_cols,
        "id_col": id_col,
        "allow_helper_columns": allow_helper_columns,
        "source_row_count": len(source_rows),
        "submission_row_count": len(submission_rows),
        "source_columns": source_fields,
        "submission_columns": submission_fields,
        "changed_text_cells": changed_text_cells,
        "unchanged_text_cells": unchanged_text_cells,
        "issues": issues,
    }


def validate_submission(
    source_path: Path,
    submission_path: Path,
    *,
    text_cols: list[str],
    id_col: str | None = None,
    output_path: Path | None = None,
    allow_helper_columns: bool = False,
    strict: bool = True,
) -> dict[str, Any]:
    report = validation_report(
        source_path,
        submission_path,
        text_cols=text_cols,
        id_col=id_col,
        allow_helper_columns=allow_helper_columns,
    )
    if output_path:
        write_json(output_path, report)
    if strict and not report["valid"]:
        codes = ", ".join(issue["code"] for issue in report["issues"])
        raise SubmissionError(f"submission validation failed: {codes}")
    return report
