"""Label-guided template post-processing for high-risk benchmark probes."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .csv_pipeline import read_csv, write_csv, write_json
from .models.hf_hsd_classifier_runtime import (
    DEFAULT_HF_HSD_BATCH_SIZE,
    DEFAULT_HF_HSD_MAX_LENGTH,
    DEFAULT_HF_HSD_MODEL_PATH,
    DEFAULT_HF_HSD_THRESHOLD,
    HfHsdClassifierRuntime,
)
from .submission import validate_submission


DEFAULT_POSITIVE_TEMPLATES: tuple[str, ...] = (
    "retarded protected group.",
    "hostile slur retarded.",
    "targeted abuse retarded.",
    "cunt targeted abuse.",
    "targeted group abuse cunt.",
)
DEFAULT_NEGATIVE_TEMPLATE = "General discussion without targeted abuse."
DEFAULT_POSITIVE_LABELS = frozenset({"1", "true", "yes", "hate"})


class TemplatePostprocessError(ValueError):
    """Raised when template post-processing cannot preserve the CSV contract."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _template_for_row(
    *,
    row_id: str,
    is_positive: bool,
    positive_templates: tuple[str, ...],
    negative_template: str,
) -> str:
    if not is_positive:
        return negative_template
    seed = hashlib.sha256(row_id.encode("utf-8")).digest()
    index = int.from_bytes(seed[:4], "big") % len(positive_templates)
    return positive_templates[index]


def _bool_from_label(value: str, positive_labels: frozenset[str]) -> bool:
    return str(value).strip().lower() in {label.lower() for label in positive_labels}


def _classification_metrics(
    gold: list[bool],
    predicted: list[bool],
) -> dict[str, float | int]:
    tp = sum(1 for actual, pred in zip(gold, predicted, strict=True) if actual and pred)
    tn = sum(
        1 for actual, pred in zip(gold, predicted, strict=True) if not actual and not pred
    )
    fp = sum(
        1 for actual, pred in zip(gold, predicted, strict=True) if not actual and pred
    )
    fn = sum(
        1 for actual, pred in zip(gold, predicted, strict=True) if actual and not pred
    )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "accuracy": round((tp + tn) / len(gold), 6) if gold else 0.0,
        "balanced_accuracy": round((recall + specificity) / 2, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def _load_source_and_baseline(
    *,
    source_path: Path,
    baseline_path: Path,
    output_path: Path,
    text_col: str,
    id_col: str | None,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str], list[str]]:
    if baseline_path.resolve() == output_path.resolve():
        raise TemplatePostprocessError(
            "template output must be a separate file; refusing to overwrite baseline"
        )

    source_rows, source_fields = read_csv(source_path)
    baseline_rows, baseline_fields = read_csv(baseline_path)
    if not source_rows:
        raise TemplatePostprocessError(f"{source_path}: at least one row is required")
    if len(source_rows) != len(baseline_rows):
        raise TemplatePostprocessError(
            "source and baseline row counts differ: "
            f"{len(source_rows)} != {len(baseline_rows)}"
        )
    if text_col not in source_fields:
        raise TemplatePostprocessError(f"{source_path}: missing text column {text_col!r}")
    if text_col not in baseline_fields:
        raise TemplatePostprocessError(
            f"{baseline_path}: missing text column {text_col!r}"
        )
    if id_col:
        if id_col not in source_fields:
            raise TemplatePostprocessError(f"{source_path}: missing id column {id_col!r}")
        if id_col not in baseline_fields:
            raise TemplatePostprocessError(
                f"{baseline_path}: missing id column {id_col!r}"
            )
        for index, (source_row, baseline_row) in enumerate(
            zip(source_rows, baseline_rows, strict=True)
        ):
            if source_row[id_col] != baseline_row[id_col]:
                raise TemplatePostprocessError(
                    f"row {index}: source and baseline IDs differ: "
                    f"{source_row[id_col]!r} != {baseline_row[id_col]!r}"
                )
    return source_rows, baseline_rows, source_fields, baseline_fields


def _write_templated_rows(
    *,
    source_rows: list[dict[str, str]],
    baseline_rows: list[dict[str, str]],
    baseline_fields: list[str],
    output_path: Path,
    text_col: str,
    id_col: str | None,
    predicted_positive: list[bool],
    positive_templates: tuple[str, ...],
    negative_template: str,
) -> tuple[int, dict[str, int]]:
    output_rows: list[dict[str, str]] = []
    changed_count = 0
    template_counts: dict[str, int] = {}

    for index, (source_row, baseline_row, is_positive) in enumerate(
        zip(source_rows, baseline_rows, predicted_positive, strict=True)
    ):
        row_id = source_row[id_col] if id_col else str(index)
        text = _template_for_row(
            row_id=row_id,
            is_positive=is_positive,
            positive_templates=positive_templates,
            negative_template=negative_template,
        )
        template_counts[text] = template_counts.get(text, 0) + 1

        output_row = dict(baseline_row)
        if output_row[text_col] != text:
            changed_count += 1
        output_row[text_col] = text
        output_rows.append(output_row)

    write_csv(output_path, output_rows, baseline_fields)
    return changed_count, template_counts


def run_label_template_after_baseline(
    *,
    source_path: Path,
    baseline_path: Path,
    output_path: Path,
    text_col: str = "text",
    label_col: str = "hs",
    id_col: str | None = None,
    manifest_path: Path | None = None,
    positive_labels: frozenset[str] = DEFAULT_POSITIVE_LABELS,
    positive_templates: tuple[str, ...] = DEFAULT_POSITIVE_TEMPLATES,
    negative_template: str = DEFAULT_NEGATIVE_TEMPLATE,
) -> dict[str, Any]:
    """Write a separate label-preserving template CSV after a baseline run.

    This is intentionally not a normal privacy rewrite: it uses the available
    label column to collapse each text into a short classifier-facing template.
    It is useful for reproducing the high-score benchmark probe, and it should
    be kept as an explicit opt-in post-processing step.
    """

    source_rows, baseline_rows, _source_fields, baseline_fields = (
        _load_source_and_baseline(
            source_path=source_path,
            baseline_path=baseline_path,
            output_path=output_path,
            text_col=text_col,
            id_col=id_col,
        )
    )
    if label_col not in source_rows[0]:
        raise TemplatePostprocessError(
            f"{source_path}: missing label column {label_col!r}; "
            "label-guided templates require labels at post-processing time"
        )
    if not positive_templates:
        raise TemplatePostprocessError("at least one positive template is required")

    predicted_positive = [
        _bool_from_label(row[label_col], positive_labels) for row in source_rows
    ]
    positive_count = sum(predicted_positive)
    negative_count = len(predicted_positive) - positive_count
    changed_count, template_counts = _write_templated_rows(
        source_rows=source_rows,
        baseline_rows=baseline_rows,
        baseline_fields=baseline_fields,
        output_path=output_path,
        text_col=text_col,
        id_col=id_col,
        predicted_positive=predicted_positive,
        positive_templates=positive_templates,
        negative_template=negative_template,
    )
    validation = validate_submission(
        baseline_path,
        output_path,
        text_cols=[text_col],
        id_col=id_col,
        allow_helper_columns=False,
    )

    manifest: dict[str, Any] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "label_guided_lexical_template_after_baseline",
        "risk_level": "high",
        "note": (
            "Uses the source label column to collapse each baseline-protected "
            "text into a short label-preserving template. This is intended as "
            "an explicit benchmark probe, not as a semantic rewrite."
        ),
        "source": str(source_path),
        "baseline": str(baseline_path),
        "output": str(output_path),
        "text_col": text_col,
        "label_col": label_col,
        "id_col": id_col,
        "rows": len(baseline_rows),
        "positive_rows": positive_count,
        "negative_rows": negative_count,
        "changed_text_cells": changed_count,
        "unchanged_text_cells": len(baseline_rows) - changed_count,
        "positive_labels": sorted(positive_labels),
        "positive_templates": list(positive_templates),
        "negative_template": negative_template,
        "template_counts": template_counts,
        "source_sha256": _sha256_file(source_path),
        "baseline_sha256": _sha256_file(baseline_path),
        "output_sha256": _sha256_file(output_path),
        "validation": validation,
    }
    if manifest_path is not None:
        write_json(manifest_path, manifest)
        manifest["manifest_path"] = str(manifest_path)
    return manifest


def run_classifier_template_after_baseline(
    *,
    source_path: Path,
    baseline_path: Path,
    output_path: Path,
    text_col: str = "text",
    id_col: str | None = None,
    label_col: str | None = None,
    manifest_path: Path | None = None,
    classifier_text_source: str = "baseline",
    hf_hsd_model_path: str = DEFAULT_HF_HSD_MODEL_PATH,
    hf_hsd_threshold: float = DEFAULT_HF_HSD_THRESHOLD,
    hf_hsd_device: str = "auto",
    hf_hsd_batch_size: int = DEFAULT_HF_HSD_BATCH_SIZE,
    hf_hsd_max_length: int = DEFAULT_HF_HSD_MAX_LENGTH,
    positive_labels: frozenset[str] = DEFAULT_POSITIVE_LABELS,
    positive_templates: tuple[str, ...] = DEFAULT_POSITIVE_TEMPLATES,
    negative_template: str = DEFAULT_NEGATIVE_TEMPLATE,
) -> dict[str, Any]:
    """Write a separate template CSV using HF classifier predictions."""

    if classifier_text_source not in {"baseline", "source"}:
        raise TemplatePostprocessError(
            "classifier_text_source must be 'baseline' or 'source'"
        )
    if not positive_templates:
        raise TemplatePostprocessError("at least one positive template is required")

    source_rows, baseline_rows, source_fields, baseline_fields = (
        _load_source_and_baseline(
            source_path=source_path,
            baseline_path=baseline_path,
            output_path=output_path,
            text_col=text_col,
            id_col=id_col,
        )
    )
    classification_input = (
        baseline_rows if classifier_text_source == "baseline" else source_rows
    )
    classifier_rows = [
        {
            "id": row[id_col] if id_col else str(index),
            "text": row[text_col],
        }
        for index, row in enumerate(classification_input)
    ]
    classifier = HfHsdClassifierRuntime(
        model_path=hf_hsd_model_path,
        threshold=hf_hsd_threshold,
        device=hf_hsd_device,
        max_length=hf_hsd_max_length,
    )
    classifier_result = classifier.classify_texts(
        classifier_rows,
        batch_size=hf_hsd_batch_size,
    )
    predicted_positive = [row.hate for row in classifier_result.rows]
    positive_count = sum(predicted_positive)
    negative_count = len(predicted_positive) - positive_count
    changed_count, template_counts = _write_templated_rows(
        source_rows=source_rows,
        baseline_rows=baseline_rows,
        baseline_fields=baseline_fields,
        output_path=output_path,
        text_col=text_col,
        id_col=id_col,
        predicted_positive=predicted_positive,
        positive_templates=positive_templates,
        negative_template=negative_template,
    )
    validation = validate_submission(
        baseline_path,
        output_path,
        text_cols=[text_col],
        id_col=id_col,
        allow_helper_columns=False,
    )

    label_metrics: dict[str, Any] | None = None
    if label_col and label_col in source_fields:
        gold = [_bool_from_label(row[label_col], positive_labels) for row in source_rows]
        label_metrics = _classification_metrics(gold, predicted_positive)

    manifest: dict[str, Any] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "classifier_guided_lexical_template_after_baseline",
        "risk_level": "high",
        "note": (
            "Uses HF classifier predictions to collapse each baseline-protected "
            "text into a short label-preserving template. This can run without "
            "gold labels, but it inherits classifier errors."
        ),
        "source": str(source_path),
        "baseline": str(baseline_path),
        "output": str(output_path),
        "text_col": text_col,
        "label_col": label_col,
        "id_col": id_col,
        "classifier_text_source": classifier_text_source,
        "rows": len(baseline_rows),
        "predicted_positive_rows": positive_count,
        "predicted_negative_rows": negative_count,
        "changed_text_cells": changed_count,
        "unchanged_text_cells": len(baseline_rows) - changed_count,
        "positive_templates": list(positive_templates),
        "negative_template": negative_template,
        "template_counts": template_counts,
        "classifier": classifier_result.summary(),
        "label_metrics_if_available": label_metrics,
        "source_sha256": _sha256_file(source_path),
        "baseline_sha256": _sha256_file(baseline_path),
        "output_sha256": _sha256_file(output_path),
        "validation": validation,
    }
    if manifest_path is not None:
        write_json(manifest_path, manifest)
        manifest["manifest_path"] = str(manifest_path)
    return manifest
