"""Shared span provider schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from contextsafe_hsd.detectors import Span


PRIVACY_CLASS_DIRECT = "direct_identifier"
PRIVACY_CLASS_QUASI = "quasi_identifier"
PRIVACY_CLASS_STYLE = "style"
PRIVACY_CLASS_NONE = "none"

UTILITY_CLASS_HSD_TARGET = "hsd_target"
UTILITY_CLASS_ACTION = "hsd_action"
UTILITY_CLASS_NEGATION = "negation"
UTILITY_CLASS_QUOTE = "quote"
UTILITY_CLASS_NONE = "none"

DIRECT_IDENTIFIER_TYPES = frozenset(
    {
        "ALIAS",
        "CREDIT_CARD",
        "CRYPTO_WALLET",
        "DISCORD_USER",
        "PERSON",
        "USER",
        "EMAIL",
        "IBAN",
        "PHONE",
        "URL",
        "IP_ADDRESS",
        "SOCIAL_LINK",
        "IDENTIFIER",
    }
)
HIGH_PRECISION_DIRECT_TYPES = frozenset(
    {
        "ALIAS",
        "CREDIT_CARD",
        "CRYPTO_WALLET",
        "DISCORD_USER",
        "EMAIL",
        "IBAN",
        "IP_ADDRESS",
        "IDENTIFIER",
        "PHONE",
        "SOCIAL_LINK",
        "URL",
        "USER",
    }
)
QUASI_IDENTIFIER_TYPES = frozenset({"AGE", "DATE", "LOCATION", "ORGANIZATION"})


def privacy_class_for_entity(entity_type: str) -> str:
    if entity_type in DIRECT_IDENTIFIER_TYPES:
        return PRIVACY_CLASS_DIRECT
    if entity_type in QUASI_IDENTIFIER_TYPES:
        return PRIVACY_CLASS_QUASI
    if entity_type == "STYLE":
        return PRIVACY_CLASS_STYLE
    return PRIVACY_CLASS_NONE


def utility_class_for_entity(entity_type: str) -> str:
    if entity_type == "TARGET_GROUP":
        return UTILITY_CLASS_HSD_TARGET
    return UTILITY_CLASS_NONE


@dataclass(frozen=True)
class SpanCandidate:
    start: int
    end: int
    text: str
    entity_type: str
    privacy_class: str
    utility_class: str
    provider: str
    score: float
    explanation_code: str
    category: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_span(
        cls,
        span: Span,
        *,
        provider: str | None = None,
        explanation_code: str | None = None,
    ) -> "SpanCandidate":
        return cls(
            start=span.start,
            end=span.end,
            text=span.text,
            entity_type=span.entity_type,
            privacy_class=privacy_class_for_entity(span.entity_type),
            utility_class=utility_class_for_entity(span.entity_type),
            provider=provider or provider_from_source(span.source),
            score=float(span.score),
            explanation_code=explanation_code or span.source,
            category=span.category,
            metadata={
                "source": span.source,
                **({"replacement": span.replacement} if span.replacement else {}),
            },
        )

    def to_span(self) -> Span:
        return Span(
            start=self.start,
            end=self.end,
            entity_type=self.entity_type,
            text=self.text,
            score=self.score,
            source=str(self.metadata.get("source") or self.provider),
            category=self.category,
            replacement=self.metadata.get("replacement"),
        )

    def audit_record(self, *, reason: str | None = None) -> dict[str, Any]:
        record = {
            "start": self.start,
            "end": self.end,
            "entity_type": self.entity_type,
            "privacy_class": self.privacy_class,
            "utility_class": self.utility_class,
            "provider": self.provider,
            "score": round(float(self.score), 4),
            "explanation_code": self.explanation_code,
        }
        if self.category:
            record["category"] = self.category
        if reason:
            record["reason"] = reason
        return record


@dataclass(frozen=True)
class SpanProviderOutput:
    provider: str
    spans: tuple[SpanCandidate, ...]
    audit: dict[str, Any] = field(default_factory=dict)


class SpanProvider(Protocol):
    name: str

    def propose(self, text: str) -> SpanProviderOutput:
        """Return normalized candidate spans for a single row of text."""


class BatchedSpanProvider(Protocol):
    name: str

    def propose_many(
        self,
        texts: list[str],
        *,
        batch_size: int,
    ) -> list[SpanProviderOutput]:
        """Return normalized candidate spans for a batch of rows."""


def provider_from_source(source: str) -> str:
    if source.startswith("presidio:"):
        return "presidio"
    if source in {
        "regex",
        "regex_crypto_wallet",
        "regex_deobfuscated_email",
        "regex_discord_handle",
        "regex_iban_mod97",
        "regex_ipv6",
        "regex_luhn_credit_card",
        "regex_social_link",
        "context_person",
        "context_alias",
        "context_location",
        "known_location",
        "target_dictionary",
        "target_hashtag",
        "target_variant",
        "target_spaced_variant",
        "external_profanity_lexicon",
        "regex_obfuscated_email",
    }:
        return "deterministic"
    return source.split(":", 1)[0] if ":" in source else source


def candidates_from_spans(
    spans: list[Span] | tuple[Span, ...],
    *,
    provider: str | None = None,
) -> tuple[SpanCandidate, ...]:
    return tuple(SpanCandidate.from_span(span, provider=provider) for span in spans)
