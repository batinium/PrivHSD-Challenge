"""Automatic CSV row orchestration."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from privhsd.metrics import aggregate_metrics, row_metric_fast, row_metric_for_depth
from privhsd.pipeline import PrivatizerConfig, privatize_text
from privhsd.rerank import length_drift, style_risk_count
from privhsd.span_providers.base import SpanCandidate

from .audit import row_audit_limit, status_summary
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
    character_retention = float(metrics.get("character_utility_retention", 1.0) or 1.0)
    target_retention = float(metrics.get("target_cue_retention", 1.0) or 1.0)
    utility_retention = float(metrics.get("utility_cue_retention", 1.0) or 1.0)
    hsd_advisory = candidate.metadata.get("hsd_advisory") or {}
    hsd_drop = float(hsd_advisory.get("score_drop", 0.0) or 0.0)
    hsd_abs_drift = float(hsd_advisory.get("abs_drift", 0.0) or 0.0)
    hsd_decision_changed = bool(hsd_advisory.get("decision_changed", False))
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
        if bool(hsd_advisory.get("large_drop", False)):
            hard_rejects.append("hsd_advisory_large_drop")
        if hsd_decision_changed and bool(hsd_advisory.get("large_abs_drift", False)):
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


class AutoPipelineEngine:
    def __init__(self, context: AutoPipelineContext) -> None:
        self.context = context

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

        self._run_provider_batches(states)
        self._run_token_policy_batch(states, text_col=text_col)
        candidate_groups = [
            (state, self._candidates_for_state(state))
            for state in states
        ]
        self._run_hsd_advisory_batch(candidate_groups)

        output_rows: list[dict[str, Any]] = []
        audit_rows: list[dict[str, Any]] = []
        metric_rows: list[dict[str, Any]] = []
        chosen_counts: Counter[str] = Counter()
        fallback_counts: Counter[str] = Counter()
        changed_count = 0
        for state, candidates in candidate_groups:
            chosen, scored, reason = choose_auto_candidate(
                state.original,
                candidates,
                baseline_metrics=state.baseline_metrics,
            )
            chosen_counts[chosen.name] += 1
            if reason.startswith("fallback"):
                fallback_counts[reason] += 1
            output_row = dict(state.row)
            output_row[target_col] = chosen.text
            output_rows.append(output_row)
            if state.original != chosen.text:
                changed_count += 1
            metrics = row_metric_for_depth(
                state.original,
                chosen.text,
                metric_depth=self.context.config.metric_depth,
                row_index=state.row_index,
            )
            metric_rows.append(metrics)
            audit_rows.append(
                self._row_audit(
                    state,
                    chosen=chosen,
                    scored=scored,
                    selection_reason=reason,
                    metrics=metrics,
                )
            )

        summary = {
            "artifact_type": "auto_csv_privatization",
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
            "providers": status_summary(self.context.provider_status),
            "models": status_summary(self.context.model_status),
            "load_counts": {
                "providers": dict(sorted(self.context.provider_load_counts.items())),
                "models": dict(sorted(self.context.model_load_counts.items())),
            },
            "metrics": aggregate_metrics(metric_rows),
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

    def _run_provider_batches(self, states: list[AutoRowState]) -> None:
        provider_rows = [state for state in states if state.decision.use_providers]
        max_rows = self.context.config.max_provider_rows
        if max_rows is not None:
            provider_rows = provider_rows[:max_rows]
        if not provider_rows:
            return
        providers = self.context.optional_span_providers()
        if not providers:
            for state in provider_rows:
                state.provider_errors.append(
                    {"provider": "auto", "error_class": "NoAvailableProvider"}
                )
            return
        for provider in providers:
            provider_name = getattr(provider, "name", "unknown")
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
    ) -> None:
        model_rows = [state for state in states if state.decision.use_token_policy]
        if not model_rows:
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
            return
        rows = [
            {**state.row, text_col: state.original}
            for state in model_rows
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
            for state in model_rows:
                state.model_errors.append(
                    {
                        "model": "token_policy_ensemble",
                        "error_class": type(exc).__name__,
                    }
                )
            return
        for state, output in zip(model_rows, outputs):
            state.model_outputs.append(output)
            state.model_candidates.extend(output.spans)

    def _run_hsd_advisory_batch(
        self,
        candidate_groups: list[tuple[AutoRowState, list[AutoCandidate]]],
    ) -> None:
        advisory_groups = [
            (state, candidates)
            for state, candidates in candidate_groups
            if len(candidates) > 1
        ]
        if not advisory_groups:
            return
        advisory = self.context.ensure_hsd_advisory()
        if advisory is None:
            return

        texts: list[str] = []
        for state, candidates in advisory_groups:
            texts.append(state.original)
            texts.extend(candidate.text for candidate in candidates)
        try:
            scores = advisory.score_texts(
                texts,
                batch_size=self.context.config.max_model_batch_size,
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
        if len(scores) != len(texts):
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
            original_score = scores[cursor]
            cursor += 1
            for candidate in candidates:
                candidate_score = scores[cursor]
                cursor += 1
                candidate.metadata["hsd_advisory"] = advisory.compare(
                    original_score,
                    candidate_score,
                )

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
        return self._dedupe_candidates(candidates)

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
        return {
            "row_id": state.row_id,
            "row_index": state.row_index,
            "chosen_candidate": chosen.name,
            "chosen_reason": selection_reason,
            "candidate_count": len(scored),
            "changed": state.original != chosen.text,
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
            or bool(state.model_errors),
        }
