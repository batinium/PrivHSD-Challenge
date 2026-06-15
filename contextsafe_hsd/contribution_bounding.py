"""User-level contribution bounding for repeated-author text datasets."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import random
from statistics import mean
from typing import Any

from .csv_pipeline import read_csv, write_csv, write_json
from .row_ids import report_row_id


BOUNDING_STRATEGIES = {
    "first",
    "last",
    "longest",
    "random",
    "shortest",
    "stratified",
}


class ContributionBoundingError(ValueError):
    pass


def quantiles(values: list[int]) -> dict[str, int | float]:
    if not values:
        return {}
    sorted_values = sorted(values)

    def q(percentile: float) -> int:
        index = round((len(sorted_values) - 1) * percentile)
        return sorted_values[index]

    return {
        "min": sorted_values[0],
        "p25": q(0.25),
        "p50": q(0.50),
        "p75": q(0.75),
        "p90": q(0.90),
        "p95": q(0.95),
        "p99": q(0.99),
        "max": sorted_values[-1],
        "mean": round(mean(sorted_values), 2),
    }


def validate_columns(
    fieldnames: list[str],
    *,
    author_col: str,
    id_col: str | None,
    text_col: str | None,
    stratify_cols: tuple[str, ...],
    strategy: str,
) -> None:
    missing = [column for column in (author_col, id_col, text_col) if column]
    missing.extend(stratify_cols)
    missing = [column for column in missing if column not in fieldnames]
    if missing:
        raise ContributionBoundingError(
            f"missing required column(s): {', '.join(sorted(set(missing)))}"
        )
    if strategy not in BOUNDING_STRATEGIES:
        raise ContributionBoundingError(
            f"strategy must be one of {sorted(BOUNDING_STRATEGIES)}"
        )
    if strategy in {"longest", "shortest"} and not text_col:
        raise ContributionBoundingError(
            f"--text-col is required for {strategy!r} strategy"
        )


def stratified_allocations(
    buckets: dict[tuple[str, ...], list[int]],
    max_records: int,
) -> dict[tuple[str, ...], int]:
    allocations = {key: 0 for key in buckets}
    remaining = max_records
    if max_records >= len(buckets):
        for key in sorted(buckets):
            allocations[key] = 1
            remaining -= 1

    total = sum(len(bucket) for bucket in buckets.values())
    while remaining > 0:
        candidates: list[tuple[float, int, tuple[str, ...]]] = []
        for key, bucket in buckets.items():
            capacity = len(bucket) - allocations[key]
            if capacity <= 0:
                continue
            exact = max_records * (len(bucket) / total)
            remainder = exact - allocations[key]
            candidates.append((remainder, len(bucket), key))
        if not candidates:
            break
        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        for _remainder, _size, key in candidates:
            if remaining <= 0:
                break
            if allocations[key] < len(buckets[key]):
                allocations[key] += 1
                remaining -= 1
    return allocations


def stratified_sample(
    rows: list[dict[str, str]],
    indices: list[int],
    *,
    max_records: int,
    stratify_cols: tuple[str, ...],
    rng: random.Random,
) -> set[int]:
    bucket_cols = stratify_cols or ("__all__",)
    buckets: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index in indices:
        if stratify_cols:
            key = tuple(
                str(rows[index].get(column, "") or "")
                for column in stratify_cols
            )
        else:
            key = bucket_cols
        buckets[key].append(index)
    allocations = stratified_allocations(dict(buckets), max_records)
    selected: set[int] = set()
    for key in sorted(buckets):
        bucket = buckets[key]
        allocation = allocations[key]
        if allocation >= len(bucket):
            selected.update(bucket)
        elif allocation > 0:
            selected.update(rng.sample(bucket, allocation))
    return selected


def select_author_indices(
    rows: list[dict[str, str]],
    indices: list[int],
    *,
    max_records: int,
    strategy: str,
    text_col: str | None,
    stratify_cols: tuple[str, ...],
    rng: random.Random,
) -> set[int]:
    if len(indices) <= max_records:
        return set(indices)
    if strategy == "first":
        return set(indices[:max_records])
    if strategy == "last":
        return set(indices[-max_records:])
    if strategy == "longest":
        return set(
            sorted(
                indices,
                key=lambda index: (
                    -len(str(rows[index].get(text_col or "", "") or "")),
                    index,
                ),
            )[:max_records]
        )
    if strategy == "shortest":
        return set(
            sorted(
                indices,
                key=lambda index: (
                    len(str(rows[index].get(text_col or "", "") or "")),
                    index,
                ),
            )[:max_records]
        )
    if strategy == "stratified" or stratify_cols:
        return stratified_sample(
            rows,
            indices,
            max_records=max_records,
            stratify_cols=stratify_cols,
            rng=rng,
        )
    return set(rng.sample(indices, max_records))


def author_count_summary(groups: dict[str, list[int]]) -> dict[str, Any]:
    values = [len(indices) for indices in groups.values()]
    over_one = sum(1 for value in values if value > 1)
    return {
        "author_count": len(values),
        "authors_with_multiple_rows": over_one,
        "row_count_distribution": quantiles(values),
    }


def bound_contributions(
    input_path: Path,
    output_path: Path,
    *,
    author_col: str,
    max_records_per_author: int,
    id_col: str | None = None,
    text_col: str | None = None,
    report_path: Path | None = None,
    strategy: str = "random",
    stratify_cols: list[str] | None = None,
    random_state: int = 13,
    drop_missing_author: bool = False,
) -> dict[str, Any]:
    if max_records_per_author < 1:
        raise ContributionBoundingError("--max-records-per-author must be at least 1")
    rows, fieldnames = read_csv(input_path)
    stratify_tuple = tuple(stratify_cols or ())
    validate_columns(
        fieldnames,
        author_col=author_col,
        id_col=id_col,
        text_col=text_col,
        stratify_cols=stratify_tuple,
        strategy=strategy,
    )

    groups: dict[str, list[int]] = defaultdict(list)
    missing_author_indices: list[int] = []
    for index, row in enumerate(rows):
        author = str(row.get(author_col, "") or "")
        if author:
            groups[author].append(index)
        else:
            missing_author_indices.append(index)

    rng = random.Random(random_state)
    kept_indices: set[int] = set()
    dropped_by_author_count = 0
    dropped_author_rows = 0
    after_counts: Counter[str] = Counter()
    for author, indices in groups.items():
        selected = select_author_indices(
            rows,
            indices,
            max_records=max_records_per_author,
            strategy=strategy,
            text_col=text_col,
            stratify_cols=stratify_tuple,
            rng=rng,
        )
        kept_indices.update(selected)
        after_counts[author] = len(selected)
        dropped = len(indices) - len(selected)
        if dropped:
            dropped_by_author_count += 1
            dropped_author_rows += dropped

    if not drop_missing_author:
        kept_indices.update(missing_author_indices)

    output_rows = [dict(row) for index, row in enumerate(rows) if index in kept_indices]
    write_csv(output_path, output_rows, fieldnames)

    dropped_indices = [index for index in range(len(rows)) if index not in kept_indices]
    report = {
        "artifact_type": "contribution_bounding_report",
        "status": "ok" if dropped_indices else "ok_no_rows_dropped",
        "input": str(input_path),
        "output": str(output_path),
        "privacy_note": (
            "Contribution bounding limits repeated nonblank author groups before "
            "release or training. It does not by itself provide differential privacy, "
            "and row-dropping outputs are not exact-format challenge submissions."
        ),
        "columns": {
            "author_col": author_col,
            "id_col": id_col,
            "text_col": text_col,
            "stratify_cols": list(stratify_tuple),
        },
        "selection": {
            "max_records_per_author": max_records_per_author,
            "strategy": strategy,
            "random_state": random_state,
            "drop_missing_author": drop_missing_author,
        },
        "row_counts": {
            "before": len(rows),
            "after": len(output_rows),
            "dropped": len(dropped_indices),
            "dropped_from_bounded_authors": dropped_author_rows,
            "dropped_missing_author": (
                len(missing_author_indices) if drop_missing_author else 0
            ),
            "missing_author_rows": len(missing_author_indices),
            "unbounded_missing_author_rows": (
                0 if drop_missing_author else len(missing_author_indices)
            ),
        },
        "author_groups": {
            "before": author_count_summary(dict(groups)),
            "after": {
                "author_count": len(after_counts),
                "authors_with_multiple_rows": sum(
                    1 for value in after_counts.values() if value > 1
                ),
                "authors_over_limit_before": dropped_by_author_count,
                "row_count_distribution": quantiles(list(after_counts.values())),
                "max_rows_per_author_after": max(after_counts.values(), default=0),
            },
        },
    }
    if id_col:
        report["dropped_row_examples"] = [
            {
                "row_index": index + 1,
                "row_id": report_row_id(
                    rows[index],
                    row_index=index + 1,
                    id_col=id_col,
                ),
            }
            for index in dropped_indices[:50]
        ]
    if report_path:
        write_json(report_path, report)
    return report
