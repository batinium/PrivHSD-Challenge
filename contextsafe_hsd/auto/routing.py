"""Cheap row routing rules for automatic mode."""

from __future__ import annotations

import re
from typing import Any

from contextsafe_hsd.metrics import row_metric_fast
from contextsafe_hsd.row_ids import report_row_id
from contextsafe_hsd.style import style_risk_count

from .row_state import RowRiskProfile, RowRoutingDecision


PERSON_AMBIGUITY_PATTERN = re.compile(
    r"\b(?:kill|threaten|call|called|email|emailed|dm|message|said|says|posted|reported)\s+"
    r"([A-Z][A-Za-z.'-]{2,}(?:\s+[A-Z][A-Za-z.'-]{2,}){0,2})\b"
)
QUASI_CONTEXT_PATTERN = re.compile(
    r"\b(?:from|near|at|in|works at|studies at|school at)\s+"
    r"[A-Z][A-Za-z0-9.'-]{2,}(?:\s+[A-Z][A-Za-z0-9.'-]{2,}){0,4}\b"
)
TARGET_AMBIGUITY_PATTERN = re.compile(r"(?:#\w{5,}|[A-Za-z0-9]\s+[A-Za-z0-9]\s+[A-Za-z0-9])")
STYLE_CANDIDATE_MIN_RISK = 2


def metric_float(metrics: dict[str, Any], key: str, default: float) -> float:
    value = metrics.get(key, default)
    if value is None:
        return default
    return float(value)


def row_id_for(
    row: dict[str, str],
    *,
    row_index: int,
    id_col: str | None,
) -> str:
    return report_row_id(row, row_index=row_index, id_col=id_col)


def cheap_profile(
    row: dict[str, str],
    *,
    row_index: int,
    id_col: str | None,
    text_col: str,
    baseline_text: str,
    source_col: str | None = None,
    label_col: str | None = None,
) -> tuple[RowRiskProfile, dict[str, Any]]:
    original = str(row.get(text_col, "") or "")
    metrics = row_metric_fast(original, baseline_text)
    provider_reasons: list[str] = []
    model_reasons: list[str] = []
    review_reasons: list[str] = []

    if int(metrics.get("direct_identifier_count_after", 0) or 0):
        provider_reasons.append("residual_direct_identifier")
        model_reasons.append("residual_direct_identifier")
    if int(metrics.get("quasi_identifier_count_after", 0) or 0):
        provider_reasons.append("residual_quasi_identifier")
        model_reasons.append("residual_quasi_identifier")
    if PERSON_AMBIGUITY_PATTERN.search(original):
        provider_reasons.append("provider_worthy_person_ambiguity")
    if QUASI_CONTEXT_PATTERN.search(original):
        provider_reasons.append("provider_worthy_quasi_context")

    style_count = style_risk_count(original)
    if style_count >= 2:
        model_reasons.append("high_style_risk")

    target_count = int(metrics.get("target_cue_count_before", 0) or 0)
    target_retention = metric_float(metrics, "target_cue_retention", 1.0)
    utility_retention = metric_float(metrics, "utility_cue_retention", 1.0)
    if target_count and target_retention < 1.0:
        model_reasons.append("target_cue_loss_risk")
        review_reasons.append("target_cue_loss_risk")
    if TARGET_AMBIGUITY_PATTERN.search(original):
        model_reasons.append("target_or_obfuscation_ambiguity")

    profile = RowRiskProfile(
        row_index=row_index,
        row_id=row_id_for(row, row_index=row_index, id_col=id_col),
        text_length=len(original),
        baseline_changed=original != baseline_text,
        direct_identifier_count_before=int(metrics.get("direct_identifier_count_before", 0) or 0),
        direct_identifier_count_after=int(metrics.get("direct_identifier_count_after", 0) or 0),
        quasi_identifier_count_before=int(metrics.get("quasi_identifier_count_before", 0) or 0),
        quasi_identifier_count_after=int(metrics.get("quasi_identifier_count_after", 0) or 0),
        placeholder_count=int(metrics.get("placeholder_count", 0) or 0),
        target_cue_count_before_fast=target_count,
        target_cue_retention_fast=round(target_retention, 4),
        utility_cue_retention_fast=round(utility_retention, 4),
        style_risk_count=style_count,
        author_metadata_available=bool(row.get("author") or row.get("author_id")),
        source=str(row.get(source_col, "") or "") if source_col else row.get("source"),
        label=str(row.get(label_col, "") or "") if label_col else row.get("label"),
        provider_needed_reasons=tuple(sorted(set(provider_reasons))),
        model_needed_reasons=tuple(sorted(set(model_reasons))),
        review_reasons=tuple(sorted(set(review_reasons))),
    )
    return profile, metrics


def route_row(profile: RowRiskProfile) -> RowRoutingDecision:
    use_providers = bool(profile.provider_needed_reasons)
    use_style_candidate = profile.style_risk_count >= STYLE_CANDIDATE_MIN_RISK
    review_recommended = bool(profile.review_reasons)
    risk_reasons: list[str] = []
    low_risk_reasons: list[str] = []
    if profile.direct_identifier_count_before:
        risk_reasons.append("deterministic_direct_identifier_detected")
    if profile.quasi_identifier_count_before:
        risk_reasons.append("deterministic_quasi_identifier_detected")
    if profile.baseline_changed:
        risk_reasons.append("deterministic_baseline_changed")
    risk_reasons.extend(profile.provider_needed_reasons)
    if use_style_candidate:
        risk_reasons.append("style_risk_threshold_met")
    risk_reasons.extend(profile.review_reasons)
    if not profile.direct_identifier_count_before:
        low_risk_reasons.append("no_deterministic_direct_identifier")
    if not profile.quasi_identifier_count_before:
        low_risk_reasons.append("no_deterministic_quasi_identifier")
    if not profile.provider_needed_reasons:
        low_risk_reasons.append("no_provider_worthy_ambiguity")
    if not use_style_candidate:
        low_risk_reasons.append("style_risk_below_threshold")
    if not profile.review_reasons:
        low_risk_reasons.append("no_cue_loss_review_signal")
    risk_level = (
        "low_privacy_style_risk"
        if (
            not profile.baseline_changed
            and not use_providers
            and not use_style_candidate
            and not review_recommended
        )
        else "routed_or_changed"
    )
    return RowRoutingDecision(
        use_providers=use_providers,
        use_style_candidate=use_style_candidate,
        review_recommended=review_recommended,
        risk_level=risk_level,
        risk_reasons=tuple(sorted(set(risk_reasons))),
        low_risk_reasons=tuple(low_risk_reasons),
        style_candidate_policy=(
            f"style_scrubbed candidates are generated only when "
            f"style_risk_count >= {STYLE_CANDIDATE_MIN_RISK}"
        ),
    )
