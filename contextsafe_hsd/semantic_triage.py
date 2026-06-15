"""Semantic review triage for privatized HSD datasets.

The report ranks rows that deserve model or human semantic review after
privatization. It does not rewrite text and does not include raw text.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from .classifier import ClassifierError, load_model
from .context import analyze_context
from .csv_pipeline import read_csv, write_csv, write_json
from .cue_checks import DEFAULT_RETENTION_THRESHOLD, cue_terms, row_cue_report
from .metrics import row_metric
from .row_ids import report_row_id


DEFAULT_LOW_CONFIDENCE = 0.65
DEFAULT_LOW_MARGIN = 0.20
DEFAULT_CONFIDENCE_DROP = 0.20
DEFAULT_MAX_REVIEW_ROWS = 1000
DEFAULT_SAMPLE_SIZE = 0
DEFAULT_SAMPLE_STRATEGY = "first_n"
DEFAULT_PRIVACY_SCAN = "changed"
PRIVACY_SCAN_MODES = frozenset({"all", "changed", "none"})
SAMPLE_STRATEGIES = frozenset({"first_n", "source_label_round_robin"})

AMBIGUOUS_LABELS = frozenset({"ambiguous", "ambiguous_abuse"})
ADJACENT_LABELS = frozenset(
    {
        "offensive",
        "toxic",
        "abuse",
        "not_abuse",
        "not_abusive",
    }
)
SEMANTIC_REVIEW_TAGS = frozenset(
    {
        "negated_hate",
        "counterspeech",
        "quoted_or_reported",
        "public_interest_or_institutional_criticism",
        "offensive_only_risk",
    }
)
HARD_CONTEXT_TAGS = frozenset(
    {
        "protected_target",
        "historical_victim_group",
        "hostile_action",
        "threat",
        "dehumanization",
        "exclusion",
        "negated_hate",
        "counterspeech",
        "quoted_or_reported",
        "public_interest_or_institutional_criticism",
        "offensive_only_risk",
    }
)


class SemanticTriageError(ValueError):
    pass


def rounded(value: float) -> float:
    return round(float(value), 4)


def validate_columns(
    input_path: Path,
    fieldnames: list[str],
    *,
    text_col: str,
    privatized_col: str,
    id_col: str | None,
    label_col: str | None,
    source_col: str | None,
) -> None:
    missing = [
        column
        for column in (text_col, privatized_col, id_col, label_col, source_col)
        if column and column not in fieldnames
    ]
    if missing:
        raise SemanticTriageError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )


def normalize_label(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def classifier_predictions(model: Any, texts: list[str]) -> list[dict[str, Any]]:
    if not hasattr(model, "predict_proba"):
        raise SemanticTriageError("classifier model does not expose predict_proba")
    classes = [str(value) for value in getattr(model, "classes_", [])]
    if not classes:
        raise SemanticTriageError("classifier model does not expose classes_")
    probability_rows = model.predict_proba(texts)
    predictions: list[dict[str, Any]] = []
    for probabilities in probability_rows:
        pairs = sorted(
            (
                (label, float(probability))
                for label, probability in zip(classes, probabilities)
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        if not pairs:
            raise SemanticTriageError("classifier returned an empty probability row")
        confidence = pairs[0][1]
        second = pairs[1][1] if len(pairs) > 1 else 0.0
        predictions.append(
            {
                "prediction": pairs[0][0],
                "confidence": rounded(confidence),
                "margin": rounded(confidence - second),
                "top_scores": [
                    {"label": label, "score": rounded(score)}
                    for label, score in pairs[:3]
                ],
            }
        )
    if len(predictions) != len(texts):
        raise SemanticTriageError("classifier returned a different row count")
    return predictions


def load_optional_classifier(
    model_path: Path | None,
    *,
    original_texts: list[str],
    privatized_texts: list[str],
) -> dict[str, Any]:
    if model_path is None:
        return {"status": "not_requested"}
    try:
        model, metadata = load_model(model_path)
        original = classifier_predictions(model, original_texts)
        privatized = classifier_predictions(model, privatized_texts)
    except (ClassifierError, SemanticTriageError, ModuleNotFoundError) as exc:
        return {
            "status": "skipped",
            "skip_reason": "classifier_unavailable",
            "detail": str(exc),
            "model": str(model_path),
        }
    return {
        "status": "ok",
        "model": str(model_path),
        "model_info": metadata,
        "original": original,
        "privatized": privatized,
    }


def priority(score: int) -> str:
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    if score >= 1:
        return "low"
    return "none"


def review_route(*, hard_repair: bool, semantic_review: bool) -> str:
    if hard_repair:
        return "repair_before_model_review"
    if semantic_review:
        return "qwen_semantic_check"
    return "no_review"


def classifier_reason_codes(
    *,
    original: dict[str, Any],
    privatized: dict[str, Any],
    low_confidence: float,
    low_margin: float,
    confidence_drop: float,
) -> tuple[list[str], int]:
    reasons: list[str] = []
    score = 0
    if original["prediction"] != privatized["prediction"]:
        reasons.append("classifier_prediction_shift")
        score += 3
    if privatized["confidence"] < low_confidence:
        reasons.append("classifier_low_confidence")
        score += 2
    if privatized["margin"] < low_margin:
        reasons.append("classifier_low_margin")
        score += 2
    if original["confidence"] - privatized["confidence"] >= confidence_drop:
        reasons.append("classifier_confidence_drop")
        score += 2
    return reasons, score


def sorted_counts(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def sample_indices(
    rows: list[dict[str, str]],
    *,
    sample_size: int,
    strategy: str,
    source_col: str | None,
    label_col: str | None,
) -> list[int]:
    if sample_size <= 0 or sample_size >= len(rows):
        return list(range(len(rows)))
    if strategy == "first_n" or (not source_col and not label_col):
        return list(range(sample_size))
    buckets: dict[tuple[str, str], list[int]] = {}
    for index, row in enumerate(rows):
        key = (
            str(row.get(source_col, "") or "<blank>") if source_col else "<all>",
            str(row.get(label_col, "") or "<blank>") if label_col else "<all>",
        )
        buckets.setdefault(key, []).append(index)
    selected: list[int] = []
    bucket_keys = sorted(buckets)
    offset = 0
    while len(selected) < sample_size:
        added = False
        for key in bucket_keys:
            values = buckets[key]
            if offset < len(values):
                selected.append(values[offset])
                added = True
                if len(selected) >= sample_size:
                    break
        if not added:
            break
        offset += 1
    return selected


def review_queue_row(row: dict[str, Any]) -> dict[str, Any]:
    classifier = row.get("classifier") or {}
    protected = classifier.get("privatized") or {}
    return {
        "row_index": row["row_index"],
        "row_id": row["row_id"],
        "source": row.get("source"),
        "label": row.get("label"),
        "priority": row["priority"],
        "priority_score": row["priority_score"],
        "review_route": row["review_route"],
        "reasons": ";".join(row["reasons"]),
        "original_context_tags": ";".join(row["original_context_tags"]),
        "privatized_context_tags": ";".join(row["privatized_context_tags"]),
        "lost_context_tags": ";".join(row["lost_context_tags"]),
        "cue_loss_groups": ";".join(row["cue_loss_groups"]),
        "classifier_prediction": protected.get("prediction", ""),
        "classifier_confidence": protected.get("confidence", ""),
        "classifier_margin": protected.get("margin", ""),
    }


def unchanged_cue_report(
    *,
    row_index: int,
    row_id: str,
) -> dict[str, Any]:
    return {
        "row_index": row_index,
        "row_id": row_id,
        "loss_groups": [],
        "groups": {
            group: {
                "before": 0,
                "after": 0,
                "retention": 1.0,
                "lost_terms": [],
                "counts_before": {},
                "counts_after": {},
            }
            for group in cue_terms()
        },
    }


def empty_metric() -> dict[str, Any]:
    return {
        "residual_direct_identifier_count": 0,
        "residual_quasi_identifier_count": 0,
        "privacy_warnings": [],
        "overmasking_warnings": [],
    }


def run_semantic_triage_report(
    input_path: Path,
    *,
    protected_path: Path | None = None,
    text_col: str,
    privatized_col: str = "privatized_text",
    id_col: str | None = None,
    label_col: str | None = None,
    source_col: str | None = None,
    output_path: Path | None = None,
    queue_output_path: Path | None = None,
    classifier_model: Path | None = None,
    low_confidence: float = DEFAULT_LOW_CONFIDENCE,
    low_margin: float = DEFAULT_LOW_MARGIN,
    confidence_drop: float = DEFAULT_CONFIDENCE_DROP,
    max_review_rows: int = DEFAULT_MAX_REVIEW_ROWS,
    retention_threshold: float = DEFAULT_RETENTION_THRESHOLD,
    privacy_scan: str = DEFAULT_PRIVACY_SCAN,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    sample_strategy: str = DEFAULT_SAMPLE_STRATEGY,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    if protected_path:
        protected_rows, protected_fieldnames = read_csv(protected_path)
        validate_columns(
            input_path,
            fieldnames,
            text_col=text_col,
            privatized_col=text_col,
            id_col=id_col,
            label_col=label_col,
            source_col=source_col,
        )
        protected_missing = [
            column
            for column in (privatized_col, id_col)
            if column and column not in protected_fieldnames
        ]
        if protected_missing:
            raise SemanticTriageError(
                f"{protected_path}: missing required column(s): "
                + ", ".join(protected_missing)
            )
        if len(rows) != len(protected_rows):
            raise SemanticTriageError(
                "original/protected row counts differ: "
                f"{len(rows)} != {len(protected_rows)}"
            )
        if id_col:
            for index, (row, protected_row) in enumerate(
                zip(rows, protected_rows),
                start=1,
            ):
                if str(row.get(id_col, "")) != str(protected_row.get(id_col, "")):
                    raise SemanticTriageError(
                        f"row {index}: original/protected IDs differ"
                    )
    else:
        protected_rows = rows
        validate_columns(
            input_path,
            fieldnames,
            text_col=text_col,
            privatized_col=privatized_col,
            id_col=id_col,
            label_col=label_col,
            source_col=source_col,
        )
    if not 0 <= low_confidence <= 1:
        raise SemanticTriageError("--low-confidence must be between 0 and 1")
    if not 0 <= low_margin <= 1:
        raise SemanticTriageError("--low-margin must be between 0 and 1")
    if not 0 <= confidence_drop <= 1:
        raise SemanticTriageError("--confidence-drop must be between 0 and 1")
    if max_review_rows < 0:
        raise SemanticTriageError("--max-review-rows must be non-negative")
    if not 0 <= retention_threshold <= 1:
        raise SemanticTriageError("--retention-threshold must be between 0 and 1")
    if privacy_scan not in PRIVACY_SCAN_MODES:
        raise SemanticTriageError(
            "--privacy-scan must be one of: " + ", ".join(sorted(PRIVACY_SCAN_MODES))
        )
    if sample_size < 0:
        raise SemanticTriageError("--sample-size must be non-negative")
    if sample_strategy not in SAMPLE_STRATEGIES:
        raise SemanticTriageError(
            "--sample-strategy must be one of: "
            + ", ".join(sorted(SAMPLE_STRATEGIES))
        )

    source_row_count = len(rows)
    selected_indices = sample_indices(
        rows,
        sample_size=sample_size,
        strategy=sample_strategy,
        source_col=source_col,
        label_col=label_col,
    )
    rows = [rows[index] for index in selected_indices]
    protected_rows = [protected_rows[index] for index in selected_indices]

    original_texts = [str(row.get(text_col, "") or "") for row in rows]
    privatized_texts = [
        str(row.get(privatized_col, "") or "") for row in protected_rows
    ]
    classifier = load_optional_classifier(
        classifier_model,
        original_texts=original_texts,
        privatized_texts=privatized_texts,
    )

    triage_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    original_tag_counts: Counter[str] = Counter()
    privatized_tag_counts: Counter[str] = Counter()
    lost_tag_counts: Counter[str] = Counter()
    cue_loss_counts: Counter[str] = Counter()
    classifier_confidences: list[float] = []
    classifier_margins: list[float] = []

    classifier_ok = classifier.get("status") == "ok"
    original_classifier = classifier.get("original", [])
    privatized_classifier = classifier.get("privatized", [])

    for selected_offset, row in enumerate(rows):
        row_index = selected_indices[selected_offset] + 1
        original = original_texts[selected_offset]
        privatized = privatized_texts[selected_offset]
        changed = original != privatized
        row_id = report_row_id(row, row_index=row_index, id_col=id_col)
        label = str(row.get(label_col, "") or "") if label_col else None
        source = str(row.get(source_col, "") or "") if source_col else None

        original_context = analyze_context(original, row)
        privatized_context = analyze_context(privatized, row)
        original_tags = list(original_context["context_tags"])
        privatized_tags = list(privatized_context["context_tags"])
        lost_tags = sorted((set(original_tags) - set(privatized_tags)) & HARD_CONTEXT_TAGS)
        semantic_tags = sorted(set(original_tags) & SEMANTIC_REVIEW_TAGS)
        if changed:
            cue_report = row_cue_report(
                row_index=row_index,
                row_id=row_id,
                original=original,
                privatized=privatized,
                threshold=retention_threshold,
            )
        else:
            cue_report = unchanged_cue_report(row_index=row_index, row_id=row_id)
        if privacy_scan == "all" or (privacy_scan == "changed" and changed):
            metrics = row_metric(original, privatized)
        else:
            metrics = empty_metric()

        reasons: list[str] = []
        score = 0
        label_key = normalize_label(label or "")
        if label_key in AMBIGUOUS_LABELS:
            reasons.append("ambiguous_source_label")
            score += 3
        elif label_key in ADJACENT_LABELS:
            reasons.append("adjacent_source_label")
            score += 1
        if semantic_tags:
            reasons.append("semantic_context_marker")
            score += 2
        if lost_tags:
            reasons.append("context_tag_loss")
            score += 4
        if cue_report["loss_groups"]:
            reasons.append("cue_loss")
            score += 4
        if metrics["residual_direct_identifier_count"]:
            reasons.append("residual_direct_identifier")
            score += 4
        elif metrics["residual_quasi_identifier_count"]:
            reasons.append("residual_quasi_identifier")
            score += 3

        classifier_payload: dict[str, Any] | None = None
        if classifier_ok:
            original_pred = original_classifier[selected_offset]
            privatized_pred = privatized_classifier[selected_offset]
            classifier_payload = {
                "original": original_pred,
                "privatized": privatized_pred,
            }
            classifier_confidences.append(float(privatized_pred["confidence"]))
            classifier_margins.append(float(privatized_pred["margin"]))
            classifier_reasons, classifier_score = classifier_reason_codes(
                original=original_pred,
                privatized=privatized_pred,
                low_confidence=low_confidence,
                low_margin=low_margin,
                confidence_drop=confidence_drop,
            )
            reasons.extend(classifier_reasons)
            score += classifier_score

        hard_repair = bool(
            cue_report["loss_groups"]
            or lost_tags
            or metrics["residual_direct_identifier_count"]
            or metrics["residual_quasi_identifier_count"]
        )
        semantic_review = bool(
            semantic_tags
            or label_key in AMBIGUOUS_LABELS
            or any(reason.startswith("classifier_") for reason in reasons)
        )
        row_priority = priority(score)
        route = review_route(hard_repair=hard_repair, semantic_review=semantic_review)

        reason_counts.update(reasons)
        priority_counts[row_priority] += 1
        route_counts[route] += 1
        original_tag_counts.update(original_tags)
        privatized_tag_counts.update(privatized_tags)
        lost_tag_counts.update(lost_tags)
        cue_loss_counts.update(cue_report["loss_groups"])

        triage_row = {
            "row_index": row_index,
            "row_id": row_id,
            "changed": changed,
            "source": source,
            "label": label,
            "priority": row_priority,
            "priority_score": score,
            "review_route": route,
            "reasons": reasons,
            "original_context_tags": original_tags,
            "privatized_context_tags": privatized_tags,
            "lost_context_tags": lost_tags,
            "semantic_review_tags": semantic_tags,
            "cue_loss_groups": cue_report["loss_groups"],
            "privacy_warnings": metrics["privacy_warnings"],
            "overmasking_warnings": metrics["overmasking_warnings"],
            "cue_retention": {
                group: cue_report["groups"][group]["retention"]
                for group in cue_report["groups"]
            },
            "classifier": classifier_payload,
        }
        triage_rows.append(triage_row)
        if route != "no_review":
            review_rows.append(triage_row)

    review_rows.sort(
        key=lambda item: (-item["priority_score"], item["row_index"])
    )
    review_limit = len(review_rows) if max_review_rows == 0 else max_review_rows
    limited_review_rows = review_rows[:review_limit]

    if queue_output_path:
        queue_rows = [review_queue_row(row) for row in limited_review_rows]
        write_csv(
            queue_output_path,
            queue_rows,
            [
                "row_index",
                "row_id",
                "source",
                "label",
                "priority",
                "priority_score",
                "review_route",
                "reasons",
                "original_context_tags",
                "privatized_context_tags",
                "lost_context_tags",
                "cue_loss_groups",
                "classifier_prediction",
                "classifier_confidence",
                "classifier_margin",
            ],
        )

    result = {
        "artifact_type": "semantic_triage_report",
        "raw_text_included": False,
        "input": str(input_path),
        "protected": str(protected_path) if protected_path else None,
        "output": str(output_path) if output_path else None,
        "queue_output": str(queue_output_path) if queue_output_path else None,
        "row_alignment_valid": True,
        "sample": {
            "requested_sample_size": sample_size,
            "sample_size": len(rows),
            "source_row_count": source_row_count,
            "strategy": sample_strategy,
        },
        "columns": {
            "text_col": text_col,
            "privatized_col": privatized_col,
            "id_col": id_col,
            "label_col": label_col,
            "source_col": source_col,
        },
        "thresholds": {
            "low_confidence": low_confidence,
            "low_margin": low_margin,
            "confidence_drop": confidence_drop,
            "retention_threshold": retention_threshold,
            "privacy_scan": privacy_scan,
        },
        "fallbacks": {
            "deterministic_context_tags": "always_on",
            "conservative_cue_checks": "always_on",
            "trained_classifier": classifier["status"],
            "qwen": "not_called_by_this_report",
        },
        "classifier": {
            key: value
            for key, value in classifier.items()
            if key not in {"original", "privatized"}
        },
        "aggregate": {
            "row_count": len(rows),
            "review_row_count": len(review_rows),
            "review_rows_returned": len(limited_review_rows),
            "review_rows_truncated": max(0, len(review_rows) - len(limited_review_rows)),
            "priority_counts": sorted_counts(priority_counts),
            "review_route_counts": sorted_counts(route_counts),
            "reason_counts": sorted_counts(reason_counts),
            "original_context_tag_counts": sorted_counts(original_tag_counts),
            "privatized_context_tag_counts": sorted_counts(privatized_tag_counts),
            "lost_context_tag_counts": sorted_counts(lost_tag_counts),
            "cue_loss_counts": sorted_counts(cue_loss_counts),
            "classifier_confidence_mean": (
                rounded(mean(classifier_confidences)) if classifier_confidences else None
            ),
            "classifier_margin_mean": (
                rounded(mean(classifier_margins)) if classifier_margins else None
            ),
        },
        "review_rows": limited_review_rows,
    }
    if output_path:
        write_json(output_path, result)
    return result
