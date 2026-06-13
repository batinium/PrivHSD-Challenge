"""Raw-text-free auto pipeline audit helpers."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


def status_summary(statuses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(status.get("status", "unknown")) for status in statuses.values())
    return {
        "counts_by_status": dict(sorted(counts.items())),
        "items": statuses,
    }


def row_audit_limit(rows: Iterable[dict[str, Any]], *, audit_level: str) -> list[dict[str, Any]]:
    materialized = list(rows)
    if audit_level == "summary":
        return materialized[:100]
    if audit_level == "row":
        return materialized
    return materialized
