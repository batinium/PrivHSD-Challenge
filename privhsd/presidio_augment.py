"""Compatibility wrappers for the filtered optional Presidio provider."""

from __future__ import annotations

from .span_providers.presidio import (
    FALSE_PERSON_TERMS,
    PRESIDIO_ENTITY_MAP,
    TRANSIENT_DATE_TERMS,
    PresidioAugmentError,
    durable_date_like,
    filtered_presidio_candidates,
    filtered_presidio_spans,
    load_presidio_analyzer,
    location_like,
    overlaps,
    person_like,
    rejection_reason,
    span_hits_protected_cue,
)

__all__ = [
    "FALSE_PERSON_TERMS",
    "PRESIDIO_ENTITY_MAP",
    "TRANSIENT_DATE_TERMS",
    "PresidioAugmentError",
    "durable_date_like",
    "filtered_presidio_candidates",
    "filtered_presidio_spans",
    "load_presidio_analyzer",
    "location_like",
    "overlaps",
    "person_like",
    "rejection_reason",
    "span_hits_protected_cue",
]

