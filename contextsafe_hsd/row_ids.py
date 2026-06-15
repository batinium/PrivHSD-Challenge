"""Privacy-safe row identifiers for local reports."""

from __future__ import annotations

from collections import Counter
import hashlib
from typing import Any


SENSITIVE_ID_TOKENS = frozenset(
    {
        "account",
        "annotator",
        "author",
        "handle",
        "screen_name",
        "user",
        "username",
        "worker",
    }
)


def _column_parts(column: str | None) -> set[str]:
    normalized = str(column or "").strip().lower()
    return {part for part in normalized.replace("-", "_").split("_") if part}


def is_sensitive_identifier_column(column: str | None) -> bool:
    return bool(_column_parts(column) & SENSITIVE_ID_TOKENS)


def report_row_id(
    row: dict[str, Any],
    *,
    row_index: int,
    id_col: str | None = None,
) -> str:
    """Return a row reference suitable for raw-text-free sidecar reports."""

    if id_col and not is_sensitive_identifier_column(id_col):
        value = str(row.get(id_col, "") or "").strip()
        if value:
            return value
    return str(row_index)


def value_hash(value: str, *, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def safe_value_summary(value: Any) -> dict[str, Any]:
    text = str(value or "")
    return {
        "value_hash": value_hash(text),
        "value_length": len(text),
        "blank": text == "",
    }


def safe_label(value: Any, *, prefix: str) -> str:
    text = str(value or "")
    return f"{prefix}_{value_hash(text)}"


def safe_label_counts(values: list[str], *, prefix: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for value in values:
        counts[safe_label(value, prefix=prefix)] += 1
    return dict(sorted(counts.items()))
