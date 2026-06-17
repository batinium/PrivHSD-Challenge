"""Conservative author-group residual masking.

This module treats author/user columns as grouping keys only. It does not try to
rewrite author style; it only masks detector-backed factual spans that repeat
across multiple rows from the same author after row-level sanitization.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import re
from typing import Any

from .detectors import Span, detect_spans, merge_spans
from .pipeline import PrivatizerConfig, apply_replacements


AUTHOR_GROUP_ENTITY_TYPES = frozenset(
    {
        "AGE",
        "ALIAS",
        "DATE",
        "EMAIL",
        "LOCATION",
        "ORGANIZATION",
        "PERSON",
        "PHONE",
        "URL",
        "USER",
    }
)
PLACEHOLDER_ONLY_PATTERN = re.compile(r"^\s*\[[A-Z][A-Z0-9_:-]*\]\s*$")
NORMALIZE_PATTERN = re.compile(r"[^\w]+", re.UNICODE)
MIN_NORMALIZED_LENGTH = 3


@dataclass(frozen=True)
class AuthorGroupMaskingConfig:
    enabled: bool = True
    author_col: str | None = None
    min_repetitions: int = 2
    min_author_rows: int = 2
    metric_depth: str = "fast"


@dataclass(frozen=True)
class AuthorGroupMaskingResult:
    rows: list[dict[str, Any]]
    row_transformations: dict[int, list[dict[str, Any]]]
    summary: dict[str, Any]


def normalize_value(value: str) -> str:
    return NORMALIZE_PATTERN.sub("", value.casefold())


def eligible_span(span: Span, text: str) -> bool:
    if span.entity_type not in AUTHOR_GROUP_ENTITY_TYPES:
        return False
    value = text[span.start : span.end]
    if PLACEHOLDER_ONLY_PATTERN.match(value):
        return False
    normalized = normalize_value(value)
    if len(normalized) < MIN_NORMALIZED_LENGTH:
        return False
    return True


def candidate_spans(text: str) -> list[Span]:
    spans = [
        span
        for span in detect_spans(text, include_context=True, include_targets=False)
        if eligible_span(span, text)
    ]
    return merge_spans(spans)


def resolve_author_col(
    fieldnames: list[str],
    requested: str | None,
    *,
    known_names: set[str],
) -> str | None:
    if requested:
        return requested if requested in fieldnames else None
    for column in fieldnames:
        if column.strip().lower() in known_names:
            return column
    return None


def build_repeated_keys(
    rows: list[dict[str, Any]],
    *,
    text_col: str,
    author_col: str,
    min_repetitions: int,
    min_author_rows: int,
) -> tuple[set[tuple[str, str, str]], dict[str, Any], dict[int, list[Span]]]:
    author_counts = Counter(
        str(row.get(author_col, "") or "").strip()
        for row in rows
        if str(row.get(author_col, "") or "").strip()
    )
    key_rows: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    key_counts: Counter[tuple[str, str, str]] = Counter()
    candidates_by_row: dict[int, list[Span]] = {}
    authors_considered = {
        author
        for author, count in author_counts.items()
        if count >= min_author_rows
    }
    for row_index, row in enumerate(rows):
        author = str(row.get(author_col, "") or "").strip()
        if author not in authors_considered:
            continue
        text = str(row.get(text_col, "") or "")
        spans = candidate_spans(text)
        if spans:
            candidates_by_row[row_index] = spans
        seen_in_row: set[tuple[str, str, str]] = set()
        for span in spans:
            value = text[span.start : span.end]
            key = (author, span.entity_type, normalize_value(value))
            key_counts[key] += 1
            seen_in_row.add(key)
        for key in seen_in_row:
            key_rows[key].add(row_index)

    repeated = {
        key
        for key, count in key_counts.items()
        if count >= min_repetitions and len(key_rows[key]) >= min_repetitions
    }
    summary = {
        "authors_total": len(author_counts),
        "authors_considered": len(authors_considered),
        "candidate_value_count": len(key_counts),
        "repeated_value_count": len(repeated),
    }
    return repeated, summary, candidates_by_row


def row_group_spans(
    row: dict[str, Any],
    *,
    text_col: str,
    author_col: str,
    repeated_keys: set[tuple[str, str, str]],
    candidate_row_spans: list[Span] | None = None,
) -> list[Span]:
    author = str(row.get(author_col, "") or "").strip()
    if not author:
        return []
    text = str(row.get(text_col, "") or "")
    spans = []
    for span in candidate_row_spans if candidate_row_spans is not None else candidate_spans(text):
        value = text[span.start : span.end]
        key = (author, span.entity_type, normalize_value(value))
        if key in repeated_keys:
            spans.append(span)
    return merge_spans(spans)


def apply_author_group_masking(
    rows: list[dict[str, Any]],
    *,
    fieldnames: list[str],
    text_col: str,
    config: AuthorGroupMaskingConfig,
    known_author_names: set[str],
) -> AuthorGroupMaskingResult:
    output_rows = [dict(row) for row in rows]
    if not config.enabled:
        return AuthorGroupMaskingResult(
            rows=output_rows,
            row_transformations={},
            summary={"status": "disabled", "enabled": False},
        )
    author_col = resolve_author_col(
        fieldnames,
        config.author_col,
        known_names=known_author_names,
    )
    if author_col is None:
        return AuthorGroupMaskingResult(
            rows=output_rows,
            row_transformations={},
            summary={
                "status": "skipped",
                "enabled": True,
                "skipped_reason": "missing_author_column",
                "requested_author_col": config.author_col,
            },
        )
    repeated_keys, key_summary, candidates_by_row = build_repeated_keys(
        output_rows,
        text_col=text_col,
        author_col=author_col,
        min_repetitions=config.min_repetitions,
        min_author_rows=config.min_author_rows,
    )
    row_transformations: dict[int, list[dict[str, Any]]] = {}
    counts_by_entity_type: Counter[str] = Counter()
    candidate_rows = 0
    for index, row in enumerate(output_rows):
        spans = row_group_spans(
            row,
            text_col=text_col,
            author_col=author_col,
            repeated_keys=repeated_keys,
            candidate_row_spans=candidates_by_row.get(index),
        )
        if not spans:
            continue
        candidate_rows += 1
        current = str(row.get(text_col, "") or "")
        masked, transformations = apply_replacements(
            current,
            spans,
            PrivatizerConfig(mode="balanced", generalize_targets=False),
        )
        if masked == current:
            continue
        output_rows[index][text_col] = masked
        materialized = [dict(item) for item in transformations]
        row_transformations[index] = materialized
        counts_by_entity_type.update(
            str(item.get("entity_type", "UNKNOWN")) for item in materialized
        )

    summary = {
        "status": "ok",
        "enabled": True,
        "author_col": author_col,
        "min_repetitions": config.min_repetitions,
        "min_author_rows": config.min_author_rows,
        "candidate_rows": candidate_rows,
        "changed_rows": len(row_transformations),
        "transformation_count": sum(len(items) for items in row_transformations.values()),
        "counts_by_entity_type": dict(sorted(counts_by_entity_type.items())),
        "meaning_protection": (
            "uses detector-backed non-target span eligibility; final row metrics "
            "verify target and utility cue retention after group masking"
        ),
        **key_summary,
    }
    return AuthorGroupMaskingResult(
        rows=output_rows,
        row_transformations=row_transformations,
        summary=summary,
    )
