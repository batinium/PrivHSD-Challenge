"""Optional Presidio comparison baseline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any

from .csv_pipeline import read_csv, write_json
from .detectors import Span, detect_spans, target_group_spans
from .metrics import UTILITY_CUES
from .row_ids import report_row_id


INSTALL_HINT = (
    "Install optional Presidio comparison dependencies with: "
    "python -m pip install '.[presidio]' and install an appropriate spaCy model."
)
PRESIDIO_WARNING = (
    "Presidio is evaluated as a comparison detector baseline only. It is not "
    "required for core privhsd anonymize and should not replace the deterministic "
    "pipeline without measured privacy/HSD tradeoff gains."
)
DEFAULT_SAMPLE_SIZE = 100


class PresidioCompareError(ValueError):
    pass


@dataclass(frozen=True)
class DetectorSpan:
    start: int
    end: int
    entity_type: str
    score: float
    source: str


def rounded(value: float) -> float:
    return round(float(value), 4)


def load_presidio() -> Any:
    try:
        from presidio_analyzer import AnalyzerEngine
    except ModuleNotFoundError as exc:
        if exc.name == "presidio_analyzer":
            raise PresidioCompareError(INSTALL_HINT) from exc
        raise
    try:
        return AnalyzerEngine()
    except Exception as exc:
        raise PresidioCompareError(f"Presidio initialization failed: {exc}") from exc


def overlaps(left: DetectorSpan | Span, right: DetectorSpan | Span) -> bool:
    return left.start < right.end and left.end > right.start


def presidio_spans(results: list[Any]) -> list[DetectorSpan]:
    spans: list[DetectorSpan] = []
    for result in results:
        spans.append(
            DetectorSpan(
                start=int(result.start),
                end=int(result.end),
                entity_type=str(result.entity_type),
                score=float(getattr(result, "score", 0.0) or 0.0),
                source="presidio",
            )
        )
    return spans


def utility_cue_hit(text: str, start: int, end: int) -> bool:
    value = text[start:end].lower()
    return any(cue in value for cue in UTILITY_CUES)


def false_positive_risk_count(text: str, spans: list[DetectorSpan]) -> int:
    target_spans = target_group_spans(text)
    count = 0
    for span in spans:
        if any(overlaps(span, target_span) for target_span in target_spans):
            count += 1
            continue
        if utility_cue_hit(text, span.start, span.end):
            count += 1
    return count


def compare_row(
    analyzer: Any,
    text: str,
    *,
    language: str,
) -> dict[str, Any]:
    privhsd_spans = detect_spans(text, include_context=True, include_targets=False)
    presidio_results = analyzer.analyze(text=text, language=language)
    presidio = presidio_spans(presidio_results)
    overlap_count = sum(
        1 for span in presidio if any(overlaps(span, local) for local in privhsd_spans)
    )
    presidio_only = [
        span for span in presidio if not any(overlaps(span, local) for local in privhsd_spans)
    ]
    privhsd_only = [
        span for span in privhsd_spans if not any(overlaps(span, other) for other in presidio)
    ]
    return {
        "privhsd_span_count": len(privhsd_spans),
        "presidio_span_count": len(presidio),
        "overlap_count": overlap_count,
        "presidio_only_count": len(presidio_only),
        "privhsd_only_count": len(privhsd_only),
        "presidio_only_types": sorted({span.entity_type for span in presidio_only}),
        "privhsd_only_types": sorted({span.entity_type for span in privhsd_only}),
        "false_positive_risk_count": false_positive_risk_count(text, presidio),
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [
        "privhsd_span_count",
        "presidio_span_count",
        "overlap_count",
        "presidio_only_count",
        "privhsd_only_count",
        "false_positive_risk_count",
    ]
    return {
        field: sum(row[field] for row in rows)
        for field in fields
    }


def skipped_result(
    input_path: Path,
    *,
    text_col: str,
    id_col: str | None,
    sample_size: int,
    output_path: Path | None,
    detail: str,
) -> dict[str, Any]:
    result = {
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "comparison_type": "presidio_detector_baseline",
        "status": "skipped",
        "skip_reason": "missing_optional_dependency",
        "detail": detail,
        "warning": PRESIDIO_WARNING,
        "columns": {"text_col": text_col, "id_col": id_col},
        "sample": {"requested_sample_size": sample_size},
    }
    if output_path:
        write_json(output_path, result)
    return result


def run_presidio_comparison(
    input_path: Path,
    *,
    text_col: str,
    id_col: str | None = None,
    output_path: Path | None = None,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    language: str = "en",
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    if text_col not in fieldnames:
        raise PresidioCompareError(f"{input_path}: missing text column {text_col!r}")
    if id_col and id_col not in fieldnames:
        raise PresidioCompareError(f"{input_path}: missing id column {id_col!r}")
    if sample_size < 0:
        raise PresidioCompareError("--sample-size must be non-negative")
    try:
        analyzer = load_presidio()
    except PresidioCompareError as exc:
        return skipped_result(
            input_path,
            text_col=text_col,
            id_col=id_col,
            sample_size=sample_size,
            output_path=output_path,
            detail=str(exc),
        )

    start = time.perf_counter()
    limit = len(rows) if sample_size <= 0 else min(sample_size, len(rows))
    row_reports: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows[:limit], start=1):
        row_report = compare_row(
            analyzer,
            str(row.get(text_col, "") or ""),
            language=language,
        )
        row_report.update(
            {
                "row_index": row_index,
                "row_id": report_row_id(row, row_index=row_index, id_col=id_col),
            }
        )
        row_reports.append(row_report)
    result = {
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "comparison_type": "presidio_detector_baseline",
        "status": "ok",
        "warning": PRESIDIO_WARNING,
        "columns": {"text_col": text_col, "id_col": id_col},
        "sample": {
            "requested_sample_size": sample_size,
            "sample_size": len(row_reports),
            "source_row_count": len(rows),
            "strategy": "first_n_rows",
        },
        "language": language,
        "runtime_seconds": rounded(time.perf_counter() - start),
        "aggregate": aggregate_rows(row_reports),
        "rows": row_reports,
    }
    if output_path:
        write_json(output_path, result)
    return result
