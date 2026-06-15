"""Metadata value leakage checks for text columns."""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import re
from typing import Any

from .csv_pipeline import read_csv, write_json
from .row_ids import report_row_id


DEFAULT_METADATA_COLUMNS = ("id", "author")
DEFAULT_MIN_VALUE_LENGTH = 3


class MetadataLeakageError(ValueError):
    pass


def rounded(value: float) -> float:
    return round(float(value), 4)


def normalize_value(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def value_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def contains_value(text: str, value: str) -> bool:
    if not value:
        return False
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])"
    return bool(re.search(pattern, text, re.I))


def contains_normalized_value(text: str, value: str) -> bool:
    normalized_value = normalize_value(value)
    if not normalized_value:
        return False
    return normalized_value in normalize_value(text)


def validate_columns(
    input_path: Path,
    fieldnames: list[str],
    *,
    text_cols: list[str],
    metadata_cols: list[str],
    id_col: str | None,
) -> None:
    missing = [*text_cols, *metadata_cols]
    if id_col:
        missing.append(id_col)
    missing = [column for column in missing if column not in fieldnames]
    if missing:
        raise MetadataLeakageError(
            f"{input_path}: missing required column(s): {', '.join(sorted(set(missing)))}"
        )


def choose_metadata_columns(fieldnames: list[str], requested: list[str] | None) -> list[str]:
    if requested:
        return requested
    return [column for column in DEFAULT_METADATA_COLUMNS if column in fieldnames]


def scan_metadata_leakage(
    input_path: Path,
    *,
    text_cols: list[str],
    metadata_cols: list[str] | None = None,
    id_col: str | None = None,
    output_path: Path | None = None,
    min_value_length: int = DEFAULT_MIN_VALUE_LENGTH,
    normalized: bool = True,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    metadata_cols = choose_metadata_columns(fieldnames, metadata_cols)
    if not metadata_cols:
        raise MetadataLeakageError(
            "no metadata columns requested or found; use --metadata-col"
        )
    if min_value_length < 1:
        raise MetadataLeakageError("--min-value-length must be positive")
    validate_columns(
        input_path,
        fieldnames,
        text_cols=text_cols,
        metadata_cols=metadata_cols,
        id_col=id_col,
    )

    leaks: list[dict[str, Any]] = []
    counts: Counter[tuple[str, str, str]] = Counter()
    eligible_values: Counter[str] = Counter()
    skipped_short_values: Counter[str] = Counter()
    for row_index, row in enumerate(rows, start=1):
        row_id = report_row_id(row, row_index=row_index, id_col=id_col)
        for metadata_col in metadata_cols:
            value = str(row.get(metadata_col, "") or "").strip()
            if len(value) < min_value_length:
                if value:
                    skipped_short_values[metadata_col] += 1
                continue
            eligible_values[metadata_col] += 1
            for text_col in text_cols:
                text = str(row.get(text_col, "") or "")
                exact = contains_value(text, value)
                normalized_hit = normalized and contains_normalized_value(text, value)
                if not exact and not normalized_hit:
                    continue
                leak_type = "exact" if exact else "normalized"
                counts[(metadata_col, text_col, leak_type)] += 1
                leaks.append(
                    {
                        "row_index": row_index,
                        "row_id": row_id,
                        "metadata_col": metadata_col,
                        "text_col": text_col,
                        "leak_type": leak_type,
                        "value_length": len(value),
                        "value_hash": value_hash(value),
                    }
                )

    by_metadata_col: dict[str, Any] = {}
    for metadata_col in metadata_cols:
        metadata_summary: dict[str, Any] = {
            "eligible_value_count": eligible_values.get(metadata_col, 0),
            "skipped_short_value_count": skipped_short_values.get(metadata_col, 0),
            "leak_count": 0,
            "text_columns": {},
        }
        for text_col in text_cols:
            exact_count = counts.get((metadata_col, text_col, "exact"), 0)
            normalized_count = counts.get((metadata_col, text_col, "normalized"), 0)
            leak_count = exact_count + normalized_count
            metadata_summary["leak_count"] += leak_count
            metadata_summary["text_columns"][text_col] = {
                "exact": exact_count,
                "normalized": normalized_count,
                "total": leak_count,
            }
        denominator = max(eligible_values.get(metadata_col, 0) * len(text_cols), 1)
        metadata_summary["leak_rate"] = rounded(
            metadata_summary["leak_count"] / denominator
        )
        by_metadata_col[metadata_col] = metadata_summary

    result = {
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "check_type": "metadata_value_leakage",
        "status": "ok",
        "columns": {
            "text_cols": text_cols,
            "metadata_cols": metadata_cols,
            "id_col": id_col,
        },
        "policy": {
            "min_value_length": min_value_length,
            "normalized_matching": normalized,
            "raw_metadata_values_in_report": False,
        },
        "row_count": len(rows),
        "leak_count": len(leaks),
        "leak_rows": len({(item["row_index"], item["text_col"]) for item in leaks}),
        "by_metadata_col": by_metadata_col,
        "examples": leaks[:100],
    }
    if output_path:
        write_json(output_path, result)
    return result
