"""Exact-format submission creation and validation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
from collections import Counter
from typing import Any

from .csv_pipeline import read_csv, write_csv, write_json
from .metrics import aggregate_metrics, row_metric_for_depth
from .pipeline import PrivatizerConfig, privatize_text
from .presidio_augment import filtered_presidio_spans, load_presidio_analyzer


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
                    "source_id": source_row.get(id_col),
                    "submission_id": submission_row.get(id_col),
                }
            )
        for column in metadata_cols:
            if source_row.get(column) != submission_row.get(column):
                metadata_mismatches.append(
                    {
                        "row_index": index + 1,
                        "row_id": source_row.get(id_col) if id_col else str(index + 1),
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


def create_submission(
    input_path: Path,
    output_path: Path,
    *,
    text_cols: list[str],
    id_col: str | None = None,
    manifest_path: Path | None = None,
    command: list[str] | None = None,
    mode: str = "balanced",
    generalize_targets: bool | None = None,
    style_scrub: bool = False,
    replace_text: bool = False,
    presidio_augment: bool = False,
    presidio_language: str = "en",
    metric_depth: str = "fast",
    allow_model_download: bool = False,
    device: str = "auto",
    max_model_batch_size: int = 16,
    max_provider_rows: int | None = None,
    disabled_providers: list[str] | None = None,
    disabled_models: list[str] | None = None,
    audit_level: str = "summary",
    gliner_model: str | None = None,
    gliner_profile: str = "general",
) -> dict[str, Any]:
    if not replace_text:
        raise SubmissionError("create-submission requires --replace-text")
    rows, fieldnames = read_csv(input_path)
    validate_text_columns(fieldnames, text_cols)
    if id_col and id_col not in fieldnames:
        raise SubmissionError(f"{input_path}: missing id column {id_col!r}")

    if mode == "auto":
        from .auto import AutoPipelineConfig, AutoPipelineContext, AutoPipelineEngine

        auto_config = AutoPipelineConfig(
            metric_depth=metric_depth,
            allow_model_download=allow_model_download,
            device=device,
            max_model_batch_size=max_model_batch_size,
            max_provider_rows=max_provider_rows,
            disabled_providers=frozenset(disabled_providers or []),
            disabled_models=frozenset(disabled_models or []),
            audit_level=audit_level,
            provider_language=presidio_language,
            gliner_model=gliner_model,
            gliner_profile=gliner_profile,
            generalize_targets=generalize_targets if generalize_targets is not None else False,
            style_scrub=style_scrub,
            official_mode=True,
        )
        context = AutoPipelineContext.create(auto_config)
        output_rows = [dict(row) for row in rows]
        text_column_summaries: dict[str, Any] = {}
        changed_text_cells = 0
        metrics_by_col: dict[str, Any] = {}
        for column in text_cols:
            engine_result = AutoPipelineEngine(context).process_rows(
                output_rows,
                fieldnames,
                text_col=column,
                id_col=id_col,
                output_col=column,
                replace_text=True,
            )
            output_rows = engine_result.rows
            text_column_summaries[column] = engine_result.summary
            changed_text_cells += int(engine_result.summary.get("changed_text_cells", 0) or 0)
            metrics_by_col[column] = engine_result.summary["metrics"]

        write_csv(output_path, output_rows, fieldnames)
        validation = validate_submission(
            input_path,
            output_path,
            text_cols=text_cols,
            id_col=id_col,
            allow_helper_columns=False,
            strict=True,
        )
        metrics = (
            next(iter(metrics_by_col.values()))
            if len(metrics_by_col) == 1
            else {"by_text_col": metrics_by_col}
        )
        manifest = {
            "artifact_type": "exact_format_submission",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "command": command,
            "git_commit": git_commit(),
            "input": {
                "path": str(input_path),
                "sha256": sha256_file(input_path),
                "row_count": len(rows),
            },
            "output": {
                "path": str(output_path),
                "sha256": sha256_file(output_path),
                "row_count": len(output_rows),
            },
            "columns": {
                "text_cols": text_cols,
                "id_col": id_col,
                "preserved_columns": fieldnames,
            },
            "mode": "auto",
            "baseline_mode": auto_config.baseline_mode,
            "metric_depth": metric_depth,
            "generalize_targets": auto_config.generalize_targets,
            "style_scrub": style_scrub,
            "replace_text": replace_text,
            "changed_text_cells": changed_text_cells,
            "metrics": metrics,
            "text_column_summaries": text_column_summaries,
            "providers": context.provider_status,
            "models": context.model_status,
            "load_counts": {
                "providers": dict(sorted(context.provider_load_counts.items())),
                "models": dict(sorted(context.model_load_counts.items())),
            },
            "validation": validation,
        }
        if manifest_path:
            write_json(manifest_path, manifest)
        return manifest

    config = PrivatizerConfig(
        mode=mode,
        generalize_targets=generalize_targets,
        style_scrub=style_scrub,
    )
    output_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    changed_text_cells = 0
    presidio_analyzer = load_presidio_analyzer() if presidio_augment else None
    presidio_counts: Counter[str] = Counter()
    presidio_rejected_counts: Counter[str] = Counter()
    for row in rows:
        output_row = dict(row)
        for column in text_cols:
            original = str(row.get(column, "") or "")
            extra_spans = []
            if presidio_analyzer:
                extra_spans, presidio_report = filtered_presidio_spans(
                    original,
                    presidio_analyzer,
                    language=presidio_language,
                )
                presidio_counts.update(presidio_report["accepted_counts_by_type"])
                presidio_rejected_counts.update(
                    presidio_report["rejected_counts_by_reason"]
                )
            result = privatize_text(original, config, extra_spans=extra_spans)
            output_row[column] = result.text
            metric_rows.append(
                row_metric_for_depth(
                    original,
                    result.text,
                    metric_depth=metric_depth,
                    row_index=len(metric_rows) + 1,
                )
            )
            if original != result.text:
                changed_text_cells += 1
        output_rows.append(output_row)

    write_csv(output_path, output_rows, fieldnames)
    validation = validate_submission(
        input_path,
        output_path,
        text_cols=text_cols,
        id_col=id_col,
        allow_helper_columns=False,
        strict=True,
    )
    manifest = {
        "artifact_type": "exact_format_submission",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "git_commit": git_commit(),
        "input": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
            "row_count": len(rows),
        },
        "output": {
            "path": str(output_path),
            "sha256": sha256_file(output_path),
            "row_count": len(output_rows),
        },
        "columns": {
            "text_cols": text_cols,
            "id_col": id_col,
            "preserved_columns": fieldnames,
        },
        "mode": mode,
        "metric_depth": metric_depth,
        "generalize_targets": config.target_generalization_enabled,
        "style_scrub": style_scrub,
        "presidio_augment": {
            "enabled": presidio_augment,
            "language": presidio_language if presidio_augment else None,
            "accepted_counts_by_type": dict(sorted(presidio_counts.items())),
            "rejected_counts_by_reason": dict(sorted(presidio_rejected_counts.items())),
        },
        "replace_text": replace_text,
        "changed_text_cells": changed_text_cells,
        "metrics": aggregate_metrics(metric_rows),
        "validation": validation,
    }
    if manifest_path:
        write_json(manifest_path, manifest)
    return manifest
