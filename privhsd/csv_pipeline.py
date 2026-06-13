"""CSV input/output pipeline for challenge datasets."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from collections import Counter
from typing import Any

from .metrics import aggregate_metrics, row_metric, row_metric_for_depth
from .pipeline import PrivatizerConfig, privatize_text
from .presidio_augment import filtered_presidio_spans, load_presidio_analyzer


class CsvPipelineError(ValueError):
    pass


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise CsvPipelineError(f"{path}: CSV header is required")
        rows = [dict(row) for row in reader]
        return rows, list(reader.fieldnames)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def process_csv(
    input_path: Path,
    output_path: Path,
    *,
    text_col: str,
    id_col: str | None = None,
    output_col: str = "privatized_text",
    replace_text: bool = False,
    audit_path: Path | None = None,
    mode: str = "balanced",
    generalize_targets: bool | None = None,
    style_scrub: bool = False,
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
    rows, fieldnames = read_csv(input_path)
    if text_col not in fieldnames:
        raise CsvPipelineError(f"{input_path}: missing text column {text_col!r}")
    if id_col and id_col not in fieldnames:
        raise CsvPipelineError(f"{input_path}: missing id column {id_col!r}")

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
        )
        context = AutoPipelineContext.create(auto_config)
        result = AutoPipelineEngine(context).process_rows(
            rows,
            fieldnames,
            text_col=text_col,
            id_col=id_col,
            output_col=output_col,
            replace_text=replace_text,
        )
        write_csv(output_path, result.rows, result.fieldnames)
        summary = {
            "input": str(input_path),
            "output": str(output_path),
            **result.summary,
        }
        if audit_path:
            write_json(
                audit_path,
                {
                    "summary": summary,
                    "rows": result.audit_rows,
                },
            )
        return summary

    config = PrivatizerConfig(
        mode=mode,
        generalize_targets=generalize_targets,
        style_scrub=style_scrub,
    )
    output_fieldnames = list(fieldnames)
    if not replace_text and output_col not in output_fieldnames:
        output_fieldnames.append(output_col)

    audit_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    output_rows: list[dict[str, Any]] = []
    presidio_analyzer = load_presidio_analyzer() if presidio_augment else None
    presidio_counts: Counter[str] = Counter()
    presidio_rejected_counts: Counter[str] = Counter()

    for index, row in enumerate(rows, start=1):
        original = row.get(text_col, "")
        if original is None:
            original = ""
        extra_spans = []
        presidio_report = None
        if presidio_analyzer:
            extra_spans, presidio_report = filtered_presidio_spans(
                str(original),
                presidio_analyzer,
                language=presidio_language,
            )
            presidio_counts.update(presidio_report["accepted_counts_by_type"])
            presidio_rejected_counts.update(
                presidio_report["rejected_counts_by_reason"]
            )
        result = privatize_text(str(original), config, extra_spans=extra_spans)
        out_row = dict(row)
        if replace_text:
            out_row[text_col] = result.text
        else:
            out_row[output_col] = result.text
        output_rows.append(out_row)

        row_id = row.get(id_col) if id_col else str(index)
        row_metrics = row_metric_for_depth(
            str(original),
            result.text,
            metric_depth=metric_depth,
            row_index=index,
        )
        row_metrics.update(result.metrics)
        metric_rows.append(row_metrics)
        audit_row = {
            "row_id": row_id,
            "row_index": index,
            "mode": mode,
            "changed": result.metrics["changed"],
            "metrics": row_metrics,
            "provider_fusion": result.provider_audit.get("fusion", {}),
            "transformations": list(result.transformations),
        }
        if presidio_report:
            audit_row["presidio_augment"] = presidio_report
        audit_rows.append(audit_row)

    write_csv(output_path, output_rows, output_fieldnames)
    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "text_col": text_col,
        "id_col": id_col,
        "output_col": text_col if replace_text else output_col,
        "replace_text": replace_text,
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
        "metrics": aggregate_metrics(metric_rows),
    }
    if audit_path:
        write_json(
            audit_path,
            {
                "summary": summary,
                "rows": audit_rows,
            },
        )
    return summary


def evaluate_csv(
    input_path: Path,
    *,
    text_col: str,
    privatized_col: str,
    output_path: Path | None = None,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    if text_col not in fieldnames:
        raise CsvPipelineError(f"{input_path}: missing text column {text_col!r}")
    if privatized_col not in fieldnames:
        raise CsvPipelineError(
            f"{input_path}: missing privatized column {privatized_col!r}"
        )
    row_metrics = [
        row_metric(row.get(text_col, "") or "", row.get(privatized_col, "") or "")
        for row in rows
    ]
    result = {
        "input": str(input_path),
        "text_col": text_col,
        "privatized_col": privatized_col,
        "metrics": aggregate_metrics(row_metrics),
        "rows": row_metrics,
    }
    if output_path:
        write_json(output_path, result)
    return result
