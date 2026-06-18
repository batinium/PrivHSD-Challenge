"""Final exact-format CSV sanitization plus sidecar HSD review."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .auto import AutoPipelineConfig, AutoPipelineContext, AutoPipelineEngine
from .csv_pipeline import read_csv, write_csv, write_json
from .models.hf_hsd_classifier_runtime import (
    DEFAULT_HF_HSD_BATCH_SIZE,
    DEFAULT_HF_HSD_MAX_LENGTH,
    DEFAULT_HF_HSD_MODEL_PATH,
    DEFAULT_HF_HSD_THRESHOLD,
)
from .models.dpmlm_rewrite_runtime import (
    DEFAULT_DPMLM_EPSILON,
    DEFAULT_DPMLM_MAX_LENGTH,
    DEFAULT_DPMLM_MAX_REWRITE_TOKENS,
    DEFAULT_DPMLM_MIN_ELIGIBLE_SCORE,
    DEFAULT_DPMLM_MODEL_PATH,
    DEFAULT_DPMLM_TOP_K,
)
from .row_ids import report_row_id
from .submission import git_commit, sha256_file, validation_report


class SimplifiedPipelineError(ValueError):
    pass


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


def skipped_verifier_result(
    *,
    reason: str,
    row_count: int,
    backend: str = "local_llm_verifier",
    error_class: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "skipped",
        "backend": backend,
        "skip_reason": reason,
        "row_count": row_count,
        "reviewed_scope": "main_classifier_positive_rows_only",
        "parse_count": 0,
        "fallback_count": 0,
        "skipped_count": row_count,
        "decision_counts": {},
        "reason_counts": {},
        "action_counts": {},
        "human_review_candidate_count": 0,
        "label_override_applied": False,
        "approved_use": "optional audit safeguard only; no label overrides",
        "row_reviews": [],
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


def hf_hsd_classification(
    *,
    context: AutoPipelineContext,
    output_rows: list[dict[str, Any]],
    text_col: str,
    id_col: str | None,
    require_hate_classification: bool,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if not output_rows:
        return skipped_review_result(
            reason="empty_input",
            row_count=0,
            backend="hf_classifier",
        )
    runtime = context.ensure_hf_classifier()
    if runtime is None:
        if require_hate_classification:
            raise SimplifiedPipelineError(
                "HF HSD classification was required but unavailable"
            )
        return skipped_review_result(
            reason="hf_classifier_unavailable",
            row_count=len(output_rows),
            backend="hf_classifier",
        )

    classifier_rows = [
        {
            "id": report_row_id(row, row_index=index, id_col=id_col),
            "text": str(row.get(text_col, "") or ""),
        }
        for index, row in enumerate(output_rows, start=1)
    ]
    try:
        result = runtime.classify_texts(
            classifier_rows,
            batch_size=context.config.hf_hsd_batch_size,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        if require_hate_classification:
            raise
        return skipped_review_result(
            reason="model_inference_failed",
            row_count=len(output_rows),
            backend="hf_classifier",
            error_class=type(exc).__name__,
        )

    if require_hate_classification and result.skipped_count:
        raise SimplifiedPipelineError(
            "HF HSD classification was required but one or more rows "
            "could not be parsed"
        )

    return {
        **result.summary(),
        "model_ids": [result.model_id],
        "model_count": 1 if result.parsed_count else 0,
        "pii_suggestions_applied": False,
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


def local_llm_hsd_verifier(
    *,
    context: AutoPipelineContext,
    output_rows: list[dict[str, Any]],
    classification: dict[str, Any],
    text_col: str,
    id_col: str | None,
    endpoint: str,
    model_id: str,
    timeout_seconds: float,
    batch_size: int,
    prompt_style: str,
    reasoning_effort: str | None,
    model_factories: Mapping[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if classification.get("backend") not in {"local_llm", "hf_classifier"}:
        return skipped_verifier_result(
            reason="classification_backend_not_supported",
            row_count=0,
        )
    review_by_id = {
        str(review.get("id")): review
        for review in classification.get("row_reviews", [])
        if isinstance(review, dict) and review.get("id") is not None
    }
    verifier_rows: list[dict[str, str]] = []
    for index, row in enumerate(output_rows, start=1):
        row_id = report_row_id(row, row_index=index, id_col=id_col)
        review = review_by_id.get(row_id)
        if not review or review.get("parse_status") != "ok":
            continue
        if str(review.get("label", "") or "") != "1" and review.get("hate") is not True:
            continue
        verifier_rows.append(
            {
                "id": row_id,
                "text": str(row.get(text_col, "") or ""),
            }
        )
    if not verifier_rows:
        return skipped_verifier_result(
            reason="no_main_positive_rows",
            row_count=0,
        )

    factory = (model_factories or {}).get("local_llm_verifier")
    if factory is not None:
        runtime = factory(context)
    else:
        from .models.local_llm_hsd_verifier_runtime import (
            LocalLlmHsdVerifierRuntime,
        )

        runtime = LocalLlmHsdVerifierRuntime(
            endpoint=endpoint,
            model_id=model_id,
            timeout_seconds=timeout_seconds,
            prompt_style=prompt_style,
            reasoning_effort=reasoning_effort,
        )
    try:
        result = runtime.verify_texts(
            verifier_rows,
            batch_size=batch_size,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        return skipped_verifier_result(
            reason="model_inference_failed",
            row_count=len(verifier_rows),
            error_class=type(exc).__name__,
        )

    summary = result.summary()
    return {
        **summary,
        "model_ids": [result.model_id],
        "model_count": 1 if result.parsed_count else 0,
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
    if backend == "hf_classifier":
        classification = hf_hsd_classification(
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
            row[columns["score"]] = str(review.get("score", "") or "")
            row[columns["model_count"]] = "1"
        return {
            **classification,
            "columns": columns,
        }
    if require_hate_classification:
        raise SimplifiedPipelineError(
            "HSD classification is disabled; use local_llm or hf_classifier."
        )
    for row in output_rows:
        row[columns["label"]] = ""
        row[columns["score"]] = ""
        row[columns["model_count"]] = "0"
    result = skipped_review_result(
        reason="classification_backend_disabled",
        row_count=len(output_rows),
        backend=backend,
    )
    result["columns"] = columns
    return result


def final_stage_summary(
    sanitization: dict[str, Any],
    classification: dict[str, Any],
    verifier: dict[str, Any] | None = None,
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
    if verifier is not None:
        verification["local_llm_hsd_verifier"] = {
            "status": verifier.get("status", "skipped"),
            "backend": verifier.get("backend", "local_llm_verifier"),
            "skip_reason": verifier.get("skip_reason"),
            "model_count": verifier.get("model_count", 0),
            "model_ids": verifier.get("model_ids", []),
            "prompt_style": verifier.get("prompt_style"),
            "reviewed_scope": verifier.get(
                "reviewed_scope",
                "main_classifier_positive_rows_only",
            ),
            "parse_count": verifier.get("parse_count"),
            "fallback_count": verifier.get("fallback_count"),
            "skipped_count": verifier.get("skipped_count"),
            "decision_counts": verifier.get("decision_counts", {}),
            "reason_counts": verifier.get("reason_counts", {}),
            "action_counts": verifier.get("action_counts", {}),
            "human_review_candidate_count": verifier.get(
                "human_review_candidate_count",
                0,
            ),
            "label_override_applied": verifier.get("label_override_applied", False),
            "approved_use": verifier.get("approved_use"),
        }
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
    llm_review: str = "off",
    hsd_classification_backend: str | None = None,
    hf_hsd_model_path: str = DEFAULT_HF_HSD_MODEL_PATH,
    hf_hsd_threshold: float = DEFAULT_HF_HSD_THRESHOLD,
    hf_hsd_device: str = "auto",
    hf_hsd_batch_size: int = DEFAULT_HF_HSD_BATCH_SIZE,
    hf_hsd_max_length: int = DEFAULT_HF_HSD_MAX_LENGTH,
    local_llm_endpoint: str = "http://localhost:1234/v1/chat/completions",
    local_llm_model: str = "openai/gpt-oss-20b",
    local_llm_timeout_seconds: float = 120.0,
    local_llm_batch_size: int = 10,
    local_llm_enable_pii_suggestions: bool = True,
    llm_verifier: str = "off",
    local_llm_verifier_model: str | None = None,
    local_llm_verifier_timeout_seconds: float | None = None,
    local_llm_verifier_batch_size: int | None = None,
    local_llm_verifier_prompt_style: str = "current",
    local_llm_verifier_reasoning_effort: str | None = None,
    require_hate_classification: bool = False,
    author_group_masking: bool = True,
    author_group_col: str | None = None,
    author_group_min_repetitions: int = 2,
    author_group_min_author_rows: int = 2,
    generalize_targets: bool | None = False,
    candidate_selection: bool = True,
    style_scrub: bool = True,
    style_simplify_language: bool = False,
    dpmlm_rewrite: bool = False,
    dpmlm_model_path: str = DEFAULT_DPMLM_MODEL_PATH,
    dpmlm_device: str = "auto",
    dpmlm_epsilon: float = DEFAULT_DPMLM_EPSILON,
    dpmlm_max_rewrite_tokens: int = DEFAULT_DPMLM_MAX_REWRITE_TOKENS,
    dpmlm_min_eligible_score: int = DEFAULT_DPMLM_MIN_ELIGIBLE_SCORE,
    dpmlm_top_k: int = DEFAULT_DPMLM_TOP_K,
    dpmlm_max_length: int = DEFAULT_DPMLM_MAX_LENGTH,
    dpmlm_random_seed: int = 0,
    dpmlm_min_row_style_risk: int = 1,
    hsd_token_importance_path: str | None = None,
    hsd_token_protect_threshold: float = 0.03,
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
    normalized_hsd_backend = (
        hsd_classification_backend.strip().lower().replace("-", "_")
        if hsd_classification_backend is not None
        else ("local_llm" if normalized_llm_review == "local_llm" else "none")
    )
    if normalized_hsd_backend == "off":
        normalized_hsd_backend = "none"
    if normalized_hsd_backend not in {"none", "local_llm", "hf_classifier"}:
        raise SimplifiedPipelineError(
            "hsd_classification_backend must be none, local_llm, or hf_classifier"
        )
    if normalized_hsd_backend == "local_llm":
        normalized_llm_review = "local_llm"
    normalized_llm_verifier = llm_verifier.strip().lower().replace("-", "_")
    if normalized_llm_verifier not in {"local_llm", "off"}:
        raise SimplifiedPipelineError("llm_verifier must be local_llm or off")

    disabled_model_set = set(disabled_models or [])
    if normalized_llm_review == "off" and normalized_hsd_backend != "local_llm":
        disabled_model_set.add("local_llm")
    if normalized_hsd_backend != "hf_classifier":
        disabled_model_set.add("hf_classifier")
    config = AutoPipelineConfig(
        metric_depth=metric_depth,
        allow_model_download=allow_model_download,
        device=device,
        max_model_batch_size=max_model_batch_size,
        max_provider_rows=max_provider_rows,
        disabled_providers=frozenset(disabled_providers or []),
        disabled_models=frozenset(disabled_model_set),
        audit_level=audit_level,
        hsd_classification_backend=normalized_hsd_backend,
        hf_hsd_model_path=hf_hsd_model_path,
        hf_hsd_threshold=hf_hsd_threshold,
        hf_hsd_device=hf_hsd_device,
        hf_hsd_batch_size=hf_hsd_batch_size,
        hf_hsd_max_length=hf_hsd_max_length,
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
        candidate_selection=candidate_selection,
        style_scrub=style_scrub,
        style_simplify_language=style_simplify_language,
        dpmlm_rewrite=dpmlm_rewrite,
        dpmlm_model_path=dpmlm_model_path,
        dpmlm_device=dpmlm_device,
        dpmlm_epsilon=dpmlm_epsilon,
        dpmlm_max_rewrite_tokens=dpmlm_max_rewrite_tokens,
        dpmlm_min_eligible_score=dpmlm_min_eligible_score,
        dpmlm_top_k=dpmlm_top_k,
        dpmlm_max_length=dpmlm_max_length,
        dpmlm_random_seed=dpmlm_random_seed,
        dpmlm_min_row_style_risk=dpmlm_min_row_style_risk,
        hsd_token_importance_path=hsd_token_importance_path,
        hsd_token_protect_threshold=hsd_token_protect_threshold,
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
    if normalized_hsd_backend == "local_llm":
        classification = local_llm_hsd_review(
            context=context,
            output_rows=output_rows,
            text_col=text_col,
            id_col=id_col,
            require_hate_classification=require_hate_classification,
            progress_callback=progress_callback,
        )
    elif normalized_hsd_backend == "hf_classifier":
        classification = hf_hsd_classification(
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
            backend=normalized_hsd_backend,
        )
    if normalized_llm_verifier == "local_llm" and normalized_hsd_backend in {
        "local_llm",
        "hf_classifier",
    }:
        verifier = local_llm_hsd_verifier(
            context=context,
            output_rows=output_rows,
            classification=classification,
            text_col=text_col,
            id_col=id_col,
            endpoint=local_llm_endpoint,
            model_id=local_llm_verifier_model or local_llm_model,
            timeout_seconds=(
                local_llm_verifier_timeout_seconds
                if local_llm_verifier_timeout_seconds is not None
                else local_llm_timeout_seconds
            ),
            batch_size=(
                local_llm_verifier_batch_size
                if local_llm_verifier_batch_size is not None
                else local_llm_batch_size
            ),
            prompt_style=local_llm_verifier_prompt_style,
            reasoning_effort=local_llm_verifier_reasoning_effort,
            model_factories=model_factories,
            progress_callback=progress_callback,
        )
    else:
        verifier = skipped_verifier_result(
            reason="disabled",
            row_count=0,
        )

    model_status = dict(context.model_status)
    if normalized_llm_verifier == "local_llm":
        model_status["local_llm_verifier"] = {
            "status": "available",
            "model_id": local_llm_verifier_model or local_llm_model,
            "endpoint": local_llm_endpoint,
            "timeout_seconds": (
                local_llm_verifier_timeout_seconds
                if local_llm_verifier_timeout_seconds is not None
                else local_llm_timeout_seconds
            ),
            "batch_size": (
                local_llm_verifier_batch_size
                if local_llm_verifier_batch_size is not None
                else local_llm_batch_size
            ),
            "prompt_style": local_llm_verifier_prompt_style,
            "reasoning_effort": local_llm_verifier_reasoning_effort,
            "approved_use": "optional audit metadata only; no label overrides",
        }
    else:
        model_status["local_llm_verifier"] = {"status": "disabled"}

    return {
        "rows": output_rows,
        "fieldnames": list(fieldnames),
        "sanitization": engine_result.summary,
        "classification": classification,
        "classification_verifier": verifier,
        "stages": final_stage_summary(engine_result.summary, classification, verifier),
        "audit_rows": engine_result.audit_rows,
        "providers": context.provider_status,
        "models": model_status,
        "load_counts": {
            "providers": dict(sorted(context.provider_load_counts.items())),
            "models": dict(sorted(context.model_load_counts.items())),
        },
        "config": {
            "baseline_mode": config.baseline_mode,
            "metric_depth": config.metric_depth,
            "llm_review": normalized_llm_review,
            "hsd_classification_backend": normalized_hsd_backend,
            "llm_verifier": normalized_llm_verifier,
            "device": config.device,
            "hf_hsd_model_path": config.hf_hsd_model_path,
            "hf_hsd_threshold": config.hf_hsd_threshold,
            "hf_hsd_device": config.hf_hsd_device,
            "hf_hsd_batch_size": config.hf_hsd_batch_size,
            "hf_hsd_max_length": config.hf_hsd_max_length,
            "author_group_masking": config.author_group_masking,
            "candidate_selection": config.candidate_selection,
            "style_scrub": config.style_scrub,
            "style_simplify_language": config.style_simplify_language,
            "dpmlm_rewrite": config.dpmlm_rewrite,
            "dpmlm_model_path": config.dpmlm_model_path,
            "dpmlm_device": config.dpmlm_device,
            "dpmlm_epsilon": config.dpmlm_epsilon,
            "dpmlm_max_rewrite_tokens": config.dpmlm_max_rewrite_tokens,
            "dpmlm_min_eligible_score": config.dpmlm_min_eligible_score,
            "dpmlm_top_k": config.dpmlm_top_k,
            "dpmlm_max_length": config.dpmlm_max_length,
            "dpmlm_random_seed": config.dpmlm_random_seed,
            "dpmlm_min_row_style_risk": config.dpmlm_min_row_style_risk,
            "hsd_token_importance_path": config.hsd_token_importance_path,
            "hsd_token_protect_threshold": config.hsd_token_protect_threshold,
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
    llm_review: str = "off",
    hsd_classification_backend: str | None = None,
    hf_hsd_model_path: str = DEFAULT_HF_HSD_MODEL_PATH,
    hf_hsd_threshold: float = DEFAULT_HF_HSD_THRESHOLD,
    hf_hsd_device: str = "auto",
    hf_hsd_batch_size: int = DEFAULT_HF_HSD_BATCH_SIZE,
    hf_hsd_max_length: int = DEFAULT_HF_HSD_MAX_LENGTH,
    local_llm_endpoint: str = "http://localhost:1234/v1/chat/completions",
    local_llm_model: str = "openai/gpt-oss-20b",
    local_llm_timeout_seconds: float = 120.0,
    local_llm_batch_size: int = 10,
    local_llm_enable_pii_suggestions: bool = True,
    llm_verifier: str = "off",
    local_llm_verifier_model: str | None = None,
    local_llm_verifier_timeout_seconds: float | None = None,
    local_llm_verifier_batch_size: int | None = None,
    local_llm_verifier_prompt_style: str = "current",
    local_llm_verifier_reasoning_effort: str | None = None,
    require_hate_classification: bool = False,
    author_group_masking: bool = True,
    author_group_col: str | None = None,
    author_group_min_repetitions: int = 2,
    author_group_min_author_rows: int = 2,
    generalize_targets: bool | None = False,
    candidate_selection: bool = True,
    style_scrub: bool = True,
    style_simplify_language: bool = False,
    dpmlm_rewrite: bool = False,
    dpmlm_model_path: str = DEFAULT_DPMLM_MODEL_PATH,
    dpmlm_device: str = "auto",
    dpmlm_epsilon: float = DEFAULT_DPMLM_EPSILON,
    dpmlm_max_rewrite_tokens: int = DEFAULT_DPMLM_MAX_REWRITE_TOKENS,
    dpmlm_min_eligible_score: int = DEFAULT_DPMLM_MIN_ELIGIBLE_SCORE,
    dpmlm_top_k: int = DEFAULT_DPMLM_TOP_K,
    dpmlm_max_length: int = DEFAULT_DPMLM_MAX_LENGTH,
    dpmlm_random_seed: int = 0,
    dpmlm_min_row_style_risk: int = 1,
    hsd_token_importance_path: str | None = None,
    hsd_token_protect_threshold: float = 0.03,
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
        hsd_classification_backend=hsd_classification_backend,
        hf_hsd_model_path=hf_hsd_model_path,
        hf_hsd_threshold=hf_hsd_threshold,
        hf_hsd_device=hf_hsd_device,
        hf_hsd_batch_size=hf_hsd_batch_size,
        hf_hsd_max_length=hf_hsd_max_length,
        local_llm_endpoint=local_llm_endpoint,
        local_llm_model=local_llm_model,
        local_llm_timeout_seconds=local_llm_timeout_seconds,
        local_llm_batch_size=local_llm_batch_size,
        local_llm_enable_pii_suggestions=local_llm_enable_pii_suggestions,
        llm_verifier=llm_verifier,
        local_llm_verifier_model=local_llm_verifier_model,
        local_llm_verifier_timeout_seconds=local_llm_verifier_timeout_seconds,
        local_llm_verifier_batch_size=local_llm_verifier_batch_size,
        local_llm_verifier_prompt_style=local_llm_verifier_prompt_style,
        local_llm_verifier_reasoning_effort=local_llm_verifier_reasoning_effort,
        require_hate_classification=require_hate_classification,
        author_group_masking=author_group_masking,
        author_group_col=author_group_col,
        author_group_min_repetitions=author_group_min_repetitions,
        author_group_min_author_rows=author_group_min_author_rows,
        generalize_targets=generalize_targets,
        candidate_selection=candidate_selection,
        style_scrub=style_scrub,
        style_simplify_language=style_simplify_language,
        dpmlm_rewrite=dpmlm_rewrite,
        dpmlm_model_path=dpmlm_model_path,
        dpmlm_device=dpmlm_device,
        dpmlm_epsilon=dpmlm_epsilon,
        dpmlm_max_rewrite_tokens=dpmlm_max_rewrite_tokens,
        dpmlm_min_eligible_score=dpmlm_min_eligible_score,
        dpmlm_top_k=dpmlm_top_k,
        dpmlm_max_length=dpmlm_max_length,
        dpmlm_random_seed=dpmlm_random_seed,
        dpmlm_min_row_style_risk=dpmlm_min_row_style_risk,
        hsd_token_importance_path=hsd_token_importance_path,
        hsd_token_protect_threshold=hsd_token_protect_threshold,
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
        "style_scrub": result["config"]["style_scrub"],
        "style_simplify_language": result["config"]["style_simplify_language"],
        "dpmlm_rewrite": result["config"]["dpmlm_rewrite"],
        "dpmlm_model_path": result["config"]["dpmlm_model_path"],
        "dpmlm_device": result["config"]["dpmlm_device"],
        "dpmlm_epsilon": result["config"]["dpmlm_epsilon"],
        "dpmlm_max_rewrite_tokens": result["config"]["dpmlm_max_rewrite_tokens"],
        "dpmlm_min_eligible_score": result["config"]["dpmlm_min_eligible_score"],
        "dpmlm_top_k": result["config"]["dpmlm_top_k"],
        "dpmlm_max_length": result["config"]["dpmlm_max_length"],
        "dpmlm_random_seed": result["config"]["dpmlm_random_seed"],
        "dpmlm_min_row_style_risk": result["config"]["dpmlm_min_row_style_risk"],
        "hsd_token_importance_path": result["config"]["hsd_token_importance_path"],
        "hsd_token_protect_threshold": result["config"][
            "hsd_token_protect_threshold"
        ],
        "author_group_masking": result["config"]["author_group_masking"],
        "candidate_selection": result["config"]["candidate_selection"],
        "exact_format_submission": True,
        "llm_review": result["config"]["llm_review"],
        "hsd_classification_backend": result["config"]["hsd_classification_backend"],
        "hf_hsd_model_path": result["config"]["hf_hsd_model_path"],
        "hf_hsd_threshold": result["config"]["hf_hsd_threshold"],
        "hf_hsd_max_length": result["config"]["hf_hsd_max_length"],
        "llm_verifier": result["config"]["llm_verifier"],
        "stages": result["stages"],
        "sanitization": result["sanitization"],
        "classification": result["classification"],
        "classification_verifier": result["classification_verifier"],
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
                "verifier_reviews": result["classification_verifier"].get(
                    "row_reviews",
                    [],
                ),
            },
        )
    return manifest
