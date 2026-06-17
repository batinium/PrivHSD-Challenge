"""Provider loading by CLI/app name."""

from __future__ import annotations

from .base import SpanProvider
from .presidio import PresidioSpanProvider, load_presidio_analyzer
from .scrubadub_provider import ScrubadubProviderError, load_scrubadub_provider


SUPPORTED_PROVIDER_NAMES = frozenset({"presidio", "scrubadub"})


class SpanProviderRegistryError(ValueError):
    pass


def load_span_provider(
    name: str,
    *,
    presidio_language: str = "en",
) -> SpanProvider:
    normalized = name.strip().lower().replace("_", "-")
    if normalized == "presidio":
        return PresidioSpanProvider(
            analyzer=load_presidio_analyzer(),
            language=presidio_language,
        )
    if normalized == "scrubadub":
        return load_scrubadub_provider()
    raise SpanProviderRegistryError(
        f"unknown provider {name!r}; expected one of {sorted(SUPPORTED_PROVIDER_NAMES)}"
    )


def load_span_providers(
    names: list[str] | tuple[str, ...],
    *,
    presidio_language: str = "en",
) -> list[SpanProvider]:
    providers: list[SpanProvider] = []
    seen: set[str] = set()
    for name in names:
        normalized = name.strip().lower().replace("_", "-")
        if normalized in seen:
            continue
        seen.add(normalized)
        providers.append(
            load_span_provider(
                normalized,
                presidio_language=presidio_language,
            )
        )
    return providers


__all__ = [
    "ScrubadubProviderError",
    "SUPPORTED_PROVIDER_NAMES",
    "SpanProviderRegistryError",
    "load_span_provider",
    "load_span_providers",
]
