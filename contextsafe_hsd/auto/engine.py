"""Automatic CSV row orchestration."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from contextsafe_hsd.detectors import (
    HIGH_CONFIDENCE_DIRECT_TYPES,
    Span,
    detect_spans,
    merge_spans,
)
from contextsafe_hsd.metrics import aggregate_metrics, row_metric_fast, row_metric_for_depth
from contextsafe_hsd.pipeline import PrivatizerConfig, apply_replacements, privatize_text
from contextsafe_hsd.rerank import length_drift, style_risk_count
from contextsafe_hsd.span_providers.base import SpanCandidate

from .audit import (
    MEANING_PROTECTION_REJECTION_REASONS,
    author_risk_hook,
    build_stage_summary,
    row_audit_limit,
    status_summary,
)
from .context import AutoPipelineContext
from .row_state import AutoRowState
from .routing import cheap_profile, route_row


@dataclass(frozen=True)
class AutoCandidate:
    name: str
    text: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutoPipelineResult:
    rows: list[dict[str, Any]]
    fieldnames: list[str]
    summary: dict[str, Any]
    audit_rows: list[dict[str, Any]]


ProgressCallback = Callable[[dict[str, Any]], None]


STRICT_RESIDUAL_QUASI_SOURCES = frozenset({"context_location", "regex"})
STRICT_RESIDUAL_REGEX_QUASI_TYPES = frozenset({"AGE", "DATE", "ORGANIZATION"})


def provider_count(metadata: dict[str, Any]) -> int:
    return int(
        metadata.get(
            "provider_accepted_span_count",
            metadata.get("accepted_span_count", 0),
        )
        or 0
    )


def score_auto_candidate(
    original: str,
    candidate: AutoCandidate,
    *,
    baseline_metrics: dict[str, Any],
) -> dict[str, Any]:
    metrics = row_metric_fast(original, candidate.text)
    candidate_style = style_risk_count(candidate.text)
    original_style = style_risk_count(original)
    style_reduction = max(0, original_style - candidate_style)
    direct_reduction = max(
        0,
        int(baseline_metrics.get("direct_identifier_count_after", 0) or 0)
        - int(metrics.get("direct_identifier_count_after", 0) or 0),
    )
    quasi_reduction = max(
        0,
        int(baseline_metrics.get("quasi_identifier_count_after", 0) or 0)
        - int(metrics.get("quasi_identifier_count_after", 0) or 0),
    )
    accepted_provider_spans = provider_count(candidate.metadata)
    strict_cleanup = candidate.metadata.get("strict_residual_cleanup") or {}
    character_retention = float(metrics.get("character_utility_retention", 1.0) or 1.0)
    target_retention = float(metrics.get("target_cue_retention", 1.0) or 1.0)
    utility_retention = float(metrics.get("utility_cue_retention", 1.0) or 1.0)
    hsd_advisory = candidate.metadata.get("hsd_advisory") or {}
    hsd_drop = float(hsd_advisory.get("score_drop", 0.0) or 0.0)
    hsd_abs_drift = float(hsd_advisory.get("abs_drift", 0.0) or 0.0)
    hsd_decision_changed = bool(hsd_advisory.get("decision_changed", False))
    strict_cleanup_counts = strict_cleanup.get("counts_by_entity_type", {})
    hard_privacy_cleanup = direct_reduction > 0 and any(
        int(strict_cleanup_counts.get(entity_type, 0) or 0) > 0
        for entity_type in HIGH_CONFIDENCE_DIRECT_TYPES
    )
    drift = length_drift(original, candidate.text)
    hard_rejects: list[str] = []
    if candidate.name != "balanced":
        if target_retention < 1.0:
            hard_rejects.append("target_cue_loss")
        if utility_retention < 1.0:
            hard_rejects.append("utility_cue_loss")
        if int(metrics.get("direct_identifier_count_after", 0) or 0) > int(
            baseline_metrics.get("direct_identifier_count_after", 0) or 0
        ):
            hard_rejects.append("direct_identifier_increase")
        if int(metrics.get("privacy_identifier_count_after", 0) or 0) > int(
            metrics.get("privacy_identifier_count_before", 0) or 0
        ):
            hard_rejects.append("new_identifier_signal")
        if drift > 0.65:
            hard_rejects.append("length_drift")
        if not hard_privacy_cleanup and bool(hsd_advisory.get("large_drop", False)):
            hard_rejects.append("hsd_advisory_large_drop")
        if (
            not hard_privacy_cleanup
            and hsd_decision_changed
            and bool(hsd_advisory.get("large_abs_drift", False))
        ):
            hard_rejects.append("hsd_advisory_decision_drift")
    hsd_penalty = (
        hsd_drop * 2.0
        + hsd_abs_drift * 1.0
        + (0.75 if hsd_decision_changed else 0.0)
    )
    score = (
        direct_reduction * 4.0
        + quasi_reduction * 1.5
        + min(accepted_provider_spans, 4) * 0.7
        + style_reduction * 0.4
        + target_retention * 1.5
        + utility_retention * 1.5
        + character_retention
        - drift * 0.7
        - max(0, original_style - style_reduction) * 0.05
        - hsd_penalty
    )
    return {
        "name": candidate.name,
        "source": candidate.source,
        "score": round(score, 4),
        "accepted": not hard_rejects,
        "hard_reject_reasons": hard_rejects,
        "metrics": {
            "residual_identifier_count": metrics["residual_identifier_count"],
            "residual_direct_identifier_count": metrics["residual_direct_identifier_count"],
            "residual_quasi_identifier_count": metrics["residual_quasi_identifier_count"],
            "target_cue_retention": metrics["target_cue_retention"],
            "utility_cue_retention": metrics["utility_cue_retention"],
            "character_utility_retention": metrics["character_utility_retention"],
            "length_drift": round(drift, 4),
            "style_risk_count": candidate_style,
            "provider_accepted_span_count": accepted_provider_spans,
            "strict_residual_cleanup": strict_cleanup or None,
            "hard_privacy_cleanup": hard_privacy_cleanup,
            "hsd_advisory": hsd_advisory or None,
            "hsd_advisory_penalty": round(hsd_penalty, 4),
        },
    }


def choose_auto_candidate(
    original: str,
    candidates: list[AutoCandidate],
    *,
    baseline_metrics: dict[str, Any],
) -> tuple[AutoCandidate, list[dict[str, Any]], str]:
    scored = [
        score_auto_candidate(
            original,
            candidate,
            baseline_metrics=baseline_metrics,
        )
        for candidate in candidates
    ]
    baseline = candidates[0]
    baseline_score = scored[0]["score"]
    accepted_indices = [
        index for index, score in enumerate(scored) if bool(score["accepted"])
    ]
    if not accepted_indices:
        return baseline, scored, "fallback_balanced_no_accepted_candidate"
    best_index = max(
        accepted_indices,
        key=lambda index: (
            scored[index]["score"],
            -scored[index]["metrics"]["residual_direct_identifier_count"],
            -scored[index]["metrics"]["residual_quasi_identifier_count"],
            scored[index]["metrics"]["target_cue_retention"],
            scored[index]["metrics"]["utility_cue_retention"],
            scored[index]["metrics"]["character_utility_retention"],
            -len(candidates[index].text),
        ),
    )
    chosen = candidates[best_index]
    if chosen.name != "balanced" and scored[best_index]["score"] <= baseline_score:
        return baseline, scored, "fallback_balanced_uncertain_candidate"
    return chosen, scored, "selected_least_destructive_candidate"


def strict_residual_identifier_spans(text: str) -> list[Span]:
    """Residual spans safe enough for a stricter scored PII candidate.

    This intentionally does not mask every PERSON/LOCATION/ORG that a detector
    can see. High-confidence direct identifiers are always eligible; ambiguous
    people/places are eligible only when the deterministic detector found a
    strong private context such as self-identification, contact, street/place
    suffixes, or explicit location context.
    """

    spans: list[Span] = []
    for span in detect_spans(text, include_context=True, include_targets=False):
        if span.entity_type in HIGH_CONFIDENCE_DIRECT_TYPES:
            spans.append(span)
        elif span.entity_type in {"PERSON", "ALIAS"} and span.source in {
            "context_person",
            "context_alias",
        }:
            spans.append(span)
        elif (
            span.entity_type == "LOCATION"
            and span.source in STRICT_RESIDUAL_QUASI_SOURCES
        ):
            spans.append(span)
        elif (
            span.entity_type in STRICT_RESIDUAL_REGEX_QUASI_TYPES
            and span.source == "regex"
        ):
            spans.append(span)
    return merge_spans(spans)


def cleanup_strict_residuals(text: str) -> tuple[str, list[dict[str, Any]]]:
    spans = strict_residual_identifier_spans(text)
    if not spans:
        return text, []
    cleaned, transformations = apply_replacements(
        text,
        spans,
        PrivatizerConfig(mode="balanced", generalize_targets=False),
    )
    return cleaned, [dict(transformation) for transformation in transformations]


def cleanup_direct_residuals(text: str) -> tuple[str, list[dict[str, Any]]]:
    spans = [
        span
        for span in strict_residual_identifier_spans(text)
        if span.entity_type in HIGH_CONFIDENCE_DIRECT_TYPES
    ]
    if not spans:
        return text, []
    cleaned, transformations = apply_replacements(
        text,
        merge_spans(spans),
        PrivatizerConfig(mode="balanced", generalize_targets=False),
    )
    return cleaned, [dict(transformation) for transformation in transformations]


def strict_cleanup_summary(transformations: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(item.get("entity_type", "UNKNOWN")) for item in transformations)
    return {
        "cleanup_count": len(transformations),
        "counts_by_entity_type": dict(sorted(counts.items())),
    }


class AutoPipelineEngine:
    def __init__(self, context: AutoPipelineContext) -> None:
        self.context = context

    def _emit_progress(
        self,
        progress_callback: ProgressCallback | None,
        *,
        stage: str,
        processed: int = 0,
        total: int = 0,
        detail: str = "",
        **metadata: Any,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(
            {
                "stage": stage,
                "processed": processed,
                "total": total,
                "detail": detail,
                **metadata,
            }
        )

    def process_rows(
        self,
        rows: list[dict[str, str]],
        fieldnames: list[str],
        *,
        text_col: str,
        id_col: str | None = None,
        output_col: str = "privatized_text",
        replace_text: bool = False,
        source_col: str | None = None,
        label_col: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> AutoPipelineResult:
        config = self.context.config
        output_fieldnames = list(fieldnames)
        target_col = text_col if replace_text else output_col
        if not replace_text and target_col not in output_fieldnames:
            output_fieldnames.append(target_col)

        baseline_config = PrivatizerConfig(
            mode=config.baseline_mode,
            generalize_targets=config.generalize_targets,
            style_scrub=False,
        )
        states: list[AutoRowState] = []
        total_rows = len(rows)
        self._emit_progress(
            progress_callback,
            stage="baseline",
            processed=0,
            total=total_rows,
            detail="Building deterministic privacy baseline.",
        )
        for row_index, row in enumerate(rows, start=1):
            original = str(row.get(text_col, "") or "")
            baseline = privatize_text(original, baseline_config)
            profile, baseline_metrics = cheap_profile(
                row,
                row_index=row_index,
                id_col=id_col,
                text_col=text_col,
                baseline_text=baseline.text,
                source_col=source_col,
                label_col=label_col,
            )
            states.append(
                AutoRowState(
                    row=row,
                    row_index=row_index,
                    row_id=profile.row_id,
                    original=original,
                    baseline=baseline,
                    baseline_metrics=baseline_metrics,
                    profile=profile,
                    decision=route_row(profile),
                )
            )
            self._emit_progress(
                progress_callback,
                stage="baseline",
                processed=row_index,
                total=total_rows,
                detail="Built deterministic privacy baseline.",
                row_id=profile.row_id,
            )

        self._run_provider_batches(states, progress_callback=progress_callback)
        self._run_token_policy_batch(
            states,
            text_col=text_col,
            progress_callback=progress_callback,
        )
        candidate_groups = []
        self._emit_progress(
            progress_callback,
            stage="candidates",
            processed=0,
            total=total_rows,
            detail="Generating candidate masked outputs.",
        )
        for index, state in enumerate(states, start=1):
            candidate_groups.append((state, self._candidates_for_state(state)))
            self._emit_progress(
                progress_callback,
                stage="candidates",
                processed=index,
                total=total_rows,
                detail="Generated candidate masked outputs.",
                row_id=state.row_id,
            )
        self._run_hsd_advisory_batch(
            candidate_groups,
            progress_callback=progress_callback,
        )

        output_rows: list[dict[str, Any]] = []
        audit_rows: list[dict[str, Any]] = []
        metric_rows: list[dict[str, Any]] = []
        chosen_counts: Counter[str] = Counter()
        fallback_counts: Counter[str] = Counter()
        rejection_counts: Counter[str] = Counter()
        changed_count = 0
        candidate_count = 0
        rejected_candidate_count = 0
        candidate_name_counts: Counter[str] = Counter()
        hsd_advisory_comparison_count = 0
        residual_review_required_count = 0
        residual_direct_cleanup_count = 0
        self._emit_progress(
            progress_callback,
            stage="selection",
            processed=0,
            total=total_rows,
            detail="Selecting final masked output and computing row metrics.",
        )
        for row_number, (state, candidates) in enumerate(candidate_groups, start=1):
            chosen, scored, reason = choose_auto_candidate(
                state.original,
                candidates,
                baseline_metrics=state.baseline_metrics,
            )
            candidate_count += len(scored)
            for score in scored:
                candidate_name_counts[str(score.get("name", "unknown"))] += 1
                if score.get("accepted") is False:
                    rejected_candidate_count += 1
                for reject_reason in score.get("hard_reject_reasons", []):
                    rejection_counts[str(reject_reason)] += 1
                if score.get("metrics", {}).get("hsd_advisory"):
                    hsd_advisory_comparison_count += 1
            chosen_counts[chosen.name] += 1
            if reason.startswith("fallback"):
                fallback_counts[reason] += 1
            chosen_text, residual_cleanup = cleanup_direct_residuals(chosen.text)
            residual_direct_cleanup_count += len(residual_cleanup)
            output_row = dict(state.row)
            output_row[target_col] = chosen_text
            output_rows.append(output_row)
            if state.original != chosen_text:
                changed_count += 1
            metrics = row_metric_for_depth(
                state.original,
                chosen_text,
                metric_depth=self.context.config.metric_depth,
                row_index=state.row_index,
            )
            metric_rows.append(metrics)
            residual_review_required = bool(metrics.get("privacy_warnings")) or int(
                metrics.get("residual_identifier_count", 0) or 0
            ) > 0
            if residual_review_required:
                residual_review_required_count += 1
            audit_rows.append(
                self._row_audit(
                    state,
                    chosen=chosen,
                    scored=scored,
                    selection_reason=reason,
                    metrics=metrics,
                    residual_review_required=residual_review_required,
                    chosen_text=chosen_text,
                    residual_cleanup=residual_cleanup,
                )
            )
            self._emit_progress(
                progress_callback,
                stage="selection",
                processed=row_number,
                total=total_rows,
                detail="Selected final masked output and computed row metrics.",
                row_id=state.row_id,
            )

        self._emit_progress(
            progress_callback,
            stage="summary",
            processed=0,
            total=0,
            detail="Aggregating audit metrics.",
        )
        metrics = aggregate_metrics(metric_rows)
        provider_rows_considered = sum(1 for state in states if state.decision.use_providers)
        if config.max_provider_rows is not None:
            provider_rows_considered = min(provider_rows_considered, config.max_provider_rows)
        token_policy_rows_considered = sum(
            1 for state in states if state.decision.use_token_policy
        )
        stage_summary = build_stage_summary(
            config=config,
            row_count=len(rows),
            changed_text_cells=changed_count,
            chosen_counts=chosen_counts,
            fallback_counts=fallback_counts,
            provider_statuses=self.context.provider_status,
            model_statuses=self.context.model_status,
            provider_load_counts=self.context.provider_load_counts,
            model_load_counts=self.context.model_load_counts,
            audit_counters=self.context.audit_counters,
            metrics=metrics,
            provider_rows_considered=provider_rows_considered,
            token_policy_rows_considered=token_policy_rows_considered,
            candidate_count=candidate_count,
            candidate_name_counts=candidate_name_counts,
            rejected_candidate_count=rejected_candidate_count,
            rejection_counts=rejection_counts,
            hsd_advisory_comparison_count=hsd_advisory_comparison_count,
            residual_review_required_count=residual_review_required_count,
            residual_direct_cleanup_count=residual_direct_cleanup_count,
            author_risk=author_risk_hook(
                fieldnames,
                rows,
                author_metadata_rows=sum(
                    1 for state in states if state.profile.author_metadata_available
                ),
            ),
        )
        summary = {
            "artifact_type": "auto_csv_privatization",
            "pipeline": "auto",
            "row_count": len(rows),
            "text_col": text_col,
            "id_col": id_col,
            "output_col": target_col,
            "replace_text": replace_text,
            "mode": "auto",
            "baseline_mode": config.baseline_mode,
            "metric_depth": config.metric_depth,
            "changed_text_cells": changed_count,
            "chosen_counts": dict(sorted(chosen_counts.items())),
            "fallback_counts": dict(sorted(fallback_counts.items())),
            "stages": stage_summary,
            "providers": status_summary(self.context.provider_status),
            "models": status_summary(self.context.model_status),
            "load_counts": {
                "providers": dict(sorted(self.context.provider_load_counts.items())),
                "models": dict(sorted(self.context.model_load_counts.items())),
            },
            "metrics": metrics,
        }
        return AutoPipelineResult(
            rows=output_rows,
            fieldnames=output_fieldnames,
            summary=summary,
            audit_rows=row_audit_limit(
                audit_rows,
                audit_level=self.context.config.audit_level,
            ),
        )

    def _run_provider_batches(
        self,
        states: list[AutoRowState],
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        provider_rows = [state for state in states if state.decision.use_providers]
        max_rows = self.context.config.max_provider_rows
        if max_rows is not None:
            provider_rows = provider_rows[:max_rows]
        self._emit_progress(
            progress_callback,
            stage="providers",
            processed=0,
            total=len(provider_rows),
            detail="Checking optional PII providers.",
        )
        if not provider_rows:
            self._emit_progress(
                progress_callback,
                stage="providers",
                processed=0,
                total=0,
                detail="No rows needed optional PII providers.",
            )
            return
        providers = self.context.optional_span_providers()
        if not providers:
            for state in provider_rows:
                state.provider_errors.append(
                    {"provider": "auto", "error_class": "NoAvailableProvider"}
                )
            self._emit_progress(
                progress_callback,
                stage="providers",
                processed=len(provider_rows),
                total=len(provider_rows),
                detail="Optional PII providers were unavailable.",
            )
            return
        provider_total = len(providers)
        for provider_number, provider in enumerate(providers, start=1):
            provider_name = getattr(provider, "name", "unknown")
            if progress_callback is not None:
                self._emit_progress(
                    progress_callback,
                    stage="providers",
                    processed=0,
                    total=len(provider_rows),
                    detail=f"Running {provider_name} PII provider.",
                    provider=provider_name,
                    provider_index=provider_number,
                    provider_total=provider_total,
                )
                for row_number, state in enumerate(provider_rows, start=1):
                    try:
                        output = provider.propose(state.original)
                    except Exception as exc:
                        state.provider_errors.append(
                            {
                                "provider": provider_name,
                                "error_class": type(exc).__name__,
                            }
                        )
                        self.context.audit_counters[
                            f"provider_runtime_error:{provider_name}:{type(exc).__name__}"
                        ] += 1
                    else:
                        state.provider_outputs.append(output)
                        state.provider_candidates.extend(output.spans)
                    self._emit_progress(
                        progress_callback,
                        stage="providers",
                        processed=row_number,
                        total=len(provider_rows),
                        detail=f"Ran {provider_name} PII provider.",
                        row_id=state.row_id,
                        provider=provider_name,
                        provider_index=provider_number,
                        provider_total=provider_total,
                    )
                continue
            propose_many = getattr(provider, "propose_many", None)
            if callable(propose_many):
                texts = [state.original for state in provider_rows]
                try:
                    outputs = propose_many(
                        texts,
                        batch_size=self.context.config.max_model_batch_size,
                    )
                except Exception as exc:
                    for state in provider_rows:
                        state.provider_errors.append(
                            {
                                "provider": provider_name,
                                "error_class": type(exc).__name__,
                            }
                        )
                    self.context.audit_counters[
                        f"provider_runtime_error:{provider_name}:{type(exc).__name__}"
                    ] += 1
                    continue
                if len(outputs) != len(provider_rows):
                    for state in provider_rows:
                        state.provider_errors.append(
                            {
                                "provider": provider_name,
                                "error_class": "UnexpectedOutputCount",
                            }
                        )
                    self.context.audit_counters[
                        f"provider_runtime_error:{provider_name}:UnexpectedOutputCount"
                    ] += 1
                    continue
                for state, output in zip(provider_rows, outputs):
                    state.provider_outputs.append(output)
                    state.provider_candidates.extend(output.spans)
                continue
            for state in provider_rows:
                try:
                    output = provider.propose(state.original)
                except Exception as exc:
                    state.provider_errors.append(
                        {
                            "provider": provider_name,
                            "error_class": type(exc).__name__,
                        }
                    )
                    self.context.audit_counters[
                        f"provider_runtime_error:{provider_name}:{type(exc).__name__}"
                    ] += 1
                    continue
                state.provider_outputs.append(output)
                state.provider_candidates.extend(output.spans)

    def _run_token_policy_batch(
        self,
        states: list[AutoRowState],
        *,
        text_col: str,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        model_rows = [state for state in states if state.decision.use_token_policy]
        self._emit_progress(
            progress_callback,
            stage="token_policy",
            processed=0,
            total=len(model_rows),
            detail="Checking token-policy model candidates.",
        )
        if not model_rows:
            self._emit_progress(
                progress_callback,
                stage="token_policy",
                processed=0,
                total=0,
                detail="No rows needed token-policy model candidates.",
            )
            return
        token_provider = self.context.ensure_token_policy_provider()
        if token_provider is None:
            for state in model_rows:
                state.model_errors.append(
                    {
                        "model": "token_policy_ensemble",
                        "error_class": "UnavailableModel",
                    }
                )
            self._emit_progress(
                progress_callback,
                stage="token_policy",
                processed=len(model_rows),
                total=len(model_rows),
                detail="Token-policy model was unavailable.",
            )
            return
        chunk_size = (
            self.context.config.max_model_batch_size
            if progress_callback is not None
            else len(model_rows)
        )
        processed_rows = 0
        for start in range(0, len(model_rows), max(1, chunk_size)):
            chunk = model_rows[start : start + max(1, chunk_size)]
            rows = [
                {**state.row, text_col: state.original}
                for state in chunk
            ]
            try:
                outputs = token_provider.propose_many(
                    rows,
                    text_col=text_col,
                    batch_size=self.context.config.max_model_batch_size,
                )
            except Exception as exc:
                self.context.audit_counters[
                    f"model_runtime_error:token_policy_ensemble:{type(exc).__name__}"
                ] += 1
                for state in chunk:
                    state.model_errors.append(
                        {
                            "model": "token_policy_ensemble",
                            "error_class": type(exc).__name__,
                        }
                    )
                processed_rows += len(chunk)
                self._emit_progress(
                    progress_callback,
                    stage="token_policy",
                    processed=processed_rows,
                    total=len(model_rows),
                    detail="Token-policy model candidate check encountered an error.",
                )
                continue
            for state, output in zip(chunk, outputs):
                state.model_outputs.append(output)
                state.model_candidates.extend(output.spans)
            processed_rows += len(chunk)
            self._emit_progress(
                progress_callback,
                stage="token_policy",
                processed=processed_rows,
                total=len(model_rows),
                detail="Checked token-policy model candidates.",
            )

    def _run_hsd_advisory_batch(
        self,
        candidate_groups: list[tuple[AutoRowState, list[AutoCandidate]]],
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        advisory_groups = [
            (state, candidates)
            for state, candidates in candidate_groups
            if candidates
        ]
        self._emit_progress(
            progress_callback,
            stage="hsd_advisory",
            processed=0,
            total=len(advisory_groups),
            detail="Checking HSD preservation across masked candidates.",
        )
        if not advisory_groups:
            self._emit_progress(
                progress_callback,
                stage="hsd_advisory",
                processed=0,
                total=0,
                detail="No HSD advisory comparisons were needed.",
            )
            return
        advisory = self.context.ensure_hsd_advisory()
        if advisory is None:
            self._emit_progress(
                progress_callback,
                stage="hsd_advisory",
                processed=len(advisory_groups),
                total=len(advisory_groups),
                detail="HSD advisory model was unavailable.",
            )
            return

        if progress_callback is not None:
            chunk_size = min(self.context.config.max_model_batch_size, 8)
            processed_rows = 0
            for start in range(0, len(advisory_groups), max(1, chunk_size)):
                chunk = advisory_groups[start : start + max(1, chunk_size)]
                self._score_hsd_advisory_groups(advisory, chunk)
                processed_rows += len(chunk)
                self._emit_progress(
                    progress_callback,
                    stage="hsd_advisory",
                    processed=processed_rows,
                    total=len(advisory_groups),
                    detail="Checked HSD preservation across masked candidates.",
                )
            return

        self._score_hsd_advisory_groups(advisory, advisory_groups)

    def _score_hsd_advisory_groups(
        self,
        advisory: Any,
        advisory_groups: list[tuple[AutoRowState, list[AutoCandidate]]],
    ) -> None:
        texts: list[str] = []
        for state, candidates in advisory_groups:
            texts.append(state.original)
            texts.extend(candidate.text for candidate in candidates)
        try:
            score_by_model = self._score_hsd_advisory(
                advisory,
                texts,
            )
        except Exception as exc:
            self.context.audit_counters[
                f"model_runtime_error:hsd_advisory:{type(exc).__name__}"
            ] += 1
            for state, _candidates in advisory_groups:
                state.model_errors.append(
                    {
                        "model": "hsd_advisory",
                        "error_class": type(exc).__name__,
                    }
                )
            return
        if any(len(scores) != len(texts) for scores in score_by_model.values()):
            self.context.audit_counters[
                "model_runtime_error:hsd_advisory:UnexpectedScoreCount"
            ] += 1
            for state, _candidates in advisory_groups:
                state.model_errors.append(
                    {
                        "model": "hsd_advisory",
                        "error_class": "UnexpectedScoreCount",
                    }
                )
            return

        cursor = 0
        for _state, candidates in advisory_groups:
            original_scores = {
                model_id: scores[cursor]
                for model_id, scores in score_by_model.items()
            }
            cursor += 1
            for candidate in candidates:
                candidate_scores = {
                    model_id: scores[cursor]
                    for model_id, scores in score_by_model.items()
                }
                cursor += 1
                candidate.metadata["hsd_advisory"] = self._compare_hsd_advisory(
                    advisory,
                    original_scores,
                    candidate_scores,
                )

    def _score_hsd_advisory(
        self,
        advisory: Any,
        texts: list[str],
    ) -> dict[str, list[float]]:
        score_by_model = getattr(advisory, "score_texts_by_model", None)
        if callable(score_by_model):
            return score_by_model(
                texts,
                batch_size=self.context.config.max_model_batch_size,
            )
        return {
            "hsd_advisory": advisory.score_texts(
                texts,
                batch_size=self.context.config.max_model_batch_size,
            )
        }

    def _compare_hsd_advisory(
        self,
        advisory: Any,
        original_scores: dict[str, float],
        candidate_scores: dict[str, float],
    ) -> dict[str, Any]:
        compare_by_model = getattr(advisory, "compare_scores_by_model", None)
        if callable(compare_by_model):
            return compare_by_model(original_scores, candidate_scores)
        common_models = [
            model_id
            for model_id in original_scores
            if model_id in candidate_scores
        ]
        if not common_models:
            common_models = ["hsd_advisory"]
            original_scores = {"hsd_advisory": 0.0}
            candidate_scores = {"hsd_advisory": 0.0}
        original_score = sum(
            float(original_scores[model_id]) for model_id in common_models
        ) / len(common_models)
        candidate_score = sum(
            float(candidate_scores[model_id]) for model_id in common_models
        ) / len(common_models)
        compare = getattr(advisory, "compare", None)
        if callable(compare):
            return compare(original_score, candidate_score)
        decision_threshold = float(getattr(advisory, "decision_threshold", 0.5))
        large_drop_threshold = float(getattr(advisory, "large_drop_threshold", 0.20))
        max_abs_drift = float(getattr(advisory, "max_abs_drift", 0.35))
        delta = candidate_score - original_score
        abs_drift = abs(delta)
        score_drop = max(0.0, original_score - candidate_score)
        original_decision = original_score >= decision_threshold
        candidate_decision = candidate_score >= decision_threshold
        return {
            "model_id": "hsd_advisory",
            "original_score": round(float(original_score), 4),
            "candidate_score": round(float(candidate_score), 4),
            "score_delta": round(float(delta), 4),
            "score_drop": round(float(score_drop), 4),
            "abs_drift": round(float(abs_drift), 4),
            "original_decision": "positive" if original_decision else "negative",
            "candidate_decision": "positive" if candidate_decision else "negative",
            "decision_changed": original_decision != candidate_decision,
            "large_drop": original_decision and score_drop >= large_drop_threshold,
            "large_abs_drift": abs_drift >= max_abs_drift,
            "decision_threshold": decision_threshold,
            "large_drop_threshold": large_drop_threshold,
            "max_abs_drift": max_abs_drift,
            "model_count": len(common_models),
            "models": {
                model_id: {
                    "model_id": model_id,
                    "original_score": round(float(original_scores[model_id]), 4),
                    "candidate_score": round(float(candidate_scores[model_id]), 4),
                }
                for model_id in common_models
            },
            "original_positive_model_count": sum(
                float(original_scores[model_id]) >= decision_threshold
                for model_id in common_models
            ),
            "candidate_positive_model_count": sum(
                float(candidate_scores[model_id]) >= decision_threshold
                for model_id in common_models
            ),
            "original_max_score": round(
                max(float(original_scores[model_id]) for model_id in common_models),
                4,
            ),
            "candidate_max_score": round(
                max(float(candidate_scores[model_id]) for model_id in common_models),
                4,
            ),
        }

    def _candidates_for_state(self, state: AutoRowState) -> list[AutoCandidate]:
        candidates = [
            AutoCandidate(
                name="balanced",
                text=state.baseline.text,
                source="deterministic",
                metadata={},
            )
        ]
        if state.decision.use_style_candidate or self.context.config.style_scrub:
            style_result = privatize_text(
                state.original,
                PrivatizerConfig(
                    mode=self.context.config.baseline_mode,
                    generalize_targets=self.context.config.generalize_targets,
                    style_scrub=True,
                ),
            )
            candidates.append(
                AutoCandidate(
                    name="style_scrubbed",
                    text=style_result.text,
                    source="deterministic",
                    metadata={"style_scrub": style_result.metrics},
                )
            )
        if state.provider_candidates:
            candidates.append(
                self._candidate_from_spans(
                    state,
                    name="provider_fusion_augmented",
                    source="provider_fusion",
                    spans=state.provider_candidates,
                )
            )
        if state.model_candidates:
            candidates.append(
                self._candidate_from_spans(
                    state,
                    name="token_policy_candidate",
                    source="token_policy_ensemble",
                    spans=state.model_candidates,
                )
            )
        return self._with_strict_residual_cleanup_candidates(candidates)

    def _with_strict_residual_cleanup_candidates(
        self,
        candidates: list[AutoCandidate],
    ) -> list[AutoCandidate]:
        expanded = self._dedupe_candidates(candidates)
        for candidate in list(expanded):
            cleaned, transformations = cleanup_strict_residuals(candidate.text)
            if not transformations or cleaned == candidate.text:
                continue
            metadata = dict(candidate.metadata)
            metadata["strict_residual_cleanup"] = strict_cleanup_summary(
                transformations
            )
            expanded.append(
                AutoCandidate(
                    name=f"{candidate.name}_strict_pii",
                    text=cleaned,
                    source=f"{candidate.source}+strict_residual_cleanup",
                    metadata=metadata,
                )
            )
        return self._dedupe_candidates(expanded)

    def _candidate_from_spans(
        self,
        state: AutoRowState,
        *,
        name: str,
        source: str,
        spans: list[SpanCandidate],
    ) -> AutoCandidate:
        result = privatize_text(
            state.original,
            PrivatizerConfig(
                mode=self.context.config.baseline_mode,
                generalize_targets=self.context.config.generalize_targets,
            ),
            provider_candidates=spans,
        )
        return AutoCandidate(
            name=name,
            text=result.text,
            source=source,
            metadata={
                "accepted_span_count": result.provider_audit.get("fusion", {}).get(
                    "accepted_span_count",
                    0,
                ),
                "provider_fusion": result.provider_audit,
            },
        )

    def _dedupe_candidates(self, candidates: list[AutoCandidate]) -> list[AutoCandidate]:
        seen: set[tuple[str, str]] = set()
        deduped: list[AutoCandidate] = []
        for candidate in candidates:
            key = (candidate.name, candidate.text)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def _row_audit(
        self,
        state: AutoRowState,
        *,
        chosen: AutoCandidate,
        scored: list[dict[str, Any]],
        selection_reason: str,
        metrics: dict[str, Any],
        residual_review_required: bool,
        chosen_text: str,
        residual_cleanup: list[dict[str, Any]],
    ) -> dict[str, Any]:
        accepted_provider_counts = Counter(
            output.provider
            for output in state.provider_outputs
            if output.spans
        )
        accepted_model_counts = Counter(
            output.provider
            for output in state.model_outputs
            if output.spans
        )
        meaning_protection_rejections = [
            {
                "candidate": str(score.get("name", "unknown")),
                "reasons": [
                    reason
                    for reason in score.get("hard_reject_reasons", [])
                    if reason in MEANING_PROTECTION_REJECTION_REASONS
                ],
            }
            for score in scored
            if any(
                reason in MEANING_PROTECTION_REJECTION_REASONS
                for reason in score.get("hard_reject_reasons", [])
            )
        ]
        return {
            "row_id": state.row_id,
            "row_index": state.row_index,
            "chosen_candidate": chosen.name,
            "chosen_reason": selection_reason,
            "why_chosen": selection_reason,
            "privacy_gain": metrics.get("privacy_gain"),
            "meaning_protection_rejections": meaning_protection_rejections,
            "residual_review_required": residual_review_required,
            "residual_direct_cleanup_count": len(residual_cleanup),
            "residual_direct_cleanup": residual_cleanup,
            "residual_identifier_count": metrics.get("residual_identifier_count", 0),
            "residual_direct_identifier_count": metrics.get(
                "residual_direct_identifier_count",
                0,
            ),
            "residual_quasi_identifier_count": metrics.get(
                "residual_quasi_identifier_count",
                0,
            ),
            "candidate_count": len(scored),
            "changed": state.original != chosen_text,
            "risk_profile": state.profile.audit_record(),
            "routing": state.decision.audit_record(),
            "accepted_provider_spans_by_provider": dict(
                sorted(accepted_provider_counts.items())
            ),
            "accepted_model_spans_by_provider": dict(sorted(accepted_model_counts.items())),
            "provider_errors": state.provider_errors,
            "model_errors": state.model_errors,
            "scores": scored,
            "metrics": metrics,
            "review_recommended": state.decision.review_recommended
            or bool(state.provider_errors)
            or bool(state.model_errors)
            or residual_review_required,
        }
