"""Deterministic high-confidence PII scrubbing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..io import CsvError, read_csv, sha256_file, write_csv
from ..results import StepResult


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    replacement: str


PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("[EMAIL]", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("[URL]", re.compile(r"\b(?:https?://|hxxps?://|www\.)[^\s<>()]+", re.I)),
    ("[USER]", re.compile(r"(?<!\w)@[A-Za-z0-9._-]{1,64}\b")),
    ("[PHONE]", re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{6,}\d)(?!\w)")),
    ("[IP_ADDRESS]", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    (
        "[CREDIT_CARD]",
        re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
    ),
    (
        "[ID]",
        re.compile(
            r"\b(?:id|case|ticket|student|user|ref)[-_:#]?"
            r"(?:[A-Z0-9]+[-_])*[A-Z0-9]*\d[A-Z0-9_-]*\b",
            re.I,
        ),
    ),
)


def _spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for replacement, pattern in PATTERNS:
        spans.extend(
            Span(m.start(), m.end(), replacement) for m in pattern.finditer(text)
        )
    spans.sort(key=lambda span: (span.start, -(span.end - span.start)))
    accepted: list[Span] = []
    cursor = -1
    for span in spans:
        if span.start < cursor:
            continue
        accepted.append(span)
        cursor = span.end
    return accepted


def scrub_text(text: str) -> tuple[str, int]:
    spans = _spans(text)
    if not spans:
        return text, 0
    parts: list[str] = []
    cursor = 0
    for span in spans:
        parts.append(text[cursor : span.start])
        parts.append(span.replacement)
        cursor = span.end
    parts.append(text[cursor:])
    return "".join(parts), len(spans)


def scrub_csv(
    input_csv: str | Path,
    output_csv: str | Path,
    *,
    text_col: str = "text",
) -> StepResult:
    rows, fieldnames = read_csv(input_csv)
    if text_col not in fieldnames:
        raise CsvError(f"missing text column {text_col!r}")
    changed_rows = 0
    replacement_count = 0
    output_rows: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        cleaned, count = scrub_text(str(row.get(text_col, "") or ""))
        out[text_col] = cleaned
        changed_rows += int(cleaned != row.get(text_col, ""))
        replacement_count += count
        output_rows.append(out)
    output_path = Path(output_csv)
    write_csv(output_path, output_rows, fieldnames)
    return StepResult(
        name="pii_scrub",
        status="complete",
        path=output_path,
        metadata={
            "row_count": len(output_rows),
            "changed_rows": changed_rows,
            "replacement_count": replacement_count,
            "sha256": sha256_file(output_path),
        },
    )
