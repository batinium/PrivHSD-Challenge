"""Optional scrubadub PII span provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import (
    SpanCandidate,
    SpanProviderOutput,
    privacy_class_for_entity,
    utility_class_for_entity,
)


SCRUBADUB_ENTITY_MAP = {
    "email": "EMAIL",
    "url": "URL",
    "phone": "PHONE",
    "twitter": "USER",
    "skype": "USER",
    "name": "PERSON",
    "address": "LOCATION",
    "postcode": "LOCATION",
}


class ScrubadubProviderError(ValueError):
    pass


def load_scrubber() -> Any:
    try:
        import scrubadub
    except ModuleNotFoundError as exc:
        if exc.name == "scrubadub":
            raise ScrubadubProviderError(
                "Install optional scrubadub dependencies with: "
                "python -m pip install '.[scrubadub]'"
            ) from exc
        raise
    try:
        return scrubadub.Scrubber()
    except Exception as exc:  # pragma: no cover - optional dependency path.
        raise ScrubadubProviderError(f"scrubadub initialization failed: {exc}") from exc


def filth_type(filth: Any) -> str:
    raw = (
        getattr(filth, "type", None)
        or getattr(filth, "detector_name", None)
        or filth.__class__.__name__.replace("Filth", "")
    )
    return str(raw).lower().replace("_filth", "").replace("filth", "")


@dataclass(frozen=True)
class ScrubadubSpanProvider:
    scrubber: Any
    name: str = "scrubadub"

    def propose(self, text: str) -> SpanProviderOutput:
        try:
            raw_results = list(self.scrubber.iter_filth(text))
        except Exception as exc:  # pragma: no cover - optional dependency path.
            raise ScrubadubProviderError(f"scrubadub detection failed: {exc}") from exc
        candidates: list[SpanCandidate] = []
        rejected_counts: dict[str, int] = {}
        for filth in raw_results:
            kind = filth_type(filth)
            mapped_type = SCRUBADUB_ENTITY_MAP.get(kind)
            if not mapped_type:
                rejected_counts["unsupported_type"] = (
                    rejected_counts.get("unsupported_type", 0) + 1
                )
                continue
            start = int(getattr(filth, "beg", getattr(filth, "start", -1)))
            end = int(getattr(filth, "end", -1))
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
                    score=float(getattr(filth, "score", 0.7) or 0.7),
                    explanation_code=kind,
                    metadata={"source": f"scrubadub:{kind}"},
                )
            )
        audit = {
            "enabled": True,
            "provider": self.name,
            "raw_span_count": len(raw_results),
            "accepted_span_count": len(candidates),
            "rejected_span_count": sum(rejected_counts.values()),
            "rejected_counts_by_reason": dict(sorted(rejected_counts.items())),
        }
        return SpanProviderOutput(provider=self.name, spans=tuple(candidates), audit=audit)


def load_scrubadub_provider() -> ScrubadubSpanProvider:
    return ScrubadubSpanProvider(scrubber=load_scrubber())

