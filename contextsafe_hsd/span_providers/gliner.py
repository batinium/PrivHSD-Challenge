"""Optional GLiNER zero-shot PII span provider."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re
from typing import Any

from .base import (
    SpanCandidate,
    SpanProviderOutput,
    privacy_class_for_entity,
    utility_class_for_entity,
)


DEFAULT_GLINER_MODEL = "urchade/gliner_medium-v2.1"
GLINER_PROFILES = frozenset({"general", "pii"})
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
GLINER_PII_MODEL = "nvidia/gliner-PII"
GLINER_PII_LABELS = (
    "person",
    "full name",
    "username",
    "online handle",
    "social media handle",
    "email address",
    "phone number",
    "street address",
    "home address",
    "ip address",
    "url",
    "personal url",
    "government id",
    "account number",
    "case number",
    "student id",
    "driver license number",
    "passport number",
    "date of birth",
    "age",
    "city",
    "neighborhood",
    "school",
    "university",
    "organization",
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
GLINER_PII_ENTITY_MAP = {
    **GLINER_ENTITY_MAP,
    "full name": "PERSON",
    "username": "USER",
    "social media handle": "USER",
    "home address": "LOCATION",
    "ip address": "IP_ADDRESS",
    "url": "URL",
    "personal url": "URL",
    "account number": "IDENTIFIER",
    "driver license number": "IDENTIFIER",
    "passport number": "IDENTIFIER",
    "age": "AGE",
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
GLINER_PII_THRESHOLDS = {
    **DEFAULT_THRESHOLDS,
    "full name": 0.55,
    "username": 0.4,
    "online handle": 0.4,
    "social media handle": 0.4,
    "email address": 0.3,
    "phone number": 0.3,
    "street address": 0.5,
    "home address": 0.5,
    "ip address": 0.3,
    "url": 0.3,
    "personal url": 0.3,
    "government id": 0.4,
    "account number": 0.4,
    "case number": 0.4,
    "student id": 0.4,
    "driver license number": 0.4,
    "passport number": 0.4,
    "date of birth": 0.5,
    "age": 0.5,
    "city": 0.65,
    "neighborhood": 0.65,
    "school": 0.6,
    "university": 0.6,
    "organization": 0.65,
}


@dataclass(frozen=True)
class GlinerProfile:
    name: str
    labels: tuple[str, ...]
    entity_map: dict[str, str]
    thresholds: dict[str, float]
    recommended_model: str | None = None


GLINER_PROFILE_CONFIGS = {
    "general": GlinerProfile(
        name="general",
        labels=GLINER_LABELS,
        entity_map=GLINER_ENTITY_MAP,
        thresholds=DEFAULT_THRESHOLDS,
        recommended_model=DEFAULT_GLINER_MODEL,
    ),
    "pii": GlinerProfile(
        name="pii",
        labels=GLINER_PII_LABELS,
        entity_map=GLINER_PII_ENTITY_MAP,
        thresholds=GLINER_PII_THRESHOLDS,
        recommended_model=GLINER_PII_MODEL,
    ),
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


def normalize_label(label: str) -> str:
    normalized = label.lower().strip()
    normalized = re.sub(r"[_-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" .,:;[](){}")


def gliner_profile_config(profile: str) -> GlinerProfile:
    normalized = profile.strip().lower()
    try:
        return GLINER_PROFILE_CONFIGS[normalized]
    except KeyError as exc:
        raise GlinerProviderError(
            f"unknown GLiNER profile {profile!r}; expected one of {sorted(GLINER_PROFILES)}"
        ) from exc


@dataclass(frozen=True)
class GlinerSpanProvider:
    model: Any
    labels: tuple[str, ...] = GLINER_LABELS
    thresholds: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_THRESHOLDS)
    )
    entity_map: dict[str, str] = field(default_factory=lambda: dict(GLINER_ENTITY_MAP))
    profile: str = "general"
    name: str = "gliner"

    def __post_init__(self) -> None:
        profile_config = gliner_profile_config(self.profile)
        object.__setattr__(self, "profile", profile_config.name)
        if self.labels == GLINER_LABELS and profile_config.name != "general":
            object.__setattr__(self, "labels", profile_config.labels)
        if self.thresholds == DEFAULT_THRESHOLDS and profile_config.name != "general":
            object.__setattr__(self, "thresholds", dict(profile_config.thresholds))
        if self.entity_map == GLINER_ENTITY_MAP and profile_config.name != "general":
            object.__setattr__(self, "entity_map", dict(profile_config.entity_map))

    def propose(self, text: str) -> SpanProviderOutput:
        return self.propose_many([text], batch_size=1)[0]

    def propose_many(
        self,
        texts: list[str],
        *,
        batch_size: int,
    ) -> list[SpanProviderOutput]:
        if not texts:
            return []
        try:
            raw_batches = self._predict_batches(texts, batch_size=batch_size)
        except Exception as exc:  # pragma: no cover - model runtime path.
            raise GlinerProviderError(f"GLiNER prediction failed: {exc}") from exc
        if len(raw_batches) != len(texts):
            raise GlinerProviderError(
                "GLiNER prediction returned a different number of rows than requested"
            )
        return [
            self._output_from_results(text, raw_results)
            for text, raw_results in zip(texts, raw_batches)
        ]

    def _predict_batches(
        self,
        texts: list[str],
        *,
        batch_size: int,
    ) -> list[list[dict[str, Any]]]:
        labels = list(self.labels)
        batch_predict = getattr(self.model, "batch_predict_entities", None)
        if callable(batch_predict):
            raw_batches = batch_predict(texts, labels, batch_size=batch_size)
            return [list(batch) for batch in raw_batches]
        return [list(self.model.predict_entities(text, labels)) for text in texts]

    def _output_from_results(
        self,
        text: str,
        raw_results: list[dict[str, Any]],
    ) -> SpanProviderOutput:
        candidates: list[SpanCandidate] = []
        rejected_counts: dict[str, int] = {}
        raw_label_counts: Counter[str] = Counter()
        for item in raw_results:
            raw_label = str(item.get("label", ""))
            label = normalize_label(raw_label)
            raw_label_counts[label] += 1
            mapped_type = self.entity_map.get(label)
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
            "profile": self.profile,
            "raw_span_count": len(raw_results),
            "raw_counts_by_label": dict(sorted(raw_label_counts.items())),
            "accepted_span_count": len(candidates),
            "rejected_span_count": sum(rejected_counts.values()),
            "rejected_counts_by_reason": dict(sorted(rejected_counts.items())),
            "labels": list(self.labels),
            "thresholds": dict(sorted(self.thresholds.items())),
        }
        return SpanProviderOutput(provider=self.name, spans=tuple(candidates), audit=audit)


def load_gliner_provider(
    model_name: str = DEFAULT_GLINER_MODEL,
    *,
    profile: str = "general",
) -> GlinerSpanProvider:
    profile_config = gliner_profile_config(profile)
    return GlinerSpanProvider(
        model=load_gliner_model(model_name),
        labels=profile_config.labels,
        thresholds=dict(profile_config.thresholds),
        entity_map=dict(profile_config.entity_map),
        profile=profile_config.name,
    )
