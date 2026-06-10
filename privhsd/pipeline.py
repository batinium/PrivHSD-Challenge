"""Text privatization pipeline."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .detectors import Span, detect_spans


MODES = {"utility", "balanced", "privacy"}


@dataclass(frozen=True)
class PrivatizerConfig:
    mode: str = "balanced"
    generalize_targets: bool | None = None
    include_context_detectors: bool = True

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {sorted(MODES)}")

    @property
    def target_generalization_enabled(self) -> bool:
        if self.generalize_targets is not None:
            return self.generalize_targets
        return self.mode == "privacy"


@dataclass(frozen=True)
class PrivatizationResult:
    text: str
    spans: tuple[Span, ...]
    transformations: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]


def replacement_for(span: Span, config: PrivatizerConfig) -> str:
    return span.replacement_tag()


def apply_replacements(
    text: str,
    spans: list[Span],
    config: PrivatizerConfig,
) -> tuple[str, tuple[dict[str, Any], ...]]:
    parts: list[str] = []
    transformations: list[dict[str, Any]] = []
    cursor = 0
    output_cursor = 0
    for span in spans:
        prefix = text[cursor : span.start]
        parts.append(prefix)
        output_cursor += len(prefix)
        replacement = replacement_for(span, config)
        parts.append(replacement)
        transformations.append(
            {
                "entity_type": span.entity_type,
                "category": span.category,
                "source": span.source,
                "score": span.score,
                "source_start": span.start,
                "source_end": span.end,
                "output_start": output_cursor,
                "output_end": output_cursor + len(replacement),
                "replacement": replacement,
            }
        )
        output_cursor += len(replacement)
        cursor = span.end
    parts.append(text[cursor:])
    return "".join(parts), tuple(transformations)


def text_metrics(original: str, privatized: str, spans: list[Span]) -> dict[str, Any]:
    direct_spans = [span for span in spans if span.entity_type != "TARGET_GROUP"]
    counts = Counter(span.entity_type for span in spans)
    direct_counts = Counter(span.entity_type for span in direct_spans)
    similarity = SequenceMatcher(None, original, privatized).ratio()
    return {
        "span_count": len(spans),
        "direct_identifier_span_count": len(direct_spans),
        "counts_by_entity_type": dict(sorted(counts.items())),
        "direct_identifier_counts_by_entity_type": dict(sorted(direct_counts.items())),
        "character_similarity": round(similarity, 4),
        "changed": original != privatized,
    }


def privatize_text(
    text: str,
    config: PrivatizerConfig | None = None,
) -> PrivatizationResult:
    config = config or PrivatizerConfig()
    spans = detect_spans(
        text,
        include_context=config.include_context_detectors,
        include_targets=config.target_generalization_enabled,
    )
    privatized, transformations = apply_replacements(text, spans, config)
    return PrivatizationResult(
        text=privatized,
        spans=tuple(spans),
        transformations=transformations,
        metrics=text_metrics(text, privatized, spans),
    )

