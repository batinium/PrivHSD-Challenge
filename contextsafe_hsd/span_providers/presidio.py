"""Filtered optional Presidio span provider."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Any

from contextsafe_hsd.detectors import Span, target_group_spans
from contextsafe_hsd.metrics import UTILITY_CUES

from .base import (
    SpanCandidate,
    SpanProviderOutput,
    privacy_class_for_entity,
    utility_class_for_entity,
)


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


@dataclass(frozen=True)
class PresidioSpanProvider:
    analyzer: Any
    language: str = "en"
    name: str = "presidio"

    def propose_many(
        self,
        texts: list[str],
        *,
        batch_size: int,
    ) -> list[SpanProviderOutput]:
        return [self.propose(text) for text in texts]

    def propose(self, text: str) -> SpanProviderOutput:
        results = self.analyzer.analyze(text=text, language=self.language)
        accepted: list[SpanCandidate] = []
        rejected_counts: Counter[str] = Counter()
        accepted_counts: Counter[str] = Counter()
        raw_counts: Counter[str] = Counter()
        for result in results:
            start = int(result.start)
            end = int(result.end)
            raw_entity_type = str(result.entity_type)
            raw_counts[raw_entity_type] += 1
            score = float(getattr(result, "score", 0.0) or 0.0)
            reason = rejection_reason(text, raw_entity_type, start, end)
            if reason:
                rejected_counts[reason] += 1
                continue
            mapped_type = PRESIDIO_ENTITY_MAP[raw_entity_type]
            accepted.append(
                SpanCandidate(
                    start=start,
                    end=end,
                    entity_type=mapped_type,
                    text=text[start:end],
                    privacy_class=privacy_class_for_entity(mapped_type),
                    utility_class=utility_class_for_entity(mapped_type),
                    provider=self.name,
                    score=score,
                    explanation_code=raw_entity_type,
                    category=None,
                    metadata={
                        "source": f"presidio:{raw_entity_type}",
                        "raw_entity_type": raw_entity_type,
                    },
                )
            )
            accepted_counts[mapped_type] += 1
        audit = {
            "enabled": True,
            "provider": self.name,
            "language": self.language,
            "presidio_span_count": len(results),
            "raw_counts_by_type": dict(sorted(raw_counts.items())),
            "accepted_span_count": len(accepted),
            "accepted_counts_by_type": dict(sorted(accepted_counts.items())),
            "rejected_span_count": sum(rejected_counts.values()),
            "rejected_counts_by_reason": dict(sorted(rejected_counts.items())),
        }
        return SpanProviderOutput(provider=self.name, spans=tuple(accepted), audit=audit)


def filtered_presidio_candidates(
    text: str,
    analyzer: Any,
    *,
    language: str = "en",
) -> tuple[list[SpanCandidate], dict[str, Any]]:
    output = PresidioSpanProvider(analyzer=analyzer, language=language).propose(text)
    return list(output.spans), dict(output.audit)


def filtered_presidio_spans(
    text: str,
    analyzer: Any,
    *,
    language: str = "en",
) -> tuple[list[Span], dict[str, Any]]:
    candidates, report = filtered_presidio_candidates(
        text,
        analyzer,
        language=language,
    )
    return [candidate.to_span() for candidate in candidates], report
