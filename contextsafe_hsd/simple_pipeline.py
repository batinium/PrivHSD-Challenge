"""One-command CSV sanitization plus HSD classification."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Mapping

from .auto import AutoPipelineConfig, AutoPipelineContext, AutoPipelineEngine
from .csv_pipeline import read_csv, write_csv, write_json
from .row_ids import report_row_id
from .submission import git_commit, sha256_file, validation_report


DEFAULT_HATE_LABEL_COL = "is_hate_speech"
DEFAULT_HATE_SCORE_COL = "hate_speech_score"
DEFAULT_HATE_MODEL_COUNT_COL = "hate_speech_model_count"


class SimplifiedPipelineError(ValueError):
    pass


def rounded(value: float) -> float:
    return round(float(value), 4)


def resolve_output_column(
    existing: list[str],
    desired: str,
    *,
    overwrite_existing: bool,
) -> str:
    if desired not in existing or overwrite_existing:
        return desired
    candidates = [
        f"predicted_{desired}",
        f"{desired}_predicted",
    ]
    index = 2
    while True:
        candidates.append(f"predicted_{desired}_{index}")
        for candidate in candidates:
            if candidate not in existing:
                return candidate
        index += 1


def classification_fieldnames(
    fieldnames: list[str],
    *,
    hate_label_col: str,
    hate_score_col: str,
    hate_model_count_col: str,
    overwrite_existing_hate_cols: bool,
) -> tuple[list[str], dict[str, str]]:
    output = list(fieldnames)
    columns: dict[str, str] = {}
    for logical_name, desired in [
        ("label", hate_label_col),
        ("score", hate_score_col),
        ("model_count", hate_model_count_col),
    ]:
        column = resolve_output_column(
            output,
            desired,
            overwrite_existing=overwrite_existing_hate_cols,
        )
        columns[logical_name] = column
        if column not in output:
            output.append(column)
    return output, columns


def score_by_model(
    runtime: Any,
    texts: list[str],
    *,
    batch_size: int,
) -> dict[str, list[float]]:
    score_texts_by_model = getattr(runtime, "score_texts_by_model", None)
    if callable(score_texts_by_model):
        scores = score_texts_by_model(texts, batch_size=batch_size)
    else:
        scores = {"hsd_advisory": runtime.score_texts(texts, batch_size=batch_size)}
    for model_id, values in scores.items():
        if len(values) != len(texts):
            raise SimplifiedPipelineError(
                f"HSD advisory model {model_id!r} returned {len(values)} scores "
                f"for {len(texts)} rows"
            )
    return scores


def ensemble_scores(scores: dict[str, list[float]], row_count: int) -> list[float]:
    if not scores:
        return [0.0 for _row in range(row_count)]
    return [
        float(mean(model_scores[index] for model_scores in scores.values()))
        for index in range(row_count)
    ]


def model_score_summary(
    original_by_model: dict[str, list[float]],
    sanitized_by_model: dict[str, list[float]],
    *,
    threshold: float,
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for model_id, sanitized_scores in sanitized_by_model.items():
        original_scores = original_by_model.get(model_id, [])
        deltas = [
            sanitized - original
            for original, sanitized in zip(original_scores, sanitized_scores)
        ]
        summary[model_id] = {
            "row_count": len(sanitized_scores),
            "original_score_mean": rounded(mean(original_scores))
            if original_scores
            else 0.0,
            "sanitized_score_mean": rounded(mean(sanitized_scores))
            if sanitized_scores
            else 0.0,
            "mean_delta": rounded(mean(deltas)) if deltas else 0.0,
            "positive_count": sum(score >= threshold for score in sanitized_scores),
        }
    return summary


def skipped_classification_result(
    *,
    reason: str,
    output_rows: list[dict[str, Any]],
    columns: dict[str, str],
    backend: str = "ml",
) -> dict[str, Any]:
    for row in output_rows:
        row[columns["label"]] = ""
        row[columns["score"]] = ""
        row[columns["model_count"]] = "0"
    return {
        "status": "skipped",
        "backend": backend,
        "skip_reason": reason,
        "row_count": len(output_rows),
        "columns": columns,
    }


def skipped_review_result(
    *,
    reason: str,
    row_count: int,
    backend: str = "local_llm",
    error_class: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "skipped",
        "backend": backend,
        "skip_reason": reason,
        "row_count": row_count,
        "parse_count": 0,
        "fallback_count": 0,
        "skipped_count": row_count,
        "prediction_counts": {},
        "reason_tag_counts": {},
        "pii_suggestion_count": 0,
        "accepted_pii_suggestion_count": 0,
        "validated_pii_suggestion_counts": {
            "total": 0,
            "accepted_for_review": 0,
            "rejected": 0,
        },
        "pii_suggestion_status_counts": {},
        "row_reviews": [],
        "pii_suggestions_applied": False,
    }
    if error_class:
        result["error_class"] = error_class
    return result


def local_llm_hsd_review(
    *,
    context: AutoPipelineContext,
    output_rows: list[dict[str, Any]],
    text_col: str,
    id_col: str | None,
    require_hate_classification: bool,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if not output_rows:
        return skipped_review_result(reason="empty_input", row_count=0)
    runtime = context.ensure_local_llm_review()
    if runtime is None:
        if require_hate_classification:
            raise SimplifiedPipelineError(
                "Local LLM HSD classification was required but unavailable"
            )
        return skipped_review_result(
            reason="local_llm_unavailable",
            row_count=len(output_rows),
        )

    review_rows = [
        {
            "id": report_row_id(row, row_index=index, id_col=id_col),
            "text": str(row.get(text_col, "") or ""),
        }
        for index, row in enumerate(output_rows, start=1)
    ]
    try:
        result = runtime.review_texts(
            review_rows,
            batch_size=context.config.local_llm_batch_size,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        if require_hate_classification:
            raise
        return skipped_review_result(
            reason="model_inference_failed",
            row_count=len(output_rows),
            error_class=type(exc).__name__,
        )

    if require_hate_classification and result.skipped_count:
        raise SimplifiedPipelineError(
            "Local LLM HSD classification was required but one or more rows "
            "could not be parsed"
        )

    summary = result.summary(include_suggestion_text=False)
    return {
        **summary,
        "model_ids": [result.model_id],
        "model_count": 1 if result.parsed_count else 0,
        "score_basis": "binary_structured_hsd_label_no_confidence",
        "pii_suggestions_applied": False,
    }


def append_ml_hate_classification(
    *,
    context: AutoPipelineContext,
    original_rows: list[dict[str, str]],
    output_rows: list[dict[str, Any]],
    text_col: str,
    columns: dict[str, str],
    require_hate_classification: bool,
) -> dict[str, Any]:
    if not output_rows:
        return skipped_classification_result(
            reason="empty_input",
            output_rows=output_rows,
            columns=columns,
            backend="ml",
        )
    runtime = context.ensure_hsd_advisory()
    if runtime is None:
        if require_hate_classification:
            raise SimplifiedPipelineError("HSD classification was required but unavailable")
        return skipped_classification_result(
            reason="hsd_advisory_unavailable",
            output_rows=output_rows,
            columns=columns,
            backend="ml",
        )

    original_texts = [str(row.get(text_col, "") or "") for row in original_rows]
    sanitized_texts = [str(row.get(text_col, "") or "") for row in output_rows]
    try:
        original_by_model = score_by_model(
            runtime,
            original_texts,
            batch_size=context.config.max_model_batch_size,
        )
        sanitized_by_model = score_by_model(
            runtime,
            sanitized_texts,
            batch_size=context.config.max_model_batch_size,
        )
    except Exception as exc:
        if require_hate_classification:
            raise
        for row in output_rows:
            row[columns["label"]] = ""
            row[columns["score"]] = ""
            row[columns["model_count"]] = "0"
        return {
            "status": "skipped",
            "backend": "ml",
            "skip_reason": "model_inference_failed",
            "error_class": type(exc).__name__,
            "row_count": len(output_rows),
            "columns": columns,
        }

    threshold = float(
        getattr(
            runtime,
            "decision_threshold",
            context.config.hsd_advisory_decision_threshold,
        )
    )
    original_scores = ensemble_scores(original_by_model, len(output_rows))
    sanitized_scores = ensemble_scores(sanitized_by_model, len(output_rows))
    labels = ["1" if score >= threshold else "0" for score in sanitized_scores]
    model_count = len(sanitized_by_model)
    for row, label, score in zip(output_rows, labels, sanitized_scores):
        row[columns["label"]] = label
        row[columns["score"]] = f"{rounded(score):.4f}"
        row[columns["model_count"]] = str(model_count)

    original_labels = [score >= threshold for score in original_scores]
    sanitized_labels = [score >= threshold for score in sanitized_scores]
    decision_changes = [
        original != sanitized
        for original, sanitized in zip(original_labels, sanitized_labels)
    ]
    deltas = [
        sanitized - original
        for original, sanitized in zip(original_scores, sanitized_scores)
    ]
    return {
        "status": "ok",
        "backend": "ml",
        "row_count": len(output_rows),
        "columns": columns,
        "decision_threshold": threshold,
        "model_ids": sorted(sanitized_by_model),
        "model_count": model_count,
        "prediction_counts": dict(sorted(Counter(labels).items())),
        "sanitized_score_mean": rounded(mean(sanitized_scores)),
        "original_score_mean": rounded(mean(original_scores)),
        "mean_delta": rounded(mean(deltas)) if deltas else 0.0,
        "decision_changed_count": sum(decision_changes),
        "decision_agreement": rounded(1.0 - (sum(decision_changes) / len(output_rows))),
        "models": model_score_summary(
            original_by_model,
            sanitized_by_model,
            threshold=threshold,
        ),
    }


def append_local_llm_hate_classification(
    *,
    context: AutoPipelineContext,
    output_rows: list[dict[str, Any]],
    text_col: str,
    id_col: str | None,
    columns: dict[str, str],
    require_hate_classification: bool,
) -> dict[str, Any]:
    classification = local_llm_hsd_review(
        context=context,
        output_rows=output_rows,
        text_col=text_col,
        id_col=id_col,
        require_hate_classification=require_hate_classification,
    )
    review_by_id = {
        str(review.get("id")): review
        for review in classification.get("row_reviews", [])
        if isinstance(review, dict) and review.get("id") is not None
    }
    for index, row in enumerate(output_rows, start=1):
        row_id = report_row_id(row, row_index=index, id_col=id_col)
        review = review_by_id.get(row_id)
        if review is None or review.get("parse_status") != "ok":
            row[columns["label"]] = ""
            row[columns["score"]] = ""
            row[columns["model_count"]] = "0"
            continue
        row[columns["label"]] = str(review.get("label", "") or "")
        row[columns["score"]] = ""
        row[columns["model_count"]] = "1"

    return {
        **classification,
        "columns": columns,
    }


def append_hate_classification(
    *,
    context: AutoPipelineContext,
    original_rows: list[dict[str, str]],
    output_rows: list[dict[str, Any]],
    text_col: str,
    columns: dict[str, str],
    require_hate_classification: bool,
    id_col: str | None = None,
) -> dict[str, Any]:
    backend = context.config.hsd_classification_backend
    if backend == "local_llm":
        return append_local_llm_hate_classification(
            context=context,
            output_rows=output_rows,
            text_col=text_col,
            id_col=id_col,
            columns=columns,
            require_hate_classification=require_hate_classification,
        )
    return append_ml_hate_classification(
        context=context,
        original_rows=original_rows,
        output_rows=output_rows,
        text_col=text_col,
        columns=columns,
        require_hate_classification=require_hate_classification,
    )


def tradeoff_summary(
    sanitization: dict[str, Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    metrics = sanitization.get("metrics", {})
    identifier_counts = metrics.get("identifier_counts", {})
    direct_identifier_counts = metrics.get("direct_identifier_counts", {})
    quasi_identifier_counts = metrics.get("quasi_identifier_counts", {})
    return {
        "identifier_count_before": int(identifier_counts.get("before", 0) or 0),
        "identifier_count_after": int(identifier_counts.get("after", 0) or 0),
        "direct_identifier_count_after": int(
            direct_identifier_counts.get("after", 0) or 0
        ),
        "quasi_identifier_count_after": int(
            quasi_identifier_counts.get("after", 0) or 0
        ),
        "target_cue_retention_mean": metrics.get("target_cue_retention_mean"),
        "utility_cue_retention_mean": metrics.get("utility_cue_retention_mean"),
        "character_utility_retention_mean": metrics.get(
            "character_utility_retention_mean"
        ),
        "rows_with_overmasking_warnings": metrics.get("rows_with_overmasking_warnings"),
        "classification_status": classification.get("status"),
        "classification_backend": classification.get("backend"),
        "classification_mean_delta": classification.get("mean_delta"),
        "classification_decision_changed_count": classification.get(
            "decision_changed_count"
        ),
    }


def analysis_stage_summary(
    sanitization: dict[str, Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    stages = deepcopy(sanitization.get("stages", {}))
    verification = stages.setdefault("verification", {})
    candidate_drift_check = verification.get("hsd_advisory")
    classification_status = str(classification.get("status", "skipped"))
    verification["hsd_candidate_drift_check"] = candidate_drift_check
    verification["hsd_advisory_status"] = (
        classification_status if classification_status == "ok" else "skipped"
    )
    verification["hsd_advisory"] = {
        "status": verification["hsd_advisory_status"],
        "use": "analysis_prediction_columns",
        "columns": classification.get("columns", {}),
        "skip_reason": classification.get("skip_reason"),
        "model_count": classification.get("model_count", 0),
        "model_ids": classification.get("model_ids", []),
        "decision_changed_count": classification.get("decision_changed_count"),
        "candidate_drift_check": candidate_drift_check,
    }
    verification["hsd_classification"] = {
        "status": classification_status,
        "backend": classification.get("backend", "ml"),
        "columns": classification.get("columns", {}),
        "skip_reason": classification.get("skip_reason"),
        "model_count": classification.get("model_count", 0),
        "model_ids": classification.get("model_ids", []),
        "parse_count": classification.get("parse_count"),
        "fallback_count": classification.get("fallback_count"),
        "skipped_count": classification.get("skipped_count"),
        "prediction_counts": classification.get("prediction_counts", {}),
        "reason_tag_counts": classification.get("reason_tag_counts", {}),
        "pii_suggestion_status_counts": classification.get(
            "pii_suggestion_status_counts",
            {},
        ),
        "pii_suggestions_applied": classification.get("pii_suggestions_applied"),
    }
    return stages


def final_stage_summary(
    sanitization: dict[str, Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    stages = deepcopy(sanitization.get("stages", {}))
    verification = stages.setdefault("verification", {})
    classification_status = str(classification.get("status", "skipped"))
    review_summary = {
        "status": classification_status,
        "backend": classification.get("backend", "local_llm"),
        "skip_reason": classification.get("skip_reason"),
        "model_count": classification.get("model_count", 0),
        "model_ids": classification.get("model_ids", []),
        "parse_count": classification.get("parse_count"),
        "fallback_count": classification.get("fallback_count"),
        "skipped_count": classification.get("skipped_count"),
        "prediction_counts": classification.get("prediction_counts", {}),
        "reason_tag_counts": classification.get("reason_tag_counts", {}),
        "pii_suggestion_count": classification.get("pii_suggestion_count", 0),
        "accepted_pii_suggestion_count": classification.get(
            "accepted_pii_suggestion_count",
            0,
        ),
        "validated_pii_suggestion_counts": classification.get(
            "validated_pii_suggestion_counts",
            {},
        ),
        "pii_suggestion_status_counts": classification.get(
            "pii_suggestion_status_counts",
            {},
        ),
        "pii_suggestions_applied": classification.get("pii_suggestions_applied"),
    }
    verification["local_llm_hsd_review"] = review_summary
    verification["hsd_classification"] = review_summary
    return stages


def build_final_pipeline_rows(
    rows: list[dict[str, str]],
    fieldnames: list[str],
    *,
    text_col: str = "text",
    id_col: str | None = None,
    metric_depth: str = "fast",
    allow_model_download: bool = False,
    device: str = "cpu",
    max_model_batch_size: int = 16,
    max_provider_rows: int | None = None,
    disabled_providers: list[str] | None = None,
    disabled_models: list[str] | None = None,
    audit_level: str = "summary",
    llm_review: str = "local_llm",
    local_llm_endpoint: str = "http://localhost:1234/v1/chat/completions",
    local_llm_model: str = "openai/gpt-oss-20b",
    local_llm_timeout_seconds: float = 120.0,
    local_llm_batch_size: int = 10,
    local_llm_enable_pii_suggestions: bool = True,
    require_hate_classification: bool = False,
    author_group_masking: bool = False,
    author_group_col: str | None = None,
    author_group_min_repetitions: int = 2,
    author_group_min_author_rows: int = 2,
    generalize_targets: bool | None = False,
    style_scrub: bool = False,
    provider_factories: Mapping[str, Any] | None = None,
    model_factories: Mapping[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if text_col not in fieldnames:
        raise SimplifiedPipelineError(f"missing text column {text_col!r}")
    if id_col and id_col not in fieldnames and not all(id_col in row for row in rows):
        raise SimplifiedPipelineError(f"missing id column {id_col!r}")
    normalized_llm_review = llm_review.strip().lower().replace("-", "_")
    if normalized_llm_review not in {"local_llm", "off"}:
        raise SimplifiedPipelineError("llm_review must be local_llm or off")

    disabled_model_set = set(disabled_models or [])
    disabled_model_set.add("semantic")
    if normalized_llm_review == "off":
        disabled_model_set.update({"hsd_advisory", "local_llm"})
    config = AutoPipelineConfig(
        metric_depth=metric_depth,
        allow_model_download=allow_model_download,
        device=device,
        max_model_batch_size=max_model_batch_size,
        max_provider_rows=max_provider_rows,
        disabled_providers=frozenset(disabled_providers or []),
        disabled_models=frozenset(disabled_model_set),
        audit_level=audit_level,
        gliner_model=None,
        gliner_profile="pii",
        hsd_classification_backend=(
            "local_llm" if normalized_llm_review == "local_llm" else "ml"
        ),
        local_llm_endpoint=local_llm_endpoint,
        local_llm_model=local_llm_model,
        local_llm_timeout_seconds=local_llm_timeout_seconds,
        local_llm_batch_size=local_llm_batch_size,
        local_llm_enable_pii_suggestions=local_llm_enable_pii_suggestions,
        author_group_masking=author_group_masking,
        author_group_col=author_group_col,
        author_group_min_repetitions=author_group_min_repetitions,
        author_group_min_author_rows=author_group_min_author_rows,
        generalize_targets=generalize_targets,
        style_scrub=style_scrub,
        official_mode=False,
    )
    context = AutoPipelineContext.create(
        config,
        provider_factories=provider_factories,
        model_factories=model_factories,
    )
    engine_result = AutoPipelineEngine(context).process_rows(
        rows,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        output_col=text_col,
        replace_text=True,
        progress_callback=progress_callback,
    )
    output_rows = [dict(row) for row in engine_result.rows]
    if normalized_llm_review == "local_llm":
        classification = local_llm_hsd_review(
            context=context,
            output_rows=output_rows,
            text_col=text_col,
            id_col=id_col,
            require_hate_classification=require_hate_classification,
            progress_callback=progress_callback,
        )
    else:
        classification = skipped_review_result(
            reason="disabled",
            row_count=len(output_rows),
        )

    return {
        "rows": output_rows,
        "fieldnames": list(fieldnames),
        "sanitization": engine_result.summary,
        "classification": classification,
        "stages": final_stage_summary(engine_result.summary, classification),
        "audit_rows": engine_result.audit_rows,
        "providers": context.provider_status,
        "models": context.model_status,
        "load_counts": {
            "providers": dict(sorted(context.provider_load_counts.items())),
            "models": dict(sorted(context.model_load_counts.items())),
        },
        "config": {
            "baseline_mode": config.baseline_mode,
            "metric_depth": config.metric_depth,
            "llm_review": normalized_llm_review,
            "device": config.device,
            "author_group_masking": config.author_group_masking,
        },
    }


def run_final_csv_pipeline(
    input_path: Path,
    output_path: Path,
    *,
    text_col: str = "text",
    id_col: str | None = None,
    manifest_path: Path | None = None,
    audit_path: Path | None = None,
    command: list[str] | None = None,
    preset: str = "exact",
    metric_depth: str = "fast",
    allow_model_download: bool = False,
    device: str = "cpu",
    max_model_batch_size: int = 16,
    max_provider_rows: int | None = None,
    disabled_providers: list[str] | None = None,
    disabled_models: list[str] | None = None,
    audit_level: str = "summary",
    llm_review: str = "local_llm",
    local_llm_endpoint: str = "http://localhost:1234/v1/chat/completions",
    local_llm_model: str = "openai/gpt-oss-20b",
    local_llm_timeout_seconds: float = 120.0,
    local_llm_batch_size: int = 10,
    local_llm_enable_pii_suggestions: bool = True,
    require_hate_classification: bool = False,
    author_group_masking: bool = False,
    author_group_col: str | None = None,
    author_group_min_repetitions: int = 2,
    author_group_min_author_rows: int = 2,
    generalize_targets: bool | None = False,
    style_scrub: bool = False,
    provider_factories: Mapping[str, Any] | None = None,
    model_factories: Mapping[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    result = build_final_pipeline_rows(
        rows,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        metric_depth=metric_depth,
        allow_model_download=allow_model_download,
        device=device,
        max_model_batch_size=max_model_batch_size,
        max_provider_rows=max_provider_rows,
        disabled_providers=disabled_providers,
        disabled_models=disabled_models,
        audit_level=audit_level,
        llm_review=llm_review,
        local_llm_endpoint=local_llm_endpoint,
        local_llm_model=local_llm_model,
        local_llm_timeout_seconds=local_llm_timeout_seconds,
        local_llm_batch_size=local_llm_batch_size,
        local_llm_enable_pii_suggestions=local_llm_enable_pii_suggestions,
        require_hate_classification=require_hate_classification,
        author_group_masking=author_group_masking,
        author_group_col=author_group_col,
        author_group_min_repetitions=author_group_min_repetitions,
        author_group_min_author_rows=author_group_min_author_rows,
        generalize_targets=generalize_targets,
        style_scrub=style_scrub,
        provider_factories=provider_factories,
        model_factories=model_factories,
        progress_callback=progress_callback,
    )
    write_csv(output_path, result["rows"], result["fieldnames"])
    validation = validation_report(
        input_path,
        output_path,
        text_cols=[text_col],
        id_col=id_col,
        allow_helper_columns=False,
    )
    if not validation["valid"]:
        codes = ", ".join(issue["code"] for issue in validation["issues"])
        raise SimplifiedPipelineError(f"final CSV validation failed: {codes}")

    manifest = {
        "artifact_type": "final_exact_csv",
        "pipeline": "final_exact",
        "preset": preset,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "git_commit": git_commit(),
        "input": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
            "row_count": len(rows),
        },
        "output": {
            "path": str(output_path),
            "sha256": sha256_file(output_path),
            "row_count": len(result["rows"]),
        },
        "columns": {
            "text_col": text_col,
            "text_cols": [text_col],
            "id_col": id_col,
            "original_columns": fieldnames,
            "output_columns": result["fieldnames"],
            "preserved_columns": fieldnames,
            "classification_columns": [],
        },
        "mode": "auto",
        "baseline_mode": result["config"]["baseline_mode"],
        "metric_depth": metric_depth,
        "replace_text": True,
        "exact_format_submission": True,
        "llm_review": result["config"]["llm_review"],
        "stages": result["stages"],
        "sanitization": result["sanitization"],
        "classification": result["classification"],
        "metrics": result["sanitization"].get("metrics", {}),
        "providers": result["providers"],
        "models": result["models"],
        "load_counts": result["load_counts"],
        "validation": validation,
    }
    if manifest_path:
        write_json(manifest_path, manifest)
    if audit_path:
        write_json(
            audit_path,
            {
                "summary": manifest,
                "rows": result["audit_rows"],
                "classification_reviews": result["classification"].get(
                    "row_reviews",
                    [],
                ),
            },
        )
    return manifest


def run_sanitize_classify(
    input_path: Path,
    output_path: Path,
    *,
    text_col: str = "text",
    id_col: str | None = None,
    manifest_path: Path | None = None,
    audit_path: Path | None = None,
    command: list[str] | None = None,
    metric_depth: str = "fast",
    allow_model_download: bool = False,
    device: str = "cpu",
    max_model_batch_size: int = 16,
    max_provider_rows: int | None = None,
    disabled_providers: list[str] | None = None,
    disabled_models: list[str] | None = None,
    audit_level: str = "summary",
    gliner_model: str | None = None,
    gliner_profile: str = "pii",
    hsd_advisory_models: list[str] | None = None,
    hsd_classification_backend: str = "ml",
    local_llm_endpoint: str = "http://localhost:1234/v1/chat/completions",
    local_llm_model: str = "openai/gpt-oss-20b",
    local_llm_timeout_seconds: float = 120.0,
    local_llm_batch_size: int = 10,
    local_llm_enable_pii_suggestions: bool = True,
    author_group_masking: bool = False,
    author_group_col: str | None = None,
    author_group_min_repetitions: int = 2,
    author_group_min_author_rows: int = 2,
    generalize_targets: bool | None = False,
    style_scrub: bool = False,
    hate_label_col: str = DEFAULT_HATE_LABEL_COL,
    hate_score_col: str = DEFAULT_HATE_SCORE_COL,
    hate_model_count_col: str = DEFAULT_HATE_MODEL_COUNT_COL,
    overwrite_existing_hate_cols: bool = False,
    require_hate_classification: bool = False,
    provider_factories: Mapping[str, Any] | None = None,
    model_factories: Mapping[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    if text_col not in fieldnames:
        raise SimplifiedPipelineError(f"{input_path}: missing text column {text_col!r}")
    if id_col and id_col not in fieldnames:
        raise SimplifiedPipelineError(f"{input_path}: missing id column {id_col!r}")

    config_kwargs: dict[str, Any] = {
        "metric_depth": metric_depth,
        "allow_model_download": allow_model_download,
        "device": device,
        "max_model_batch_size": max_model_batch_size,
        "max_provider_rows": max_provider_rows,
        "disabled_providers": frozenset(disabled_providers or []),
        "disabled_models": frozenset(disabled_models or []),
        "audit_level": audit_level,
        "gliner_model": gliner_model,
        "gliner_profile": gliner_profile,
        "hsd_classification_backend": hsd_classification_backend,
        "local_llm_endpoint": local_llm_endpoint,
        "local_llm_model": local_llm_model,
        "local_llm_timeout_seconds": local_llm_timeout_seconds,
        "local_llm_batch_size": local_llm_batch_size,
        "local_llm_enable_pii_suggestions": local_llm_enable_pii_suggestions,
        "author_group_masking": author_group_masking,
        "author_group_col": author_group_col,
        "author_group_min_repetitions": author_group_min_repetitions,
        "author_group_min_author_rows": author_group_min_author_rows,
        "generalize_targets": generalize_targets,
        "style_scrub": style_scrub,
        "official_mode": False,
    }
    if hsd_advisory_models is not None:
        config_kwargs["hsd_advisory_models"] = tuple(hsd_advisory_models)
    config = AutoPipelineConfig(**config_kwargs)
    context = AutoPipelineContext.create(
        config,
        provider_factories=provider_factories,
        model_factories=model_factories,
    )
    engine_result = AutoPipelineEngine(context).process_rows(
        rows,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        output_col=text_col,
        replace_text=True,
        progress_callback=progress_callback,
    )
    output_rows = [dict(row) for row in engine_result.rows]
    output_fieldnames, classification_columns = classification_fieldnames(
        engine_result.fieldnames,
        hate_label_col=hate_label_col,
        hate_score_col=hate_score_col,
        hate_model_count_col=hate_model_count_col,
        overwrite_existing_hate_cols=overwrite_existing_hate_cols,
    )
    classification = append_hate_classification(
        context=context,
        original_rows=rows,
        output_rows=output_rows,
        text_col=text_col,
        columns=classification_columns,
        require_hate_classification=require_hate_classification,
        id_col=id_col,
    )

    write_csv(output_path, output_rows, output_fieldnames)
    validation = validation_report(
        input_path,
        output_path,
        text_cols=[text_col],
        id_col=id_col,
        allow_helper_columns=True,
    )
    manifest = {
        "artifact_type": "sanitize_classify_csv",
        "pipeline": "auto",
        "preset": "analysis",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "git_commit": git_commit(),
        "input": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
            "row_count": len(rows),
        },
        "output": {
            "path": str(output_path),
            "sha256": sha256_file(output_path),
            "row_count": len(output_rows),
        },
        "columns": {
            "text_col": text_col,
            "id_col": id_col,
            "original_columns": fieldnames,
            "output_columns": output_fieldnames,
            "classification_columns": classification_columns,
        },
        "mode": "auto",
        "baseline_mode": config.baseline_mode,
        "metric_depth": metric_depth,
        "replace_text": True,
        "exact_format_submission": False,
        "stages": analysis_stage_summary(engine_result.summary, classification),
        "sanitization": engine_result.summary,
        "classification": classification,
        "tradeoff": tradeoff_summary(engine_result.summary, classification),
        "providers": context.provider_status,
        "models": context.model_status,
        "load_counts": {
            "providers": dict(sorted(context.provider_load_counts.items())),
            "models": dict(sorted(context.model_load_counts.items())),
        },
        "validation": validation,
    }
    if manifest_path:
        write_json(manifest_path, manifest)
    if audit_path:
        write_json(
            audit_path,
            {
                "summary": manifest,
                "rows": engine_result.audit_rows,
            },
        )
    return manifest
