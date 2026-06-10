"""Deterministic span detectors for privacy-sensitive text.

The challenge needs a reliable baseline that runs locally and is explainable.
These detectors intentionally focus on direct identifiers and conservative
quasi-identifiers. Target-group detection is separated so it can be enabled only
when a run explicitly wants group-category generalization.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    entity_type: str
    text: str
    score: float
    source: str
    category: str | None = None

    def replacement_tag(self) -> str:
        if self.entity_type == "TARGET_GROUP" and self.category:
            return f"[TARGET_GROUP:{self.category}]"
        return TAGS.get(self.entity_type, "[IDENTIFIER]")


TAGS = {
    "PERSON": "[PERSON]",
    "ALIAS": "[ALIAS]",
    "USER": "[USER]",
    "EMAIL": "[EMAIL]",
    "PHONE": "[PHONE]",
    "URL": "[URL]",
    "IP_ADDRESS": "[ID]",
    "DATE": "[DATE]",
    "LOCATION": "[LOCATION]",
    "ORGANIZATION": "[ORG]",
    "IDENTIFIER": "[ID]",
    "AGE": "[AGE]",
}


REGEX_PATTERNS: Sequence[tuple[str, re.Pattern[str]]] = (
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("URL", re.compile(r"\b(?:https?://|www\.)[^\s<>()]+", re.I)),
    ("USER", re.compile(r"(?<!\w)@[A-Za-z0-9._-]{2,64}\b")),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    (
        "PHONE",
        re.compile(
            r"(?<!\w)(?:\+?\d[\d\s().-]{6,}\d)(?:\s*(?:ext|x)\s*\d{1,6})?(?!\w)",
            re.I,
        ),
    ),
    (
        "DATE",
        re.compile(
            r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
            r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
            r"[a-z]*\s+\d{1,2},?\s+\d{2,4})\b",
            re.I,
        ),
    ),
    ("AGE", re.compile(r"\b(?:I am|I'm|aged?)\s+(\d{1,2})(?:\s+years?\s+old)?\b", re.I)),
    ("AGE", re.compile(r"\b\d{1,2}[- ]year[- ]old\b", re.I)),
    (
        "IDENTIFIER",
        re.compile(
            r"\b(?:id|case|ticket|student|user|ref)[-_:#]?"
            r"(?:[A-Z0-9]+[-_])*[A-Z0-9]*\d[A-Z0-9_-]*\b",
            re.I,
        ),
    ),
    (
        "ORGANIZATION",
        re.compile(
            r"\b[A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,5}\s+"
            r"(?:University|College|Institute|Academy|School|Centre|Center)\b"
        ),
    ),
)


PERSON_CONTEXT_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(
        r"\b(?i:my name is|i am|i'm|this is|call me)\s+"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b"
    ),
    re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s+"
        r"(?:said|emailed|called|posted|replied|wrote)\b"
    ),
    re.compile(
        r"\b(?:said|emailed|called|posted|replied|wrote)\s+"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b"
    ),
)


ALIAS_CONTEXT_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(
        r"\b(?i:alias|aka|a/k/a|known as|goes by)\s+"
        r"([A-Za-z][A-Za-z0-9._-]{2,64})\b"
    ),
)


LOCATION_CONTEXT_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(
        r"\b(?i:from|in|near|at)\s+"
        r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,3})\b"
    ),
)


TARGET_GROUP_TERMS: dict[str, Sequence[str]] = {
    "nationality_or_origin": (
        "immigrant",
        "immigrants",
        "refugee",
        "refugees",
        "foreigner",
        "foreigners",
        "asylum seeker",
        "asylum seekers",
    ),
    "religion": (
        "muslim",
        "muslims",
        "jew",
        "jews",
        "christian",
        "christians",
        "hindu",
        "hindus",
        "sikh",
        "sikhs",
    ),
    "gender": (
        "woman",
        "women",
        "man",
        "men",
        "girl",
        "girls",
        "boy",
        "boys",
        "trans woman",
        "trans women",
        "trans man",
        "trans men",
    ),
    "sexual_orientation": (
        "gay people",
        "lesbian people",
        "bisexual people",
        "lgbt people",
        "lgbtq people",
    ),
    "disability": (
        "disabled people",
        "disabled students",
        "autistic people",
        "deaf people",
        "blind people",
    ),
    "race_or_ethnicity": (
        "black people",
        "asian people",
        "roma",
        "travellers",
        "latino people",
        "hispanic people",
    ),
}


def regex_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for entity_type, pattern in REGEX_PATTERNS:
        for match in pattern.finditer(text):
            spans.append(
                Span(
                    start=match.start(),
                    end=match.end(),
                    entity_type=entity_type,
                    text=match.group(0),
                    score=0.85,
                    source="regex",
                )
            )
    return spans


def context_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for pattern in PERSON_CONTEXT_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(1)
            spans.append(
                Span(start, end, "PERSON", text[start:end], 0.72, "context_person")
            )
    for pattern in ALIAS_CONTEXT_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(1)
            spans.append(
                Span(start, end, "ALIAS", text[start:end], 0.7, "context_alias")
            )
    for pattern in LOCATION_CONTEXT_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(1)
            value = text[start:end]
            if value.lower() in {"the", "a", "an"}:
                continue
            spans.append(
                Span(start, end, "LOCATION", value, 0.65, "context_location")
            )
    return spans


def target_group_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for category, terms in TARGET_GROUP_TERMS.items():
        for term in terms:
            pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)
            for match in pattern.finditer(text):
                spans.append(
                    Span(
                        start=match.start(),
                        end=match.end(),
                        entity_type="TARGET_GROUP",
                        text=match.group(0),
                        score=0.7,
                        source="target_dictionary",
                        category=category,
                    )
                )
    return spans


def span_priority(span: Span) -> tuple[int, float, int]:
    source_priority = {
        "regex": 3,
        "context_person": 2,
        "context_alias": 2,
        "context_location": 1,
        "target_dictionary": 0,
    }.get(span.source, 0)
    return (span.end - span.start, span.score, source_priority)


def merge_spans(spans: Iterable[Span]) -> list[Span]:
    chosen: list[Span] = []
    for span in sorted(spans, key=span_priority, reverse=True):
        overlaps = [
            existing
            for existing in chosen
            if span.start < existing.end and span.end > existing.start
        ]
        if not overlaps:
            chosen.append(span)
            continue
        for existing in overlaps:
            if (
                span.start == existing.start
                and span.end == existing.end
                and span.entity_type == existing.entity_type
            ):
                break
    return sorted(chosen, key=lambda item: (item.start, item.end))


def detect_spans(
    text: str,
    *,
    include_context: bool = True,
    include_targets: bool = False,
) -> list[Span]:
    spans: list[Span] = []
    spans.extend(regex_spans(text))
    if include_context:
        spans.extend(context_spans(text))
    if include_targets:
        spans.extend(target_group_spans(text))
    return merge_spans(spans)
