"""Safe aggregate profiling for incoming CSV datasets."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from pathlib import Path
from statistics import mean
from typing import Any

from .csv_pipeline import write_json


class DatasetProfileError(ValueError):
    pass


TEXT_NAME_HINTS = ("text", "comment", "content", "message", "tweet", "post", "body")
ID_NAME_HINTS = ("id", "case", "entry", "example", "source_id")
LABEL_NAME_HINTS = ("label", "class", "hate", "abuse", "toxic", "gold")
AUTHOR_NAME_HINTS = (
    "author",
    "user",
    "username",
    "account",
    "handle",
    "screen_name",
    "worker",
    "annotator",
)
CATEGORICAL_HINTS = (
    "label",
    "source",
    "split",
    "set",
    "target",
    "type",
    "platform",
    "severity",
    "category",
)


def lowered_map(fieldnames: list[str]) -> dict[str, str]:
    return {field.lower(): field for field in fieldnames}


def pick_existing(
    fieldnames: list[str],
    explicit: str | None,
    candidates: tuple[str, ...],
) -> str | None:
    if explicit:
        if explicit not in fieldnames:
            raise DatasetProfileError(f"missing requested column {explicit!r}")
        return explicit
    by_lower = lowered_map(fieldnames)
    for candidate in candidates:
        if candidate in by_lower:
            return by_lower[candidate]
    for field in fieldnames:
        lowered = field.lower()
        if any(hint in lowered for hint in candidates):
            return field
    return None


def hinted_columns(fieldnames: list[str], hints: tuple[str, ...]) -> list[str]:
    return [
        field
        for field in fieldnames
        if any(hint in field.lower() for hint in hints)
    ]


def quantiles(values: list[int]) -> dict[str, float | int]:
    if not values:
        return {}
    data = sorted(values)

    def q(percentile: float) -> int:
        index = round((len(data) - 1) * percentile)
        return data[index]

    return {
        "min": data[0],
        "p25": q(0.25),
        "p50": q(0.50),
        "p75": q(0.75),
        "p90": q(0.90),
        "p95": q(0.95),
        "p99": q(0.99),
        "max": data[-1],
        "mean": round(mean(data), 2),
    }


def top_values(counter: Counter[str], top_k: int) -> list[dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in counter.most_common(top_k)
    ]


def duplicate_summary(counter: Counter[str]) -> dict[str, int]:
    duplicate_groups = sum(1 for value, count in counter.items() if value and count > 1)
    duplicate_rows = sum(count for value, count in counter.items() if value and count > 1)
    max_rows_per_value = max(counter.values(), default=0)
    return {
        "unique_nonblank": sum(1 for value in counter if value),
        "blank_rows": counter.get("", 0),
        "duplicate_groups": duplicate_groups,
        "duplicate_rows": duplicate_rows,
        "max_rows_per_value": max_rows_per_value,
    }


def profile_dataset(
    input_path: Path,
    *,
    output_path: Path | None = None,
    text_col: str | None = None,
    id_col: str | None = None,
    label_col: str | None = None,
    source_col: str | None = None,
    split_col: str | None = None,
    top_k: int = 20,
) -> dict[str, Any]:
    if top_k < 1:
        raise DatasetProfileError("--top-k must be at least 1")
    try:
        csv.field_size_limit(10_000_000)
    except OverflowError:  # pragma: no cover - platform dependent
        pass
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise DatasetProfileError(f"{input_path}: CSV header is required")
        fieldnames = list(reader.fieldnames)
        detected_text_col = pick_existing(fieldnames, text_col, TEXT_NAME_HINTS)
        detected_id_col = pick_existing(fieldnames, id_col, ("id", "source_id", "case_id"))
        detected_label_col = pick_existing(fieldnames, label_col, LABEL_NAME_HINTS)
        detected_source_col = pick_existing(fieldnames, source_col, ("source", "dataset"))
        detected_split_col = pick_existing(fieldnames, split_col, ("split", "set"))

        categorical_columns = sorted(
            {
                column
                for column in hinted_columns(fieldnames, CATEGORICAL_HINTS)
                if column != detected_text_col
            }
        )
        author_candidate_columns = sorted(
            {
                column
                for column in hinted_columns(fieldnames, AUTHOR_NAME_HINTS)
                if column != detected_text_col
            }
        )
        id_candidate_columns = sorted(
            {
                column
                for column in hinted_columns(fieldnames, ID_NAME_HINTS)
                if column != detected_text_col
            }
        )

        rows = 0
        missing_counts: Counter[str] = Counter()
        unique_values: dict[str, set[str]] = {field: set() for field in fieldnames}
        categorical_counts: dict[str, Counter[str]] = {
            column: Counter() for column in categorical_columns
        }
        candidate_value_counts: dict[str, Counter[str]] = {
            column: Counter()
            for column in sorted(set(author_candidate_columns + id_candidate_columns))
        }
        candidate_value_counts_by_source: dict[str, dict[str, Counter[str]]] = {
            column: defaultdict(Counter)
            for column in sorted(set(author_candidate_columns + id_candidate_columns))
        }
        id_counts: Counter[str] = Counter()
        normalized_text_counts: Counter[str] = Counter()
        text_lengths: list[int] = []

        for row in reader:
            rows += 1
            for field in fieldnames:
                value = str(row.get(field, "") or "")
                if value == "":
                    missing_counts[field] += 1
                else:
                    unique_values[field].add(value)
                if field in categorical_counts:
                    categorical_counts[field][value or "<blank>"] += 1
                if field in candidate_value_counts:
                    candidate_value_counts[field][value] += 1
                    if detected_source_col:
                        source_value = str(row.get(detected_source_col, "") or "<blank>")
                        candidate_value_counts_by_source[field][source_value][value] += 1
            if detected_id_col:
                id_counts[str(row.get(detected_id_col, "") or "")] += 1
            if detected_text_col:
                text = str(row.get(detected_text_col, "") or "")
                text_lengths.append(len(text))
                normalized_text_counts[text.strip().lower()] += 1

    columns = [
        {
            "name": field,
            "missing_count": missing_counts[field],
            "missing_rate": round(missing_counts[field] / rows, 4) if rows else 0.0,
            "unique_nonblank": len(unique_values[field]),
        }
        for field in fieldnames
    ]
    result: dict[str, Any] = {
        "artifact_type": "dataset_profile",
        "input": str(input_path),
        "row_count": rows,
        "columns": columns,
        "fieldnames": fieldnames,
        "detected_columns": {
            "text_col": detected_text_col,
            "id_col": detected_id_col,
            "label_col": detected_label_col,
            "source_col": detected_source_col,
            "split_col": detected_split_col,
        },
        "candidate_columns": {
            "text": hinted_columns(fieldnames, TEXT_NAME_HINTS),
            "id": id_candidate_columns,
            "label": hinted_columns(fieldnames, LABEL_NAME_HINTS),
            "author_or_annotator": author_candidate_columns,
        },
        "top_values": {
            column: top_values(counter, top_k)
            for column, counter in sorted(categorical_counts.items())
        },
        "author_or_id_candidate_stats": {
            column: duplicate_summary(counter)
            for column, counter in sorted(candidate_value_counts.items())
        },
        "author_or_id_candidate_stats_by_source": {
            column: {
                source: duplicate_summary(counter)
                for source, counter in sorted(source_counters.items())
            }
            for column, source_counters in sorted(candidate_value_counts_by_source.items())
        },
        "text_profile": {
            "enabled": detected_text_col is not None,
            "column": detected_text_col,
            "length": quantiles(text_lengths),
            "blank_text_rows": normalized_text_counts.get("", 0),
            "duplicate_normalized_text": duplicate_summary(normalized_text_counts),
        },
        "id_profile": {
            "enabled": detected_id_col is not None,
            "column": detected_id_col,
            **duplicate_summary(id_counts),
        },
        "notes": [
            "Aggregate profile only; raw text examples are intentionally omitted.",
            "Repeated author/user candidate columns may support author-risk evaluation.",
            "Unique ID-like columns are not author labels.",
            "Treat labels as source-aware unless a mapping policy is documented.",
        ],
    }
    if output_path:
        write_json(output_path, result)
    return result
