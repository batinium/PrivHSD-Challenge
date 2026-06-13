"""Adapter for the existing deterministic detector layer."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from privhsd.detectors import detect_spans

from .base import SpanCandidate, SpanProviderOutput


@dataclass(frozen=True)
class DeterministicSpanProvider:
    include_context: bool = True
    include_targets: bool = False
    name: str = "deterministic"

    def propose(self, text: str) -> SpanProviderOutput:
        spans = detect_spans(
            text,
            include_context=self.include_context,
            include_targets=self.include_targets,
        )
        candidates = tuple(SpanCandidate.from_span(span, provider=self.name) for span in spans)
        counts = Counter(candidate.entity_type for candidate in candidates)
        source_counts = Counter(
            str(candidate.metadata.get("source") or candidate.provider)
            for candidate in candidates
        )
        audit: dict[str, Any] = {
            "enabled": True,
            "span_count": len(candidates),
            "counts_by_entity_type": dict(sorted(counts.items())),
            "counts_by_source": dict(sorted(source_counts.items())),
            "include_context": self.include_context,
            "include_targets": self.include_targets,
        }
        return SpanProviderOutput(provider=self.name, spans=candidates, audit=audit)

