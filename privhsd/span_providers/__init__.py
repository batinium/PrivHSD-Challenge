"""Pluggable span providers and fusion policy."""

from .base import (
    PRIVACY_CLASS_DIRECT,
    PRIVACY_CLASS_NONE,
    PRIVACY_CLASS_QUASI,
    PRIVACY_CLASS_STYLE,
    UTILITY_CLASS_ACTION,
    UTILITY_CLASS_HSD_TARGET,
    UTILITY_CLASS_NEGATION,
    UTILITY_CLASS_NONE,
    SpanCandidate,
    SpanProvider,
    SpanProviderOutput,
)
from .fusion import FusionConfig, FusedSpanResult, fuse_span_candidates

__all__ = [
    "FusionConfig",
    "FusedSpanResult",
    "PRIVACY_CLASS_DIRECT",
    "PRIVACY_CLASS_NONE",
    "PRIVACY_CLASS_QUASI",
    "PRIVACY_CLASS_STYLE",
    "SpanCandidate",
    "SpanProvider",
    "SpanProviderOutput",
    "UTILITY_CLASS_ACTION",
    "UTILITY_CLASS_HSD_TARGET",
    "UTILITY_CLASS_NEGATION",
    "UTILITY_CLASS_NONE",
    "fuse_span_candidates",
]

