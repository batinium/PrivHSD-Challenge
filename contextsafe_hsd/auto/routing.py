"""Cheap row routing rules for automatic mode."""

from __future__ import annotations

import re
from typing import Any

from contextsafe_hsd.metrics import row_metric_fast
from contextsafe_hsd.rerank import style_risk_count
from contextsafe_hsd.row_ids import report_row_id

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
    target_retention = float(metrics.get("target_cue_retention", 1.0) or 1.0)
    utility_retention = float(metrics.get("utility_cue_retention", 1.0) or 1.0)
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
    use_style_candidate = profile.style_risk_count >= 2
    use_token_policy = bool(profile.model_needed_reasons)
    review_recommended = bool(profile.review_reasons)
    return RowRoutingDecision(
        use_providers=use_providers,
        use_token_policy=use_token_policy,
        use_style_candidate=use_style_candidate,
        review_recommended=review_recommended,
    )
