"""Fuse provider spans into replacement-ready spans."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
import re
from typing import Any, Iterable

from contextsafe_hsd.detectors import Span, merge_spans, span_priority, target_group_spans
from contextsafe_hsd.resource_config import load_utility_cue_terms

from .base import (
    HIGH_PRECISION_DIRECT_TYPES,
    PRIVACY_CLASS_DIRECT,
    SpanCandidate,
)


DEFAULT_THRESHOLDS = {
    "ALIAS": 0.0,
    "CREDIT_CARD": 0.0,
    "CRYPTO_WALLET": 0.0,
    "DISCORD_USER": 0.0,
    "USER": 0.0,
    "EMAIL": 0.0,
    "IBAN": 0.0,
    "PHONE": 0.0,
    "URL": 0.0,
    "IP_ADDRESS": 0.0,
    "SOCIAL_LINK": 0.0,
    "IDENTIFIER": 0.0,
    "PERSON": 0.5,
    "LOCATION": 0.6,
    "ORGANIZATION": 0.6,
    "DATE": 0.55,
    "AGE": 0.5,
    "TARGET_GROUP": 0.0,
}


@dataclass(frozen=True)
class FusionConfig:
    thresholds: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_THRESHOLDS)
    )
    preserve_hsd_cues: bool = True


@dataclass(frozen=True)
class FusedSpanResult:
    spans: list[Span]
    audit: dict[str, Any]


def overlaps(start: int, end: int, span: Span | SpanCandidate) -> bool:
    return start < span.end and end > span.start


@lru_cache(maxsize=1)
def protected_term_patterns() -> tuple[re.Pattern[str], ...]:
    terms = (
        set(load_utility_cue_terms("utility_cues"))
        | set(load_utility_cue_terms("action_terms"))
        | set(load_utility_cue_terms("negation_modality_terms"))
    )
    return tuple(
        re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])",
            re.I,
        )
        for term in sorted(terms, key=lambda value: (-len(value), value))
    )


def protected_term_ranges(text: str) -> list[tuple[int, int, str]]:
    ranges: list[tuple[int, int, str]] = []
    for span in target_group_spans(text):
        ranges.append((span.start, span.end, "hsd_target"))
    for pattern in protected_term_patterns():
        for match in pattern.finditer(text):
            ranges.append((match.start(), match.end(), "hsd_cue"))
    return ranges


def hits_protected_cue(
    text: str,
    candidate: SpanCandidate,
    protected_ranges: list[tuple[int, int, str]],
) -> bool:
    if candidate.entity_type == "TARGET_GROUP":
        return False
    if (
        candidate.privacy_class == PRIVACY_CLASS_DIRECT
        and candidate.entity_type in HIGH_PRECISION_DIRECT_TYPES
    ):
        return False
    return any(
        candidate.start < end and candidate.end > start
        for start, end, _kind in protected_ranges
    )


def rejection_reason(
    text: str,
    candidate: SpanCandidate,
    config: FusionConfig,
    protected_ranges: list[tuple[int, int, str]],
) -> str | None:
    if candidate.start < 0 or candidate.end > len(text) or candidate.start >= candidate.end:
        return "invalid_offsets"
    if text[candidate.start : candidate.end] != candidate.text:
        return "text_mismatch"
    min_score = config.thresholds.get(candidate.entity_type, 0.5)
    if candidate.score < min_score:
        return "below_threshold"
    if config.preserve_hsd_cues and hits_protected_cue(text, candidate, protected_ranges):
        return "protected_cue_overlap"
    return None


def sort_key(candidate: SpanCandidate) -> tuple[int, float, int]:
    span = candidate.to_span()
    return span_priority(span)


def provider_summary(candidates: Iterable[SpanCandidate]) -> dict[str, Any]:
    by_provider = Counter(candidate.provider for candidate in candidates)
    by_type = Counter(candidate.entity_type for candidate in candidates)
    return {
        "span_count": sum(by_provider.values()),
        "counts_by_provider": dict(sorted(by_provider.items())),
        "counts_by_entity_type": dict(sorted(by_type.items())),
    }


def fuse_span_candidates(
    text: str,
    candidates: Iterable[SpanCandidate],
    config: FusionConfig | None = None,
) -> FusedSpanResult:
    config = config or FusionConfig()
    materialized = list(candidates)
    needs_protected_scan = any(
        candidate.provider != "deterministic" for candidate in materialized
    )
    protected_ranges = protected_term_ranges(text) if needs_protected_scan else []
    accepted_candidates: list[SpanCandidate] = []
    rejected: list[dict[str, Any]] = []
    rejected_counts: Counter[str] = Counter()
    for candidate in materialized:
        reason = rejection_reason(text, candidate, config, protected_ranges)
        if reason:
            rejected_counts[reason] += 1
            rejected.append(candidate.audit_record(reason=reason))
            continue
        accepted_candidates.append(candidate)

    sorted_candidates = sorted(accepted_candidates, key=sort_key, reverse=True)
    chosen: list[SpanCandidate] = []
    overlap_rejections: list[dict[str, Any]] = []
    overlap_counts: Counter[str] = Counter()
    disagreements: defaultdict[tuple[int, int], set[str]] = defaultdict(set)
    for candidate in sorted_candidates:
        overlaps_existing = [
            existing
            for existing in chosen
            if candidate.start < existing.end and candidate.end > existing.start
        ]
        if not overlaps_existing:
            chosen.append(candidate)
            continue
        for existing in overlaps_existing:
            key = (min(candidate.start, existing.start), max(candidate.end, existing.end))
            disagreements[key].update({candidate.provider, existing.provider})
        reason = "overlap_lower_priority"
        overlap_counts[reason] += 1
        overlap_rejections.append(candidate.audit_record(reason=reason))

    spans = merge_spans([candidate.to_span() for candidate in chosen])
    accepted_counts = Counter(span.entity_type for span in spans)
    accepted_provider_counts = Counter(
        candidate.provider
        for candidate in chosen
        if any(
            candidate.start == span.start
            and candidate.end == span.end
            and candidate.entity_type == span.entity_type
            for span in spans
        )
    )
    rejected.extend(overlap_rejections)
    rejected_counts.update(overlap_counts)
    provider_disagreements = [
        {
            "start": start,
            "end": end,
            "providers": sorted(providers),
        }
        for (start, end), providers in sorted(disagreements.items())
        if len(providers) > 1
    ]
    audit = {
        "enabled": True,
        "input": provider_summary(materialized),
        "accepted_span_count": len(spans),
        "accepted_counts_by_type": dict(sorted(accepted_counts.items())),
        "accepted_counts_by_provider": dict(sorted(accepted_provider_counts.items())),
        "rejected_span_count": sum(rejected_counts.values()),
        "rejected_counts_by_reason": dict(sorted(rejected_counts.items())),
        "rejected_spans": rejected[:200],
        "provider_disagreement_count": len(provider_disagreements),
        "provider_disagreements": provider_disagreements[:200],
        "thresholds": dict(sorted(config.thresholds.items())),
        "preserve_hsd_cues": config.preserve_hsd_cues,
    }
    return FusedSpanResult(spans=spans, audit=audit)
