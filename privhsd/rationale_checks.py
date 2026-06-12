"""Source-aware rationale/span preservation checks."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
import ast
import json
import re
from statistics import mean
from typing import Any

from .metrics import PLACEHOLDER_PATTERN


TOKEN_PATTERN = re.compile(r"\S+")


@dataclass(frozen=True)
class RationaleSpan:
    start: int
    end: int
    source_kind: str


def rounded(value: float) -> float:
    return round(float(value), 4)


def normalize_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def parse_span_value(raw_value: str) -> Any:
    value = (raw_value or "").strip()
    if not value:
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(value)
        except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
            continue
    numbers = [int(match.group(0)) for match in re.finditer(r"-?\d+", value)]
    return numbers or None


def token_offsets(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in TOKEN_PATTERN.finditer(text)]


def coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value)
    return None


def flatten_ints(value: Any) -> list[int]:
    number = coerce_int(value)
    if number is not None:
        return [number]
    if isinstance(value, (list, tuple)):
        result: list[int] = []
        for item in value:
            result.extend(flatten_ints(item))
        return result
    return []


def pair_like(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    start = coerce_int(value[0])
    end = coerce_int(value[1])
    if start is None or end is None:
        return None
    return start, end


def runs_from_offsets(offsets: list[int]) -> list[tuple[int, int]]:
    if not offsets:
        return []
    sorted_offsets = sorted(set(offset for offset in offsets if offset >= 0))
    if not sorted_offsets:
        return []
    runs: list[tuple[int, int]] = []
    start = previous = sorted_offsets[0]
    for offset in sorted_offsets[1:]:
        if offset == previous + 1:
            previous = offset
            continue
        runs.append((start, previous + 1))
        start = previous = offset
    runs.append((start, previous + 1))
    return runs


def hatexplain_spans(parsed: Any, text: str) -> list[RationaleSpan]:
    offsets = token_offsets(text)
    if not offsets:
        return []

    index_ranges: list[tuple[int, int]] = []
    if isinstance(parsed, (list, tuple)):
        if all(coerce_int(item) is not None for item in parsed):
            values = [int(coerce_int(item) or 0) for item in parsed]
            if len(values) == len(offsets) and set(values) <= {0, 1}:
                index_ranges.extend((index, index + 1) for index, flag in enumerate(values) if flag)
            else:
                index_ranges.extend((index, index + 1) for index in values)
        else:
            for item in parsed:
                pair = pair_like(item)
                if pair is not None:
                    start, end = pair
                    if end <= start:
                        end = start + 1
                    index_ranges.append((start, end))
                else:
                    index_ranges.extend((index, index + 1) for index in flatten_ints(item))
    else:
        index_ranges.extend((index, index + 1) for index in flatten_ints(parsed))

    spans: list[RationaleSpan] = []
    for token_start, token_end in index_ranges:
        if token_start < 0 or token_start >= len(offsets):
            continue
        token_end = max(token_start + 1, min(token_end, len(offsets)))
        char_start = offsets[token_start][0]
        char_end = offsets[token_end - 1][1]
        spans.append(RationaleSpan(char_start, char_end, "token_index_range"))
    return merge_rationale_spans(spans)


def toxic_spans(parsed: Any, text: str) -> list[RationaleSpan]:
    ranges: list[tuple[int, int]] = []
    if isinstance(parsed, (list, tuple)):
        for item in parsed:
            pair = pair_like(item)
            if pair is not None:
                start, end = pair
                if end <= start:
                    end = start + 1
                ranges.append((start, end))
            else:
                values = flatten_ints(item)
                if values:
                    ranges.extend(runs_from_offsets(values))
    else:
        ranges.extend(runs_from_offsets(flatten_ints(parsed)))

    spans: list[RationaleSpan] = []
    for start, end in ranges:
        start = max(0, min(start, len(text)))
        end = max(start, min(end, len(text)))
        if end > start:
            spans.append(RationaleSpan(start, end, "char_offset_range"))
    return merge_rationale_spans(spans)


def merge_rationale_spans(spans: list[RationaleSpan]) -> list[RationaleSpan]:
    if not spans:
        return []
    ordered = sorted(spans, key=lambda span: (span.start, span.end))
    merged: list[RationaleSpan] = [ordered[0]]
    for span in ordered[1:]:
        previous = merged[-1]
        if span.start <= previous.end and span.source_kind == previous.source_kind:
            merged[-1] = RationaleSpan(
                previous.start,
                max(previous.end, span.end),
                previous.source_kind,
            )
        else:
            merged.append(span)
    return merged


def parse_rationale_spans(
    *,
    source: str,
    raw_value: str,
    text: str,
) -> list[RationaleSpan]:
    parsed = parse_span_value(raw_value)
    if parsed is None:
        return []
    source_name = (source or "").strip().lower()
    if source_name == "hatexplain":
        return hatexplain_spans(parsed, text)
    if source_name == "toxic_spans":
        return toxic_spans(parsed, text)
    return []


def changed_ranges(
    original: str,
    protected: str,
) -> list[tuple[int, int, bool]]:
    ranges: list[tuple[int, int, bool]] = []
    matcher = SequenceMatcher(None, original, protected, autojunk=False)
    for tag, original_start, original_end, protected_start, protected_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        replacement = protected[protected_start:protected_end]
        ranges.append(
            (
                original_start,
                original_end,
                bool(PLACEHOLDER_PATTERN.search(replacement)),
            )
        )
    return ranges


def overlaps(left_start: int, left_end: int, right_start: int, right_end: int) -> bool:
    return left_start < right_end and left_end > right_start


def rationale_row_report(
    *,
    row_index: int,
    row_id: str,
    source: str,
    label: str | None,
    original: str,
    protected: str,
    raw_spans: str,
) -> dict[str, Any]:
    spans = parse_rationale_spans(source=source, raw_value=raw_spans, text=original)
    if not spans:
        return {
            "row_index": row_index,
            "row_id": row_id,
            "source": source,
            "label": label,
            "has_rationale": False,
            "span_count": 0,
            "overlap_changed_count": 0,
            "overlap_placeholder_count": 0,
            "preserved_span_count": 0,
            "rationale_span_retention": 1.0,
            "source_kind_counts": {},
        }
    changed = changed_ranges(original, protected)
    overlap_changed = 0
    overlap_placeholder = 0
    preserved = 0
    protected_norm = normalize_text(protected)
    for span in spans:
        if any(overlaps(span.start, span.end, start, end) for start, end, _ in changed):
            overlap_changed += 1
        if any(
            is_placeholder and overlaps(span.start, span.end, start, end)
            for start, end, is_placeholder in changed
        ):
            overlap_placeholder += 1
        span_norm = normalize_text(original[span.start : span.end])
        if not span_norm or span_norm in protected_norm:
            preserved += 1
    retention = preserved / len(spans) if spans else 1.0
    return {
        "row_index": row_index,
        "row_id": row_id,
        "source": source,
        "label": label,
        "has_rationale": bool(spans),
        "span_count": len(spans),
        "overlap_changed_count": overlap_changed,
        "overlap_placeholder_count": overlap_placeholder,
        "preserved_span_count": preserved,
        "rationale_span_retention": rounded(retention),
        "source_kind_counts": dict(sorted(Counter(span.source_kind for span in spans).items())),
    }


def aggregate_rationale_reports(
    row_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    if not row_reports:
        return {
            "rows_with_rationale": 0,
            "rationale_span_count": 0,
            "overlap_changed_count": 0,
            "overlap_placeholder_count": 0,
            "preserved_span_count": 0,
            "rationale_span_retention_mean": 1.0,
            "source_kind_counts": {},
        }
    with_rationale = [row for row in row_reports if row.get("has_rationale")]
    span_count = sum(row.get("span_count", 0) for row in row_reports)
    preserved = sum(row.get("preserved_span_count", 0) for row in row_reports)
    source_kind_counts: Counter[str] = Counter()
    for row in row_reports:
        source_kind_counts.update(row.get("source_kind_counts", {}))
    return {
        "rows_with_rationale": len(with_rationale),
        "rationale_span_count": span_count,
        "overlap_changed_count": sum(
            row.get("overlap_changed_count", 0) for row in row_reports
        ),
        "overlap_placeholder_count": sum(
            row.get("overlap_placeholder_count", 0) for row in row_reports
        ),
        "preserved_span_count": preserved,
        "rationale_span_retention": rounded(preserved / span_count) if span_count else 1.0,
        "rationale_span_retention_mean": (
            rounded(mean(row["rationale_span_retention"] for row in with_rationale))
            if with_rationale
            else 1.0
        ),
        "source_kind_counts": dict(sorted(source_kind_counts.items())),
    }
