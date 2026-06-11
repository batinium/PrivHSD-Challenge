"""Filtered optional Presidio spans for candidate generation."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any

from .detectors import Span, target_group_spans
from .metrics import UTILITY_CUES


PRESIDIO_ENTITY_MAP = {
    "PERSON": "PERSON",
    "LOCATION": "LOCATION",
    "DATE_TIME": "DATE",
}
FALSE_PERSON_TERMS = {
    "dick",
    "max",
    "ngl",
}
TRANSIENT_DATE_TERMS = {
    "today",
    "tomorrow",
    "yesterday",
    "christmas",
}


class PresidioAugmentError(ValueError):
    pass


def load_presidio_analyzer() -> Any:
    try:
        from presidio_analyzer import AnalyzerEngine
    except ModuleNotFoundError as exc:
        if exc.name == "presidio_analyzer":
            raise PresidioAugmentError(
                "Install optional Presidio dependencies with: "
                "python -m pip install '.[presidio]'"
            ) from exc
        raise
    try:
        return AnalyzerEngine()
    except Exception as exc:
        raise PresidioAugmentError(f"Presidio initialization failed: {exc}") from exc


def overlaps(start: int, end: int, span: Span) -> bool:
    return start < span.end and end > span.start


def span_hits_protected_cue(text: str, start: int, end: int) -> bool:
    value = text[start:end].lower()
    if any(cue in value for cue in UTILITY_CUES):
        return True
    return any(overlaps(start, end, span) for span in target_group_spans(text))


def person_like(value: str) -> bool:
    normalized = value.strip()
    lowered = normalized.lower()
    if lowered in FALSE_PERSON_TERMS:
        return False
    if any(character.isdigit() for character in normalized):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", normalized)
    if not words:
        return False
    if len(words) >= 2:
        return True
    return normalized[:1].isupper()


def location_like(value: str) -> bool:
    normalized = value.strip()
    if any(character.isdigit() for character in normalized):
        return False
    if re.fullmatch(r"[A-Z]{2,4}", normalized):
        return True
    return bool(
        re.fullmatch(
            r"[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*)*",
            normalized,
        )
    )


def durable_date_like(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in TRANSIENT_DATE_TERMS:
        return False
    return bool(
        re.search(r"\d", normalized)
        or re.search(r"\b\d{1,2}(?:st|nd|rd|th)?\s+century\b", normalized)
        or re.search(r"\b(?:early|mid|late)\s+\d{1,2}", normalized)
    )


def rejection_reason(text: str, entity_type: str, start: int, end: int) -> str | None:
    value = text[start:end]
    if entity_type == "NRP":
        return "nrp_preserved"
    if span_hits_protected_cue(text, start, end):
        return "protected_cue_overlap"
    if entity_type == "PERSON" and not person_like(value):
        return "person_shape"
    if entity_type == "LOCATION" and not location_like(value):
        return "location_shape"
    if entity_type == "DATE_TIME" and not durable_date_like(value):
        return "transient_date"
    if entity_type not in PRESIDIO_ENTITY_MAP:
        return "unsupported_type"
    return None


def filtered_presidio_spans(
    text: str,
    analyzer: Any,
    *,
    language: str = "en",
) -> tuple[list[Span], dict[str, Any]]:
    results = analyzer.analyze(text=text, language=language)
    accepted: list[Span] = []
    rejected_counts: Counter[str] = Counter()
    accepted_counts: Counter[str] = Counter()
    for result in results:
        start = int(result.start)
        end = int(result.end)
        entity_type = str(result.entity_type)
        score = float(getattr(result, "score", 0.0) or 0.0)
        reason = rejection_reason(text, entity_type, start, end)
        if reason:
            rejected_counts[reason] += 1
            continue
        mapped_type = PRESIDIO_ENTITY_MAP[entity_type]
        accepted.append(
            Span(
                start=start,
                end=end,
                entity_type=mapped_type,
                text=text[start:end],
                score=score,
                source=f"presidio:{entity_type}",
            )
        )
        accepted_counts[mapped_type] += 1
    report = {
        "enabled": True,
        "presidio_span_count": len(results),
        "accepted_span_count": len(accepted),
        "accepted_counts_by_type": dict(sorted(accepted_counts.items())),
        "rejected_span_count": sum(rejected_counts.values()),
        "rejected_counts_by_reason": dict(sorted(rejected_counts.items())),
    }
    return accepted, report
