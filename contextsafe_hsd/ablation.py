"""Ablation runner for comparing deterministic privatization modes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Any

from .csv_pipeline import read_csv, write_csv, write_json
from .metrics import aggregate_metrics, row_metric
from .pipeline import PrivatizerConfig, privatize_text
from .row_ids import report_row_id
from .utility_benchmark import (
    BenchmarkError,
    INSTALL_HINT,
    load_sklearn,
    run_utility_benchmark,
)


PRIVATIZED_COL = "privatized_text"


class AblationError(ValueError):
    pass


@dataclass(frozen=True)
class AblationVariant:
    name: str
    description: str
    config: PrivatizerConfig | None


ABLATION_WARNING = (
    "Ablation metrics are local privacy/utility proxies. They are not the "
    "official PrivHSD evaluator and should not be treated as leaderboard scores."
)


ABLATION_VARIANTS: tuple[AblationVariant, ...] = (
    AblationVariant(
        name="identity",
        description="No privatization; privatized_text equals the original text.",
        config=None,
    ),
    AblationVariant(
        name="regex_only",
        description=(
            "Direct regex detectors only; context detectors and target "
            "generalization are disabled."
        ),
        config=PrivatizerConfig(
            mode="balanced",
            include_context_detectors=False,
            generalize_targets=False,
        ),
    ),
    AblationVariant(
        name="balanced",
        description="Default balanced privatization mode.",
        config=PrivatizerConfig(mode="balanced"),
    ),
    AblationVariant(
        name="privacy",
        description="Privacy mode with default target-group generalization.",
        config=PrivatizerConfig(mode="privacy"),
    ),
    AblationVariant(
        name="balanced_with_targets",
        description="Balanced mode with target-group generalization enabled.",
        config=PrivatizerConfig(mode="balanced", generalize_targets=True),
    ),
)


def variant_config_summary(variant: AblationVariant) -> dict[str, Any]:
    if variant.config is None:
        return {
            "mode": "identity",
            "include_context_detectors": False,
            "generalize_targets": False,
        }
    return {
        "mode": variant.config.mode,
        "include_context_detectors": variant.config.include_context_detectors,
        "generalize_targets": variant.config.target_generalization_enabled,
    }


def output_fieldnames(fieldnames: list[str]) -> list[str]:
    if PRIVATIZED_COL in fieldnames:
        return list(fieldnames)
    return [*fieldnames, PRIVATIZED_COL]


def validate_columns(
    input_path: Path,
    fieldnames: list[str],
    *,
    text_col: str,
    id_col: str | None,
    label_col: str | None,
) -> None:
    missing = [column for column in (text_col, id_col, label_col) if column]
    missing = [column for column in missing if column not in fieldnames]
    if missing:
        raise AblationError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )


def identity_metrics(original: str) -> dict[str, Any]:
    metrics = row_metric(original, original)
    metrics.update(
        {
            "span_count": 0,
            "direct_identifier_span_count": 0,
            "counts_by_entity_type": {},
            "direct_identifier_counts_by_entity_type": {},
            "character_similarity": 1.0,
            "changed": False,
        }
    )
    return metrics


def run_variant(
    rows: list[dict[str, str]],
    *,
    fieldnames: list[str],
    text_col: str,
    id_col: str | None,
    label_col: str | None,
    variant: AblationVariant,
) -> dict[str, Any]:
    csv_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []

    for row_index, row in enumerate(rows, start=1):
        original = str(row.get(text_col, "") or "")
        if variant.config is None:
            privatized = original
            transformations: list[dict[str, Any]] = []
            metrics = identity_metrics(original)
        else:
            result = privatize_text(original, variant.config)
            privatized = result.text
            transformations = list(result.transformations)
            metrics = row_metric(original, privatized)
            metrics.update(result.metrics)

        output_row = dict(row)
        output_row[PRIVATIZED_COL] = privatized
        csv_rows.append(output_row)
        metric_rows.append(metrics)

        row_report: dict[str, Any] = {
            "row_index": row_index,
            "row_id": report_row_id(row, row_index=row_index, id_col=id_col),
            "changed": metrics["changed"],
            "metrics": metrics,
            "transformations": transformations,
        }
        if label_col:
            row_report["label"] = row.get(label_col)
        report_rows.append(row_report)

    return {
        "csv_rows": csv_rows,
        "fieldnames": output_fieldnames(fieldnames),
        "metric_rows": metric_rows,
        "report_rows": report_rows,
        "changed_row_count": sum(1 for row in metric_rows if row["changed"]),
    }


def utility_skip(reason: str, *, install_hint: str | None = None) -> dict[str, Any]:
    result = {"skipped": True, "reason": reason}
    if install_hint:
        result["install_hint"] = install_hint
    return result


def benchmark_available(label_col: str | None) -> tuple[bool, dict[str, Any] | None]:
    if not label_col:
        return (
            False,
            utility_skip(
                "No label column was provided; utility benchmark requires --label-col."
            ),
        )
    try:
        load_sklearn()
    except BenchmarkError as exc:
        return False, utility_skip(str(exc), install_hint=INSTALL_HINT)
    return True, None


def summarize_utility_benchmark(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "benchmark_type": result["benchmark_type"],
        "warning": result["warning"],
        "model": result["model"],
        "split": result["split"],
        "original": result["original"],
        "privatized": result["privatized"],
        "comparison": result["comparison"],
    }


def run_ablation(
    input_path: Path,
    *,
    text_col: str,
    id_col: str | None = None,
    label_col: str | None = None,
    output_path: Path | None = None,
    output_dir: Path | None = None,
    test_size: float = 0.25,
    random_state: int = 13,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        label_col=label_col,
    )

    can_benchmark, benchmark_skip = benchmark_available(label_col)
    temp_context = (
        tempfile.TemporaryDirectory(prefix="privhsd-ablation-")
        if can_benchmark and output_dir is None
        else None
    )
    temp_dir = Path(temp_context.name) if temp_context else None

    try:
        results: dict[str, Any] = {}
        for variant in ABLATION_VARIANTS:
            variant_run = run_variant(
                rows,
                fieldnames=fieldnames,
                text_col=text_col,
                id_col=id_col,
                label_col=label_col,
                variant=variant,
            )
            csv_path: Path | None = None
            if output_dir:
                csv_path = output_dir / f"{input_path.stem}.{variant.name}.csv"
                write_csv(csv_path, variant_run["csv_rows"], variant_run["fieldnames"])
            elif temp_dir:
                csv_path = temp_dir / f"{variant.name}.csv"
                write_csv(csv_path, variant_run["csv_rows"], variant_run["fieldnames"])

            variant_result: dict[str, Any] = {
                "name": variant.name,
                "description": variant.description,
                "config": variant_config_summary(variant),
                "metrics": aggregate_metrics(variant_run["metric_rows"]),
                "changed_row_count": variant_run["changed_row_count"],
                "rows": variant_run["report_rows"],
            }
            if output_dir and csv_path:
                variant_result["output_csv"] = str(csv_path)

            if can_benchmark and csv_path and label_col:
                try:
                    benchmark_result = run_utility_benchmark(
                        csv_path,
                        text_col=text_col,
                        privatized_col=PRIVATIZED_COL,
                        label_col=label_col,
                        id_col=id_col,
                        test_size=test_size,
                        random_state=random_state,
                    )
                except BenchmarkError as exc:
                    variant_result["utility_benchmark_skipped"] = utility_skip(str(exc))
                else:
                    variant_result["utility_benchmark"] = summarize_utility_benchmark(
                        benchmark_result
                    )

            results[variant.name] = variant_result

        report = {
            "input": str(input_path),
            "output": str(output_path) if output_path else None,
            "output_dir": str(output_dir) if output_dir else None,
            "columns": {
                "text_col": text_col,
                "id_col": id_col,
                "label_col": label_col,
                "privatized_col": PRIVATIZED_COL,
            },
            "warning": ABLATION_WARNING,
            "notes": [
                "The identity variant leaves text unchanged.",
                "The regex_only variant disables context detectors and target generalization.",
                "Optional utility benchmarks are local classifier deltas, not official scores.",
            ],
            "variants": [
                {
                    "name": variant.name,
                    "description": variant.description,
                    "config": variant_config_summary(variant),
                }
                for variant in ABLATION_VARIANTS
            ],
            "utility_benchmark": {
                "requested": label_col is not None,
                "available": can_benchmark,
                "test_size": test_size,
                "random_state": random_state,
            },
            "utility_benchmark_skipped": benchmark_skip,
            "results": results,
        }
        if output_path:
            write_json(output_path, report)
        return report
    finally:
        if temp_context:
            temp_context.cleanup()
