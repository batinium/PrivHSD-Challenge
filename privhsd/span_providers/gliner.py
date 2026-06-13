"""Optional GLiNER zero-shot PII span provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import (
    SpanCandidate,
    SpanProviderOutput,
    privacy_class_for_entity,
    utility_class_for_entity,
)


DEFAULT_GLINER_MODEL = "urchade/gliner_medium-v2.1"
GLINER_LABELS = (
    "person",
    "online handle",
    "email address",
    "phone number",
    "street address",
    "city",
    "neighborhood",
    "school",
    "university",
    "organization",
    "date of birth",
    "case number",
    "student id",
    "government id",
)
GLINER_ENTITY_MAP = {
    "person": "PERSON",
    "online handle": "USER",
    "email address": "EMAIL",
    "phone number": "PHONE",
    "street address": "LOCATION",
    "city": "LOCATION",
    "neighborhood": "LOCATION",
    "school": "ORGANIZATION",
    "university": "ORGANIZATION",
    "organization": "ORGANIZATION",
    "date of birth": "DATE",
    "case number": "IDENTIFIER",
    "student id": "IDENTIFIER",
    "government id": "IDENTIFIER",
}
DEFAULT_THRESHOLDS = {
    "person": 0.55,
    "online handle": 0.45,
    "email address": 0.35,
    "phone number": 0.35,
    "street address": 0.55,
    "city": 0.65,
    "neighborhood": 0.65,
    "school": 0.6,
    "university": 0.6,
    "organization": 0.65,
    "date of birth": 0.55,
    "case number": 0.45,
    "student id": 0.45,
    "government id": 0.45,
}


class GlinerProviderError(ValueError):
    pass


def load_gliner_model(model_name: str = DEFAULT_GLINER_MODEL) -> Any:
    try:
        from gliner import GLiNER
    except ModuleNotFoundError as exc:
        if exc.name == "gliner":
            raise GlinerProviderError(
                "Install optional GLiNER dependencies with: "
                "python -m pip install '.[gliner]'"
            ) from exc
        raise
    try:
        return GLiNER.from_pretrained(model_name)
    except Exception as exc:  # pragma: no cover - model download/runtime path.
        raise GlinerProviderError(f"GLiNER initialization failed: {exc}") from exc


@dataclass(frozen=True)
class GlinerSpanProvider:
    model: Any
    labels: tuple[str, ...] = GLINER_LABELS
    thresholds: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_THRESHOLDS)
    )
    name: str = "gliner"

    def propose(self, text: str) -> SpanProviderOutput:
        try:
            raw_results = self.model.predict_entities(text, list(self.labels))
        except Exception as exc:  # pragma: no cover - model runtime path.
            raise GlinerProviderError(f"GLiNER prediction failed: {exc}") from exc
        candidates: list[SpanCandidate] = []
        rejected_counts: dict[str, int] = {}
        for item in raw_results:
            label = str(item.get("label", "")).lower()
            mapped_type = GLINER_ENTITY_MAP.get(label)
            if not mapped_type:
                rejected_counts["unsupported_label"] = (
                    rejected_counts.get("unsupported_label", 0) + 1
                )
                continue
            score = float(item.get("score", 0.0) or 0.0)
            if score < self.thresholds.get(label, 0.5):
                rejected_counts["below_provider_threshold"] = (
                    rejected_counts.get("below_provider_threshold", 0) + 1
                )
                continue
            start = int(item.get("start", -1))
            end = int(item.get("end", -1))
            if start < 0 or end <= start or end > len(text):
                rejected_counts["invalid_offsets"] = (
                    rejected_counts.get("invalid_offsets", 0) + 1
                )
                continue
            candidates.append(
                SpanCandidate(
                    start=start,
                    end=end,
                    text=text[start:end],
                    entity_type=mapped_type,
                    privacy_class=privacy_class_for_entity(mapped_type),
                    utility_class=utility_class_for_entity(mapped_type),
                    provider=self.name,
                    score=score,
                    explanation_code=label.replace(" ", "_"),
                    metadata={"source": f"gliner:{label}"},
                )
            )
        audit = {
            "enabled": True,
            "provider": self.name,
            "model": getattr(self.model, "name_or_path", None),
            "raw_span_count": len(raw_results),
            "accepted_span_count": len(candidates),
            "rejected_span_count": sum(rejected_counts.values()),
            "rejected_counts_by_reason": dict(sorted(rejected_counts.items())),
            "labels": list(self.labels),
            "thresholds": dict(sorted(self.thresholds.items())),
        }
        return SpanProviderOutput(provider=self.name, spans=tuple(candidates), audit=audit)


def load_gliner_provider(model_name: str = DEFAULT_GLINER_MODEL) -> GlinerSpanProvider:
    return GlinerSpanProvider(model=load_gliner_model(model_name))

