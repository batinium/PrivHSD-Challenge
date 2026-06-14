"""Raw-text-free row state for automatic routing and audit."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contextsafe_hsd.pipeline import PrivatizationResult
from contextsafe_hsd.span_providers.base import SpanCandidate, SpanProviderOutput


@dataclass(frozen=True)
class RowRiskProfile:
    row_index: int
    row_id: str
    text_length: int
    baseline_changed: bool
    direct_identifier_count_before: int
    direct_identifier_count_after: int
    quasi_identifier_count_before: int
    quasi_identifier_count_after: int
    placeholder_count: int
    target_cue_count_before_fast: int
    target_cue_retention_fast: float
    utility_cue_retention_fast: float
    style_risk_count: int
    author_metadata_available: bool
    source: str | None = None
    label: str | None = None
    provider_needed_reasons: tuple[str, ...] = ()
    model_needed_reasons: tuple[str, ...] = ()
    review_reasons: tuple[str, ...] = ()

    def audit_record(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "row_id": self.row_id,
            "text_length": self.text_length,
            "baseline_changed": self.baseline_changed,
            "direct_identifier_count_before": self.direct_identifier_count_before,
            "direct_identifier_count_after": self.direct_identifier_count_after,
            "quasi_identifier_count_before": self.quasi_identifier_count_before,
            "quasi_identifier_count_after": self.quasi_identifier_count_after,
            "placeholder_count": self.placeholder_count,
            "target_cue_count_before_fast": self.target_cue_count_before_fast,
            "target_cue_retention_fast": self.target_cue_retention_fast,
            "utility_cue_retention_fast": self.utility_cue_retention_fast,
            "style_risk_count": self.style_risk_count,
            "author_metadata_available": self.author_metadata_available,
            "source": self.source,
            "label": self.label,
            "provider_needed_reasons": list(self.provider_needed_reasons),
            "model_needed_reasons": list(self.model_needed_reasons),
            "review_reasons": list(self.review_reasons),
        }


@dataclass(frozen=True)
class RowRoutingDecision:
    use_providers: bool
    use_token_policy: bool
    use_style_candidate: bool
    review_recommended: bool
    fallback_reason: str | None = None

    def audit_record(self) -> dict[str, Any]:
        return {
            "use_providers": self.use_providers,
            "use_token_policy": self.use_token_policy,
            "use_style_candidate": self.use_style_candidate,
            "review_recommended": self.review_recommended,
            "fallback_reason": self.fallback_reason,
        }


@dataclass
class AutoRowState:
    row: dict[str, str]
    row_index: int
    row_id: str
    original: str
    baseline: PrivatizationResult
    baseline_metrics: dict[str, Any]
    profile: RowRiskProfile
    decision: RowRoutingDecision
    provider_outputs: list[SpanProviderOutput] = field(default_factory=list)
    provider_candidates: list[SpanCandidate] = field(default_factory=list)
    model_outputs: list[SpanProviderOutput] = field(default_factory=list)
    model_candidates: list[SpanCandidate] = field(default_factory=list)
    provider_errors: list[dict[str, str]] = field(default_factory=list)
    model_errors: list[dict[str, str]] = field(default_factory=list)
