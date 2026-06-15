"""Raw-text-free auto pipeline audit helpers."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


PII_ASSIST_COMPONENTS = ("presidio", "scrubadub")
AUTHOR_COLUMN_NAMES = frozenset(
    {
        "author",
        "author_id",
        "user",
        "user_id",
        "username",
        "screen_name",
        "handle",
    }
)
MEANING_PROTECTION_REJECTION_REASONS = frozenset(
    {"target_cue_loss", "utility_cue_loss"}
)


def status_summary(statuses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(status.get("status", "unknown")) for status in statuses.values())
    return {
        "counts_by_status": dict(sorted(counts.items())),
        "items": statuses,
    }


def row_audit_limit(rows: Iterable[dict[str, Any]], *, audit_level: str) -> list[dict[str, Any]]:
    materialized = list(rows)
    if audit_level == "summary":
        return materialized[:100]
    if audit_level == "row":
        return materialized
    return materialized


def status_value(statuses: dict[str, dict[str, Any]], name: str) -> str:
    return str(statuses.get(name, {}).get("status", "unknown"))


def pii_assist_summary(
    provider_statuses: dict[str, dict[str, Any]],
    provider_load_counts: Counter[str],
) -> dict[str, Any]:
    components: dict[str, str] = {}
    component_details: dict[str, dict[str, Any]] = {}
    component_names = list(PII_ASSIST_COMPONENTS)
    for name in component_names:
        status = provider_statuses.get(name, {})
        status_name = str(status.get("status", "unknown"))
        components[name] = status_name
        detail: dict[str, Any] = {
            "status": status_name,
            "load_count": int(provider_load_counts.get(name, 0)),
        }
        for key in ("kind", "model", "profile", "local_only", "missing", "detail"):
            if key in status:
                detail[key] = status[key]
        component_details[name] = detail
    enabled = any(
        status in {"available", "ready", "download_allowed"}
        for status in components.values()
    )
    return {
        "label": "PII Assist",
        "enabled": enabled,
        "components": components,
        "component_details": component_details,
    }


def author_risk_hook(
    fieldnames: list[str],
    rows: list[dict[str, str]],
    *,
    author_metadata_rows: int,
) -> dict[str, Any]:
    author_columns = [
        column
        for column in fieldnames
        if column.strip().lower() in AUTHOR_COLUMN_NAMES
    ]
    repeated_author_data_available = False
    if author_columns:
        author_col = author_columns[0]
        counts = Counter(
            str(row.get(author_col, "") or "").strip()
            for row in rows
            if str(row.get(author_col, "") or "").strip()
        )
        repeated_author_data_available = any(count > 1 for count in counts.values())
    return {
        "author_or_user_column_exists": bool(author_columns),
        "author_columns": author_columns,
        "author_metadata_rows": author_metadata_rows,
        "repeated_author_data_available": repeated_author_data_available,
        "author_risk_evaluation_ran": False,
        "skipped_reason": "not_run_manifest_hook_only"
        if author_columns
        else "missing_author_or_user_column",
    }


def build_stage_summary(
    *,
    config: Any,
    row_count: int,
    changed_text_cells: int,
    chosen_counts: Counter[str],
    fallback_counts: Counter[str],
    provider_statuses: dict[str, dict[str, Any]],
    model_statuses: dict[str, dict[str, Any]],
    provider_load_counts: Counter[str],
    model_load_counts: Counter[str],
    audit_counters: Counter[str],
    metrics: dict[str, Any],
    provider_rows_considered: int,
    candidate_count: int,
    candidate_name_counts: Counter[str],
    rejected_candidate_count: int,
    rejection_counts: Counter[str],
    residual_review_required_count: int,
    residual_direct_cleanup_count: int,
    author_group_masking: dict[str, Any],
    author_risk: dict[str, Any],
) -> dict[str, Any]:
    meaning_rejection_counts = Counter(
        {
            reason: count
            for reason, count in rejection_counts.items()
            if reason in MEANING_PROTECTION_REJECTION_REASONS
        }
    )
    privacy_ladder_order = [
        "deterministic_baseline",
        "strict_residual_pii_cleanup",
        "pii_assist",
    ]
    meaning_protection = {
        "protected_cue_policy": (
            "target_action_negation_modality_quote_counterspeech_reporting"
        ),
        "candidate_count": candidate_count,
        "rejected_candidate_count": rejected_candidate_count,
        "cue_loss_rejections": int(sum(meaning_rejection_counts.values())),
        "rejection_counts": dict(sorted(meaning_rejection_counts.items())),
        "target_cue_retention_mean": metrics.get("target_cue_retention_mean"),
        "target_term_retention_mean": metrics.get("target_term_retention_mean"),
        "utility_cue_retention_mean": metrics.get("utility_cue_retention_mean"),
        "character_utility_retention_mean": metrics.get(
            "character_utility_retention_mean"
        ),
    }
    return {
        "privacy_detection": {
            "baseline": f"deterministic_{config.baseline_mode}",
            "privacy_ladder": {
                "order": privacy_ladder_order,
                "strict_residual_pii_cleanup": {
                    "policy": (
                        "score stricter residual cleanup candidates before final "
                        "selection; high-confidence direct identifiers are eligible "
                        "by default, while ambiguous person/place/org residuals need "
                        "strong deterministic context"
                    ),
                    "candidate_count": sum(
                        count
                        for name, count in candidate_name_counts.items()
                        if name.endswith("_strict_pii")
                    ),
                },
            },
            "deterministic_baseline": {
                "status": status_value(provider_statuses, "deterministic"),
                "mode": config.baseline_mode,
                "always_run": True,
            },
            "pii_assist": pii_assist_summary(
                provider_statuses,
                provider_load_counts,
            ),
            "rows_considered_for_pii_assist": provider_rows_considered,
            "chosen_candidate_counts": dict(sorted(chosen_counts.items())),
            "candidate_counts_by_name": dict(sorted(candidate_name_counts.items())),
            "fallback_counts": dict(sorted(fallback_counts.items())),
            "changed_text_cells": changed_text_cells,
            "privacy_gain_mean": metrics.get("privacy_gain_mean", 0.0),
        },
        "meaning_protection": meaning_protection,
        "verification": {
            "residual_identifier_count": metrics.get("residual_identifier_count", 0),
            "residual_direct_identifier_count": metrics.get(
                "residual_direct_identifier_count",
                0,
            ),
            "residual_quasi_identifier_count": metrics.get(
                "residual_quasi_identifier_count",
                0,
            ),
            "residual_direct_cleanup_count": residual_direct_cleanup_count,
            "residual_review_required_rows": residual_review_required_count,
            "privacy_warning_counts": metrics.get("privacy_warning_counts", {}),
            "overmasking_warning_counts": metrics.get("overmasking_warning_counts", {}),
            "author_group_masking": author_group_masking,
            "metadata_leakage_status": "not_run",
            "metadata_leakage": {
                "status": "not_run",
                "skipped_reason": "metadata_columns_not_supplied_to_auto_engine",
            },
            "author_risk_status": "skipped",
            "author_risk": author_risk,
            "row_count": row_count,
        },
    }
