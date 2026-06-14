"""FastAPI wrapper for the local Privacy Review Workbench."""

from __future__ import annotations

import hashlib
from collections import Counter
import csv
from functools import lru_cache
import importlib.util
import io
import json
from pathlib import Path
import time
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from contextsafe_hsd.context import analyze_context
from contextsafe_hsd.cue_checks import row_cue_report
from contextsafe_hsd.detectors import Span, target_group_spans
from contextsafe_hsd.metrics import row_metric
from contextsafe_hsd.pipeline import MODES, PrivatizerConfig, privatize_text
from contextsafe_hsd.span_providers.base import SpanProvider
from contextsafe_hsd.span_providers.registry import (
    SUPPORTED_PROVIDER_NAMES,
    load_span_provider,
)


MAX_TEXT_LENGTH = 20_000
MAX_CSV_LENGTH = 5_000_000
MAX_PREVIEW_ROWS = 25
ROOT = Path(__file__).resolve().parents[2]
CSV_CACHE_VERSION = "workbench_csv_result_v2"
CSV_RESULT_CACHE_DIR = ROOT / "workbench" / ".cache" / "csv_results"
HSD_ADVISORY_MODEL_ID = "facebook/roberta-hate-speech-dynabench-r4-target"
CARDIFF_HATE_MODEL_ID = "cardiffnlp/twitter-roberta-base-hate-latest"
LOCAL_CLASSIFIER_PATH = ROOT / "data/outputs/privhsd_classifier.pkl"
ENSEMBLE_MODEL_DIRS = [
    ROOT / "data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda",
    ROOT / "data/outputs/token_policy_hatebert.action_balanced_train30000.cuda",
]
ENSEMBLE_REPORT = (
    ROOT / "data/outputs/token_policy_ensemble.roberta_hatebert.tweet_eval_external.evaluate.json"
)


class PrivatizeRequest(BaseModel):
    text: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    mode: Literal["utility", "balanced", "privacy"] = "balanced"
    style_scrub: bool = False
    generalize_targets: bool | None = None
    use_presidio: bool = False
    providers: list[str] = Field(default_factory=list)
    gliner_model: str | None = None
    gliner_profile: Literal["general", "pii"] = "general"
    run_model_ensemble: bool = False
    run_hsd_classifier: bool = False


class PrivatizeResponse(BaseModel):
    privatized_text: str
    mode: str
    changed: bool
    transformations: list[dict[str, Any]]
    protected_spans: list[dict[str, Any]]
    protected_output_spans: list[dict[str, Any]]
    presidio_augment: dict[str, Any]
    metrics: dict[str, Any]
    cue_report: dict[str, Any]
    context: dict[str, Any]
    gauges: dict[str, int]
    warnings: list[str]
    model_advisory: dict[str, Any]
    hsd_classifier: dict[str, Any]
    llm_guidance: dict[str, Any]
    span_providers: dict[str, Any]


class CsvPrivatizeRequest(BaseModel):
    csv_text: str = Field(default="", max_length=MAX_CSV_LENGTH)
    text_col: str
    id_col: str | None = None
    output_col: str = "privatized_text"
    replace_text: bool = False
    mode: Literal["auto"] = "auto"
    style_scrub: bool = False
    generalize_targets: bool | None = None
    providers: list[str] = Field(default_factory=list)
    disabled_providers: list[str] = Field(default_factory=list)
    disabled_models: list[str] = Field(default_factory=list)
    metric_depth: Literal["fast", "sampled", "deep"] = "fast"
    gliner_model: str | None = None
    gliner_profile: Literal["general", "pii"] = "general"


class CsvPrivatizeResponse(BaseModel):
    output_csv: str
    audit: dict[str, Any]
    manifest: dict[str, Any]
    platform_insights: dict[str, Any]
    preview_rows: list[dict[str, Any]]
    cache: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="ContextSafe-HSD Privacy Review Workbench")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def pct(value: float) -> int:
    return max(0, min(100, int(round(value * 100))))


def residual_risk(metric: dict[str, Any]) -> int:
    residual = int(metric.get("residual_identifier_count", 0) or 0)
    placeholder_density = float(metric.get("placeholder_density", 0.0) or 0.0)
    return max(0, min(100, residual * 25 + int(round(placeholder_density * 20))))


def cue_retention(cue_report: dict[str, Any]) -> int:
    groups = cue_report.get("groups", {})
    retentions = [
        float(group.get("retention", 1.0))
        for group in groups.values()
        if int(group.get("before", 0) or 0) > 0
    ]
    if not retentions:
        return 100
    return pct(min(retentions))


def clean_transformations(transformations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for item in transformations:
        cleaned.append(
            {
                "entity_type": item.get("entity_type"),
                "category": item.get("category"),
                "source": item.get("source"),
                "score": item.get("score"),
                "source_start": item.get("source_start"),
                "source_end": item.get("source_end"),
                "output_start": item.get("output_start"),
                "output_end": item.get("output_end"),
                "replacement": item.get("replacement"),
            }
        )
    return cleaned


def clean_span(span: Span, *, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "entity_type": span.entity_type,
        "category": span.category,
        "source": span.source,
        "score": span.score,
        "start": span.start,
        "end": span.end,
        "replacement": span.replacement_tag(),
    }


def parse_csv_text(csv_text: str) -> tuple[list[dict[str, str]], list[str]]:
    handle = io.StringIO(csv_text)
    reader = csv.DictReader(handle)
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV header is required.")
    return [dict(row) for row in reader], list(reader.fieldnames)


def write_csv_text(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()


def validate_csv_request(
    request: CsvPrivatizeRequest,
    fieldnames: list[str],
) -> None:
    if request.text_col not in fieldnames:
        raise HTTPException(
            status_code=400,
            detail=f"Missing text column: {request.text_col}",
        )
    if request.id_col and request.id_col not in fieldnames:
        raise HTTPException(
            status_code=400,
            detail=f"Missing ID column: {request.id_col}",
        )
    if request.mode != "auto":
        raise HTTPException(
            status_code=400,
            detail="CSV privatization is exposed through auto mode only.",
        )


def normalized_csv_cache_options(request: CsvPrivatizeRequest) -> dict[str, Any]:
    disabled_models = (
        sorted(request.disabled_models)
        if request.disabled_models
        else sorted(CSV_INSIGHT_DEFAULT_DISABLED_MODELS)
    )
    return {
        "version": CSV_CACHE_VERSION,
        "csv_sha256": hashlib.sha256(request.csv_text.encode("utf-8")).hexdigest(),
        "text_col": request.text_col,
        "id_col": request.id_col or "",
        "output_col": request.output_col,
        "replace_text": request.replace_text,
        "mode": request.mode,
        "style_scrub": request.style_scrub,
        "generalize_targets": (
            request.generalize_targets
            if request.generalize_targets is not None
            else False
        ),
        "providers": sorted(request.providers),
        "disabled_providers": sorted(request.disabled_providers),
        "disabled_models": disabled_models,
        "metric_depth": request.metric_depth,
        "gliner_model": request.gliner_model or "",
        "gliner_profile": request.gliner_profile,
    }


def csv_result_cache_key(request: CsvPrivatizeRequest) -> tuple[str, dict[str, Any]]:
    options = normalized_csv_cache_options(request)
    encoded = json.dumps(options, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest(), options


def csv_result_cache_path(cache_key: str) -> Path:
    return CSV_RESULT_CACHE_DIR / f"{cache_key}.json"


def cache_metadata(
    *,
    hit: bool,
    cache_key: str,
    options: dict[str, Any],
    created_at: float | None = None,
) -> dict[str, Any]:
    return {
        "hit": hit,
        "key": cache_key,
        "created_at": created_at,
        "csv_sha256": options["csv_sha256"],
        "version": CSV_CACHE_VERSION,
    }


def read_csv_result_cache(cache_key: str) -> dict[str, Any] | None:
    path = csv_result_cache_path(cache_key)
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if record.get("version") != CSV_CACHE_VERSION:
        return None
    result = record.get("result")
    if not isinstance(result, dict):
        return None
    return record


def write_csv_result_cache(
    *,
    cache_key: str,
    options: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    CSV_RESULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    created_at = time.time()
    cached_result = {key: value for key, value in result.items() if key != "cache"}
    record = {
        "version": CSV_CACHE_VERSION,
        "cache_key": cache_key,
        "created_at": created_at,
        "options": options,
        "result": cached_result,
    }
    path = csv_result_cache_path(cache_key)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(record, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp_path.replace(path)
    return cache_metadata(
        hit=False,
        cache_key=cache_key,
        options=options,
        created_at=created_at,
    )


def cached_csv_response(
    *,
    cache_key: str,
    options: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, Any] | None:
    result = record.get("result")
    if not isinstance(result, dict):
        return None
    response = dict(result)
    response["cache"] = cache_metadata(
        hit=True,
        cache_key=cache_key,
        options=options,
        created_at=record.get("created_at"),
    )
    return response


def csv_preview_row(
    row: dict[str, str],
    *,
    row_id: Any,
    text_col: str,
    output_col: str,
) -> dict[str, Any]:
    return {
        "row_id": row_id,
        "text_length": len(str(row.get(text_col, "") or "")),
        "output": str(row.get(output_col, "") or ""),
    }


POST_CLASSIFICATION_LABEL_COLUMNS = (
    "hsd_answer",
    "hsd_label",
    "predicted_hatred",
    "hatred_label",
    "predicted_is_hate_speech",
    "is_hate_speech",
    "hatred",
    "hate_speech",
    "hate_speech_label",
)
POST_CLASSIFICATION_SCORE_COLUMNS = (
    "hate_speech_score",
    "hatred_score",
    "hsd_score",
    "score",
    "confidence",
)
POSITIVE_HATRED_LABELS = frozenset(
    {
        "1",
        "true",
        "yes",
        "positive",
        "hate",
        "hateful",
        "hatred",
        "hate_speech",
        "abuse",
        "abusive",
        "toxic",
        "offensive",
    }
)
NEGATIVE_HATRED_LABELS = frozenset(
    {
        "0",
        "false",
        "no",
        "negative",
        "clean",
        "neutral",
        "normal",
        "not_hate",
        "non_hate",
        "non-hate",
        "not_hateful",
    }
)
HATRED_SCORE_THRESHOLD = 0.5
CSV_INSIGHT_DEFAULT_DISABLED_MODELS = frozenset(
    {"semantic", "local_llm"}
)


def current_auto_pipeline_profile(
    *,
    disabled_models: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    disabled = set(disabled_models or set())
    return {
        "public_stage_model": [
            "privacy_detection",
            "meaning_protection",
            "verification",
        ],
        "baseline": "deterministic_balanced",
        "pii_assist": {
            "default_components": ["presidio", "scrubadub"],
            "explicit_research_components": ["gliner"],
            "gliner_default": "disabled_without_explicit_local_model",
        },
        "candidate_ladder": [
            "balanced",
            "balanced_strict_pii",
            "style_scrubbed",
            "style_scrubbed_strict_pii",
            "provider_fusion_augmented",
            "provider_fusion_augmented_strict_pii",
            "token_policy_candidate",
            "token_policy_candidate_strict_pii",
        ],
        "meaning_protection": {
            "hard_rejects": [
                "target_cue_loss",
                "utility_cue_loss",
                "direct_identifier_increase",
                "new_identifier_signal",
                "length_drift",
                "hsd_advisory_large_drop",
                "hsd_advisory_decision_drift",
            ],
            "protected_cue_policy": (
                "target_action_negation_modality_quote_counterspeech_reporting"
            ),
        },
        "verification": {
            "hsd_advisory_default_models": [
                HSD_ADVISORY_MODEL_ID,
                CARDIFF_HATE_MODEL_ID,
            ],
            "hsd_advisory_enabled_for_this_profile": "hsd_advisory" not in disabled,
            "post_classification_hatred_columns": list(POST_CLASSIFICATION_LABEL_COLUMNS),
            "post_classification_score_columns": list(POST_CLASSIFICATION_SCORE_COLUMNS),
        },
    }


def first_present_column(
    rows: list[dict[str, Any]],
    candidates: tuple[str, ...],
) -> str | None:
    if not rows:
        return None
    lowered = {column.lower(): column for row in rows for column in row}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def hatred_classification(
    row: dict[str, Any],
    *,
    label_col: str | None,
    score_col: str | None,
) -> dict[str, Any]:
    score = parse_float(row.get(score_col)) if score_col else None
    label_value = str(row.get(label_col, "") or "").strip().lower() if label_col else ""
    if label_value in POSITIVE_HATRED_LABELS:
        is_hatred = True
    elif label_value in NEGATIVE_HATRED_LABELS:
        is_hatred = False
    elif score is not None:
        is_hatred = score >= HATRED_SCORE_THRESHOLD
    else:
        is_hatred = None
    return {
        "classified": is_hatred is not None,
        "is_hatred": is_hatred,
        "score": score,
    }


def pipeline_hsd_classification(audit_row: dict[str, Any] | None) -> dict[str, Any]:
    if not audit_row:
        return {
            "classified": False,
            "is_hatred": None,
            "score": None,
            "original_score": None,
            "source": "pipeline_hsd_advisory",
        }
    chosen_name = str(audit_row.get("chosen_candidate", "") or "")
    scores = audit_row.get("scores") or []
    chosen_score = None
    for score in scores:
        if str(score.get("name", "") or "") == chosen_name:
            chosen_score = score
            break
    if chosen_score is None:
        return {
            "classified": False,
            "is_hatred": None,
            "score": None,
            "original_score": None,
            "source": "pipeline_hsd_advisory",
        }
    hsd = (chosen_score or {}).get("metrics", {}).get("hsd_advisory") or {}
    candidate_score = parse_float(hsd.get("candidate_score"))
    original_score = parse_float(hsd.get("original_score"))
    candidate_max_score = parse_float(hsd.get("candidate_max_score"))
    original_max_score = parse_float(hsd.get("original_max_score"))
    positive_model_count = hsd.get("candidate_positive_model_count")
    model_count = hsd.get("model_count")
    threshold = parse_float(hsd.get("decision_threshold"))
    if threshold is None:
        threshold = HATRED_SCORE_THRESHOLD
    decision = str(hsd.get("candidate_decision", "") or "").strip().lower()
    if isinstance(positive_model_count, int):
        is_hatred = positive_model_count > 0
    elif decision == "positive":
        is_hatred = True
    elif decision == "negative":
        is_hatred = False
    elif candidate_score is not None:
        is_hatred = candidate_score >= threshold
    elif original_score is not None:
        is_hatred = original_score >= threshold
    else:
        is_hatred = None
    return {
        "classified": is_hatred is not None,
        "is_hatred": is_hatred,
        "score": (
            candidate_max_score
            if candidate_max_score is not None
            else candidate_score
            if candidate_score is not None
            else original_score
        ),
        "original_score": original_score,
        "original_max_score": original_max_score,
        "positive_model_count": positive_model_count,
        "model_count": model_count,
        "source": "pipeline_hsd_advisory",
    }


def target_category_counts_for_text(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for span in target_group_spans(text):
        if span.category:
            counts[str(span.category)] += 1
    return counts


def round_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def metric_for_insight_row(
    *,
    audit_row: dict[str, Any] | None,
    original_text: str,
    protected_text: str,
) -> dict[str, Any]:
    metrics = (audit_row or {}).get("metrics")
    if isinstance(metrics, dict):
        return metrics
    return row_metric(original_text, protected_text, metric_depth="fast")


def preview_text(value: str, *, max_chars: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def leakage_status(metric: dict[str, Any]) -> dict[str, Any]:
    residual = int(metric.get("residual_identifier_count", 0) or 0)
    direct = int(metric.get("residual_direct_identifier_count", 0) or 0)
    high_confidence = int(
        metric.get("residual_high_confidence_direct_identifier_count", 0) or 0
    )
    quasi = int(metric.get("residual_quasi_identifier_count", 0) or 0)
    if high_confidence or direct:
        status = "review_required"
        label = "Privacy review required"
        message = "Protected output still contains direct identifier signals."
    elif quasi or residual:
        status = "warning"
        label = "Residual identifier warning"
        message = "Protected output contains lower-confidence or contextual identifier signals."
    else:
        status = "clear"
        label = "No residual PII detected"
        message = "Final automated leakage scan found no residual identifier signals."
    return {
        "status": status,
        "label": label,
        "message": message,
        "residual_identifier_count": residual,
        "residual_direct_identifier_count": direct,
        "residual_high_confidence_direct_identifier_count": high_confidence,
        "residual_quasi_identifier_count": quasi,
        "entity_counts": metric.get("residual_identifier_counts_by_entity_type", {}),
        "warnings": metric.get("privacy_warnings", []),
    }


CONTEXT_PRESERVATION_TAGS = frozenset(
    {
        "protected_target",
        "hostile_action",
        "threat",
        "dehumanization",
        "exclusion",
        "negated_hate",
        "counterspeech",
        "quoted_or_reported",
    }
)
QUOTE_CONTEXT_TAGS = frozenset({"quoted_or_reported", "counterspeech", "negated_hate"})
HARM_CONTEXT_TAGS = frozenset(
    {"hostile_action", "threat", "dehumanization", "exclusion"}
)


def component_status(*, applies: bool, passed: bool) -> str:
    if not applies:
        return "not_applicable"
    return "preserved" if passed else "at_risk"


def context_preservation_status(
    *,
    original_text: str,
    protected_text: str,
    metric: dict[str, Any],
) -> dict[str, Any]:
    original_context = analyze_context(original_text)
    protected_context = analyze_context(protected_text)
    original_tags = set(original_context.get("context_tags", []))
    protected_tags = set(protected_context.get("context_tags", []))
    required_tags = sorted(original_tags & CONTEXT_PRESERVATION_TAGS)
    preserved_tags = sorted((original_tags & protected_tags) & CONTEXT_PRESERVATION_TAGS)
    lost_tags = sorted((original_tags - protected_tags) & CONTEXT_PRESERVATION_TAGS)
    target_retention = float(metric.get("target_cue_retention", 1.0) or 1.0)
    target_category_retention = float(
        metric.get("target_category_retention", 1.0) or 1.0
    )
    utility_retention = float(metric.get("utility_cue_retention", 1.0) or 1.0)
    character_retention = float(
        metric.get("character_utility_retention", 1.0) or 1.0
    )
    target_applies = "protected_target" in original_tags or int(
        metric.get("target_cue_count_before", 0) or 0
    ) > 0
    harm_applies = bool(original_tags & HARM_CONTEXT_TAGS) or int(
        metric.get("utility_cue_count_before", 0) or 0
    ) > 0
    quote_applies = bool(original_tags & QUOTE_CONTEXT_TAGS)
    components = {
        "target_group_reference": component_status(
            applies=target_applies,
            passed=target_retention >= 1.0 and target_category_retention >= 1.0,
        ),
        "harm_signal": component_status(
            applies=harm_applies,
            passed=utility_retention >= 1.0 and not (set(lost_tags) & HARM_CONTEXT_TAGS),
        ),
        "quotation_or_counterspeech_context": component_status(
            applies=quote_applies,
            passed=not (set(lost_tags) & QUOTE_CONTEXT_TAGS),
        ),
    }
    component_values = [value for value in components.values() if value != "not_applicable"]
    if not component_values:
        status = "not_applicable"
        label = "No HSD context markers"
    elif all(value == "preserved" for value in component_values) and character_retention >= 0.65:
        status = "preserved"
        label = "Context preserved"
    elif "at_risk" in component_values or target_retention < 1.0 or utility_retention < 1.0:
        status = "at_risk"
        label = "Context at risk"
    else:
        status = "partial"
        label = "Context partially preserved"
    score = min(
        target_retention if target_applies else 1.0,
        target_category_retention if target_applies else 1.0,
        utility_retention if harm_applies else 1.0,
        character_retention,
    )
    return {
        "status": status,
        "label": label,
        "score": round(score, 4),
        "components": components,
        "retention": {
            "target_cue": round(target_retention, 4),
            "target_category": round(target_category_retention, 4),
            "utility_cue": round(utility_retention, 4),
            "character": round(character_retention, 4),
        },
        "context_tags_before": required_tags,
        "context_tags_after": sorted(protected_tags & CONTEXT_PRESERVATION_TAGS),
        "preserved_context_tags": preserved_tags,
        "lost_context_tags": lost_tags,
    }


def harm_risk_status(
    *,
    classification: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    tags = set(context.get("context_tags", []))
    score = parse_float(classification.get("score"))
    positive_models = classification.get("positive_model_count")
    risk_points = 0
    if classification.get("is_hatred"):
        risk_points += 1
    if tags & {"threat", "dehumanization"}:
        risk_points += 2
    if tags & {"hostile_action", "exclusion"}:
        risk_points += 1
    if score is not None and score >= 0.8:
        risk_points += 1
    if isinstance(positive_models, int) and positive_models >= 2:
        risk_points += 1
    if risk_points >= 3:
        level = "high"
        label = "High harm risk"
    elif risk_points >= 1:
        level = "medium"
        label = "Moderate harm risk"
    else:
        level = "low"
        label = "Low harm signal"
    return {
        "level": level,
        "label": label,
        "drivers": sorted(tags & {"threat", "dehumanization", "hostile_action", "exclusion"}),
    }


def safeguard_card(
    *,
    classification: dict[str, Any],
    leakage: dict[str, Any],
    context_status: dict[str, Any],
    original_context: dict[str, Any],
) -> dict[str, Any]:
    harm = harm_risk_status(
        classification=classification,
        context=original_context,
    )
    human_review_required = bool(
        classification.get("classified") and classification.get("is_hatred")
    )
    return {
        "harm_risk": harm,
        "privacy_status": {
            "status": leakage["status"],
            "label": leakage["label"],
        },
        "context_preservation": {
            "status": context_status["status"],
            "label": context_status["label"],
            "score": context_status["score"],
        },
        "human_review": {
            "required": human_review_required,
            "label": "NGO review required" if human_review_required else "No review queue route",
        },
        "proportionate_response": {
            "auto_moderation": False,
            "label": "Human assessment only",
            "message": "Use protected text and aggregate evidence for NGO assessment; this is not an automatic moderation decision.",
        },
    }


def platform_insight_report(
    *,
    original_rows: list[dict[str, str]],
    output_rows: list[dict[str, Any]],
    text_col: str,
    output_col: str,
    aggregate: dict[str, Any],
    audit_rows: list[dict[str, Any]] | None = None,
    id_col: str | None = None,
) -> dict[str, Any]:
    label_col = first_present_column(output_rows, POST_CLASSIFICATION_LABEL_COLUMNS)
    score_col = first_present_column(output_rows, POST_CLASSIFICATION_SCORE_COLUMNS)
    uses_explicit_classification = label_col is not None or score_col is not None
    target_rows = 0
    classified_rows = 0
    hatred_rows = 0
    score_values: list[float] = []
    original_score_values: list[float] = []
    positive_model_counts: list[int] = []
    model_counts: list[int] = []
    category_stats: dict[str, dict[str, Any]] = {}
    category_cue_counts_before: Counter[str] = Counter()
    category_cue_counts_after: Counter[str] = Counter()
    queue_preview: list[dict[str, Any]] = []
    leakage_status_counts: Counter[str] = Counter()
    context_status_counts: Counter[str] = Counter()
    harm_risk_counts: Counter[str] = Counter()
    component_status_counts: dict[str, Counter[str]] = {
        "target_group_reference": Counter(),
        "harm_signal": Counter(),
        "quotation_or_counterspeech_context": Counter(),
    }
    context_tag_counts: Counter[str] = Counter()
    audit_rows = audit_rows or []

    for row_index, (original_row, output_row) in enumerate(zip(original_rows, output_rows)):
        original_text = str(original_row.get(text_col, "") or "")
        protected_text = str(output_row.get(output_col, "") or "")
        audit_row = audit_rows[row_index] if row_index < len(audit_rows) else None
        metric = metric_for_insight_row(
            audit_row=audit_row,
            original_text=original_text,
            protected_text=protected_text,
        )
        original_context = analyze_context(original_text)
        protected_context = analyze_context(protected_text)
        leakage = leakage_status(metric)
        context_status = context_preservation_status(
            original_text=original_text,
            protected_text=protected_text,
            metric=metric,
        )
        leakage_status_counts[leakage["status"]] += 1
        context_status_counts[context_status["status"]] += 1
        for component, status in context_status["components"].items():
            component_status_counts[component][status] += 1
        context_tag_counts.update(original_context.get("context_tags", []))
        before_counts = target_category_counts_for_text(original_text)
        after_counts = target_category_counts_for_text(protected_text)
        category_cue_counts_before.update(before_counts)
        category_cue_counts_after.update(after_counts)
        categories = sorted(before_counts)
        if categories:
            target_rows += 1
        if uses_explicit_classification:
            classification = hatred_classification(
                output_row,
                label_col=label_col,
                score_col=score_col,
            )
        else:
            classification = pipeline_hsd_classification(audit_row)
        safeguard = safeguard_card(
            classification=classification,
            leakage=leakage,
            context_status=context_status,
            original_context=original_context,
        )
        harm_risk_counts[safeguard["harm_risk"]["level"]] += 1
        if classification["score"] is not None:
            score_values.append(float(classification["score"]))
        if classification.get("original_score") is not None:
            original_score_values.append(float(classification["original_score"]))
        if classification.get("positive_model_count") is not None:
            positive_model_counts.append(int(classification["positive_model_count"]))
        if classification.get("model_count") is not None:
            model_counts.append(int(classification["model_count"]))
        if classification["classified"]:
            classified_rows += 1
            if classification["is_hatred"]:
                hatred_rows += 1
                if len(queue_preview) < MAX_PREVIEW_ROWS:
                    row_id = (
                        output_row.get(id_col)
                        if id_col
                        else output_row.get("id") or output_row.get("case_id")
                    )
                    queue_preview.append(
                        {
                            "row_id": row_id or str(row_index + 1),
                            "status": "needs_review",
                            "target_categories": categories,
                            "protected_preview": preview_text(protected_text),
                            "score": classification.get("score"),
                            "positive_model_count": classification.get(
                                "positive_model_count"
                            ),
                            "model_count": classification.get("model_count"),
                            "privacy_leakage": leakage,
                            "context_preservation": context_status,
                            "safeguard": safeguard,
                            "context_tags": original_context.get("context_tags", []),
                            "protected_context_tags": protected_context.get(
                                "context_tags",
                                [],
                            ),
                            "review_reasons": (
                                (audit_row or {})
                                .get("risk_profile", {})
                                .get("review_reasons", [])
                            ),
                        }
                    )
        for category in categories:
            stats = category_stats.setdefault(
                category,
                {
                    "rows": 0,
                    "classified_rows": 0,
                    "hatred_rows": 0,
                    "scores": [],
                },
            )
            stats["rows"] += 1
            if classification["classified"]:
                stats["classified_rows"] += 1
                if classification["is_hatred"]:
                    stats["hatred_rows"] += 1
            if classification["score"] is not None:
                stats["scores"].append(float(classification["score"]))

    categories_report = {}
    for category, stats in sorted(category_stats.items()):
        categories_report[category] = {
            "rows": stats["rows"],
            "row_rate": round_rate(stats["rows"], len(original_rows)),
            "classified_rows": stats["classified_rows"],
            "hatred_rows": stats["hatred_rows"],
            "hatred_rate": round_rate(stats["hatred_rows"], stats["classified_rows"]),
            "mean_hatred_score": mean_or_none(stats["scores"]),
            "target_cue_count_before": int(category_cue_counts_before.get(category, 0)),
            "target_cue_count_after": int(category_cue_counts_after.get(category, 0)),
        }

    return {
        "artifact_type": "platform_hate_insight",
        "row_count": len(original_rows),
        "privacy_posture": {
            "raw_text_retained_in_report": False,
            "report_contains_only_aggregate_statistics": True,
            "protected_text_preview_rows": min(MAX_PREVIEW_ROWS, len(output_rows)),
            "residual_identifier_count": int(
                aggregate.get("residual_identifier_count", 0) or 0
            ),
            "residual_identifier_counts_by_entity_type": aggregate.get(
                "residual_identifier_counts_by_entity_type",
                {},
            ),
            "privacy_warning_counts": aggregate.get("privacy_warning_counts", {}),
            "rows_with_privacy_warnings": int(
                aggregate.get("rows_with_privacy_warnings", 0) or 0
            ),
            "leakage_status_counts": dict(sorted(leakage_status_counts.items())),
        },
        "classification": {
            "label": "post_classification_hatred",
            "source": (
                "csv_post_classification_columns"
                if uses_explicit_classification
                else "pipeline_hsd_advisory"
            ),
            "display_name": (
                "Post-classification hatred"
                if uses_explicit_classification
                else "HSD model flags"
            ),
            "score_basis": (
                "csv_score_or_label_columns"
                if uses_explicit_classification
                else "any_registered_hsd_model_positive_for_chosen_candidate"
            ),
            "label_column": label_col,
            "score_column": score_col,
            "score_threshold": HATRED_SCORE_THRESHOLD,
            "classified_rows": classified_rows,
            "unknown_rows": len(original_rows) - classified_rows,
            "hatred_rows": hatred_rows,
            "hatred_rate": round_rate(hatred_rows, classified_rows),
            "mean_hatred_score": mean_or_none(score_values),
            "mean_original_hatred_score": mean_or_none(original_score_values),
            "total_positive_model_votes": sum(positive_model_counts),
            "total_model_votes": sum(model_counts),
            "model_vote_rule": None
            if uses_explicit_classification
            else "one_or_more_registered_hsd_models_positive",
        },
        "target_groups": {
            "rows_with_target_group": target_rows,
            "target_group_row_rate": round_rate(target_rows, len(original_rows)),
            "categories": categories_report,
        },
        "context_preservation": {
            "status_counts": dict(sorted(context_status_counts.items())),
            "component_status_counts": {
                component: dict(sorted(counts.items()))
                for component, counts in sorted(component_status_counts.items())
            },
            "context_tag_counts": dict(sorted(context_tag_counts.items())),
            "target_cue_retention_mean": aggregate.get("target_cue_retention_mean"),
            "target_term_retention_mean": aggregate.get("target_term_retention_mean"),
            "utility_cue_retention_mean": aggregate.get("utility_cue_retention_mean"),
            "character_utility_retention_mean": aggregate.get(
                "character_utility_retention_mean"
            ),
        },
        "safeguards": {
            "harm_risk_counts": dict(sorted(harm_risk_counts.items())),
            "privacy_status_counts": dict(sorted(leakage_status_counts.items())),
            "context_status_counts": dict(sorted(context_status_counts.items())),
            "human_review_required_rows": hatred_rows,
            "proportionate_response": {
                "auto_moderation": False,
                "label": "Human assessment only",
            },
        },
        "ngo_review": {
            "queue_rows": hatred_rows,
            "queue_rate": round_rate(hatred_rows, len(original_rows)),
            "queue_preview": queue_preview,
            "routing_rule": (
                "post_classification_hatred_positive"
                if uses_explicit_classification
                else "pipeline_hsd_advisory_positive"
            ),
            "auto_moderation": False,
            "message": (
                "Rows classified as hatred are routed to NGO review with protected "
                "text and aggregate context; this report is not an automatic "
                "moderation decision."
            ),
        },
    }


def read_ensemble_metrics() -> dict[str, Any] | None:
    if not ENSEMBLE_REPORT.exists():
        return None
    try:
        report = json.loads(ENSEMBLE_REPORT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    metrics = report.get("metrics", {})
    per_action = metrics.get("per_action", {})
    return {
        "report": str(ENSEMBLE_REPORT.relative_to(ROOT)),
        "accuracy": metrics.get("accuracy"),
        "macro_f1": metrics.get("macro_f1"),
        "protect_target_f1": per_action.get("PROTECT_TARGET", {}).get("f1"),
        "protect_hsd_f1": per_action.get("PROTECT_HSD", {}).get("f1"),
        "mask_identifier_f1": per_action.get("MASK_IDENTIFIER", {}).get("f1"),
        "runtime_seconds": report.get("runtime_seconds"),
    }


def presidio_available() -> bool:
    try:
        import presidio_analyzer  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def model_status() -> dict[str, Any]:
    model_dirs = [
        {
            "path": str(path.relative_to(ROOT)),
            "exists": path.exists(),
        }
        for path in ENSEMBLE_MODEL_DIRS
    ]
    available = all(item["exists"] for item in model_dirs)
    return {
        "auto_pipeline_profile": current_auto_pipeline_profile(),
        "deterministic": {
            "active": True,
            "label": "Deterministic privacy and cue checks",
            "role": "Always runs. This is the submission-safe layer.",
        },
        "token_policy_ensemble": {
            "available": available,
            "active_by_default": True,
            "pipeline_role": "auto_lazy_candidate_source",
            "role": (
                "Lazy auto-pipeline token-action candidate source. It is only "
                "loaded on routed rows when local artifacts are present."
            ),
            "members": model_dirs,
            "metrics": read_ensemble_metrics(),
        },
        "hsd_advisory": {
            "available": module_available("transformers")
            and module_available("torch"),
            "active_by_default": True,
            "pipeline_role": "auto_lazy_verification",
            "model_ids": [HSD_ADVISORY_MODEL_ID, CARDIFF_HATE_MODEL_ID],
            "role": (
                "Lazy auto-pipeline HSD preservation check. It compares "
                "candidate rewrites and rejects large hatred-score drift."
            ),
        },
        "hsd_classifiers": {
            "primary": {
                "available": module_available("transformers")
                and module_available("torch"),
                "active_by_default": False,
                "model_id": HSD_ADVISORY_MODEL_ID,
                "role": (
                    "Optional HSD utility classifier. It scores original and "
                    "protected text to surface decision or score drift."
                ),
            },
            "cardiff_hate_latest": {
                "available": module_available("transformers")
                and module_available("torch"),
                "active_by_default": False,
                "model_id": CARDIFF_HATE_MODEL_ID,
                "status": "registered_not_loaded",
            },
            "local_tfidf_logreg": {
                "available": LOCAL_CLASSIFIER_PATH.exists(),
                "active_by_default": False,
                "path": str(LOCAL_CLASSIFIER_PATH.relative_to(ROOT)),
                "status": "available"
                if LOCAL_CLASSIFIER_PATH.exists()
                else "missing_artifact",
            },
        },
        "llm_guidance": {
            "available": False,
            "active_by_default": False,
            "role": (
                "Last-resort semantic review guidance only. The workbench does "
                "not call a local LLM automatically or rewrite with LLM output."
            ),
        },
        "lexicon_policy": {
            "active": True,
            "presidio_available": presidio_available(),
            "role": (
                "Street suffixes, known high-risk locations, filtered Presidio "
                "spans, target lexicons, and target-preservation rules run "
                "before optional models."
            ),
        },
        "span_providers": {
            "presidio": {
                "available": presidio_available(),
                "active_by_default": True,
                "pipeline_role": "default_pii_assist",
            },
            "gliner": {
                "available": module_available("gliner"),
                "active_by_default": False,
                "pipeline_role": "explicit_research_only",
                "status": "disabled_without_explicit_local_model",
            },
            "scrubadub": {
                "available": module_available("scrubadub"),
                "active_by_default": True,
                "pipeline_role": "default_pii_assist",
            },
        },
    }


@lru_cache(maxsize=1)
def load_ensemble() -> tuple[list[dict[str, Any]], list[float]]:
    from contextsafe_hsd.token_policy import (
        load_token_policy_ensemble,
        normalize_model_weights,
    )

    members = load_token_policy_ensemble(ENSEMBLE_MODEL_DIRS)
    weights = normalize_model_weights(None, len(members))
    return members, weights


def run_token_policy_ensemble(text: str) -> dict[str, Any]:
    status = model_status()["token_policy_ensemble"]
    if not status["available"]:
        return {
            "active": False,
            "available": False,
            "status": "missing_model_dirs",
            "message": "Token-policy ensemble model directories are not present.",
        }
    try:
        from contextsafe_hsd.token_policy import (
            ensemble_member_report,
            ensemble_predictions_for_row,
            token_spans_for_text,
        )
    except Exception as exc:  # pragma: no cover - optional dependency path
        return {
            "active": False,
            "available": True,
            "status": "dependency_error",
            "message": str(exc),
        }

    try:
        members, weights = load_ensemble()
        row = {
            "text": text,
            "source": "workbench",
            "label": "",
            "target": "",
            "target_categories": "",
            "rationale_spans": "",
        }
        spans, action_counts, skipped, _member_actions, _ensemble_actions = (
            ensemble_predictions_for_row(
                row,
                members=members,
                model_weights=weights,
                mode="mean_prob",
                text_col="text",
                token_spans=token_spans_for_text(text),
            )
        )
    except Exception as exc:  # pragma: no cover - hardware/model-load path
        return {
            "active": False,
            "available": True,
            "status": "runtime_error",
            "message": str(exc),
        }

    return {
        "active": True,
        "available": True,
        "status": "ok",
        "mode": "mean_prob",
        "members": ensemble_member_report(members, weights),
        "action_counts": dict(sorted(action_counts.items())),
        "skipped_token_count": skipped,
        "spans": spans[:80],
        "metrics": read_ensemble_metrics(),
    }


@lru_cache(maxsize=1)
def load_hsd_classifier() -> Any:
    from contextsafe_hsd.models.hsd_advisory_runtime import HsdAdvisoryRuntime

    return HsdAdvisoryRuntime.from_model_id(
        HSD_ADVISORY_MODEL_ID,
        allow_model_download=False,
        device="auto",
        decision_threshold=0.5,
        large_drop_threshold=0.25,
        max_abs_drift=0.35,
    )


def run_hsd_classifier(original: str, privatized: str) -> dict[str, Any]:
    status = model_status()["hsd_classifiers"]["primary"]
    if not status["available"]:
        return {
            "active": False,
            "available": False,
            "status": "missing_dependency",
            "model_id": HSD_ADVISORY_MODEL_ID,
            "message": "Install torch and transformers to run HSD classifier scoring.",
        }
    try:
        classifier = load_hsd_classifier()
        scores = classifier.score_texts([original, privatized], batch_size=2)
        if len(scores) != 2:
            return {
                "active": False,
                "available": True,
                "status": "unexpected_model_output",
                "model_id": HSD_ADVISORY_MODEL_ID,
                "message": "Classifier returned an unexpected number of scores.",
            }
        comparison = classifier.compare(scores[0], scores[1])
    except Exception as exc:  # pragma: no cover - optional dependency/model path
        return {
            "active": False,
            "available": True,
            "status": "runtime_error",
            "model_id": HSD_ADVISORY_MODEL_ID,
            "message": str(exc),
        }
    return {
        "active": True,
        "available": True,
        "status": "ok",
        "role": "hsd_utility_classifier",
        **comparison,
    }


def provider_status_template() -> dict[str, Any]:
    status = model_status()["span_providers"]
    return {
        name: {
            "enabled": False,
            "available": bool(status.get(name, {}).get("available", False)),
            "status": "not_requested",
        }
        for name in sorted(SUPPORTED_PROVIDER_NAMES)
    }


def selected_provider_names(request: PrivatizeRequest) -> list[str]:
    names = [name.strip().lower() for name in request.providers if name.strip()]
    if request.use_presidio and "presidio" not in names:
        names.append("presidio")
    return [name for name in names if name in SUPPORTED_PROVIDER_NAMES]


def run_selected_span_providers(
    text: str,
    names: list[str],
    *,
    gliner_model: str | None = None,
    gliner_profile: str = "general",
) -> tuple[list[Any], dict[str, Any]]:
    candidates = []
    report = provider_status_template()
    for name in names:
        try:
            provider_kwargs = (
                {"gliner_model": gliner_model, "gliner_profile": gliner_profile}
                if name == "gliner"
                else {}
            )
            provider: SpanProvider = load_span_provider(name, **provider_kwargs)
            output = provider.propose(text)
        except Exception as exc:
            report[name] = {
                **report.get(name, {}),
                "enabled": True,
                "status": "error",
                "error_class": type(exc).__name__,
                "message": str(exc),
            }
            continue
        candidates.extend(output.spans)
        report[name] = {
            **report.get(name, {}),
            "enabled": True,
            "status": "ready",
            "audit": output.audit,
            "accepted_span_count": len(output.spans),
        }
    return candidates, report


def llm_review_guidance(
    *,
    metric: dict[str, Any],
    cue: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    if metric.get("warnings"):
        reasons.extend(str(item) for item in metric["warnings"])
    if cue.get("loss_groups"):
        reasons.extend(f"cue_loss:{item}" for item in cue["loss_groups"])
    context_tags = set(context["original"].get("context_tags", []))
    for tag in (
        "quoted_or_reported",
        "counterspeech",
        "negated_hate",
        "missing_context",
        "public_interest_or_institutional_criticism",
    ):
        if tag in context_tags:
            reasons.append(f"context:{tag}")
    recommend = bool(reasons)
    return {
        "active": False,
        "recommend_review": recommend,
        "role": "last_resort_semantic_review",
        "reasons": sorted(set(reasons)),
        "message": (
            "Route to local LLM/human semantic review only if these reasons "
            "matter after deterministic audit. The workbench does not call an "
            "LLM automatically."
        ),
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/model-status")
def get_model_status() -> dict[str, Any]:
    return model_status()


@app.post("/api/privatize", response_model=PrivatizeResponse)
def privatize(request: PrivatizeRequest) -> dict[str, Any]:
    if request.mode not in MODES:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {request.mode}")
    if len(request.text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=413,
            detail=f"Text must be at most {MAX_TEXT_LENGTH} characters.",
        )

    config = PrivatizerConfig(
        mode=request.mode,
        generalize_targets=request.generalize_targets,
        style_scrub=request.style_scrub,
    )
    provider_names = selected_provider_names(request)
    provider_candidates, provider_report = run_selected_span_providers(
        request.text,
        provider_names,
        gliner_model=request.gliner_model,
        gliner_profile=request.gliner_profile,
    )
    presidio_status = provider_report.get("presidio", {})
    presidio_audit = presidio_status.get("audit")
    presidio_report: dict[str, Any] = (
        {
            **presidio_audit,
            "available": presidio_status.get("available", presidio_available()),
        }
        if isinstance(presidio_audit, dict)
        else {
            "enabled": bool(presidio_status.get("enabled", False)),
            "available": presidio_status.get("available", presidio_available()),
            "status": presidio_status.get("status", "not_requested"),
            "error": presidio_status.get("message"),
        }
    )
    result = privatize_text(
        request.text,
        config,
        provider_candidates=provider_candidates,
    )
    metric = row_metric(request.text, result.text)
    cue = row_cue_report(
        row_index=1,
        row_id="demo",
        original=request.text,
        privatized=result.text,
        threshold=1.0,
    )
    context = {
        "original": analyze_context(request.text),
        "privatized": analyze_context(result.text),
    }
    protected_spans = [
        clean_span(span, role="protect") for span in target_group_spans(request.text)
    ]
    protected_output_spans = [
        clean_span(span, role="protect") for span in target_group_spans(result.text)
    ]
    gauges = {
        "privacy_gain": pct(float(metric.get("privacy_gain", 0.0) or 0.0)),
        "residual_risk": residual_risk(metric),
        "cue_retention": cue_retention(cue),
        "text_similarity": pct(float(metric.get("character_utility_retention", 1.0))),
    }
    warnings = sorted(
        {
            *metric.get("warnings", []),
            *cue.get("loss_groups", []),
            *context["original"].get("context_tags", []),
        }
    )
    model_advisory = (
        run_token_policy_ensemble(request.text)
        if request.run_model_ensemble
        else {
            "active": False,
            "available": model_status()["token_policy_ensemble"]["available"],
            "status": "not_requested",
            "message": "Enable Run ensemble to load RoBERTa + HateBERT advisory predictions.",
            "metrics": read_ensemble_metrics(),
        }
    )
    hsd_classifier = (
        run_hsd_classifier(request.text, result.text)
        if request.run_hsd_classifier
        else {
            "active": False,
            "available": model_status()["hsd_classifiers"]["primary"]["available"],
            "status": "not_requested",
            "model_id": HSD_ADVISORY_MODEL_ID,
            "message": "Enable Run HSD classifier to score original/protected drift.",
        }
    )
    llm_guidance = llm_review_guidance(metric=metric, cue=cue, context=context)
    return {
        "privatized_text": result.text,
        "mode": request.mode,
        "changed": bool(metric.get("privacy_identifier_count_before", 0))
        or request.text != result.text,
        "transformations": clean_transformations(list(result.transformations)),
        "protected_spans": protected_spans,
        "protected_output_spans": protected_output_spans,
        "presidio_augment": presidio_report,
        "metrics": metric,
        "cue_report": cue,
        "context": context,
        "gauges": gauges,
        "warnings": warnings,
        "model_advisory": model_advisory,
        "hsd_classifier": hsd_classifier,
        "llm_guidance": llm_guidance,
        "span_providers": provider_report,
    }


@app.post("/api/csv/cache")
def lookup_csv_cache(request: CsvPrivatizeRequest) -> dict[str, Any]:
    _rows, fieldnames = parse_csv_text(request.csv_text)
    validate_csv_request(request, fieldnames)
    cache_key, options = csv_result_cache_key(request)
    record = read_csv_result_cache(cache_key)
    if record is None:
        return {
            "cache_hit": False,
            "cache": cache_metadata(
                hit=False,
                cache_key=cache_key,
                options=options,
            ),
            "result": None,
        }
    return {
        "cache_hit": True,
        "cache": cache_metadata(
            hit=True,
            cache_key=cache_key,
            options=options,
            created_at=record.get("created_at"),
        ),
        "result": cached_csv_response(
            cache_key=cache_key,
            options=options,
            record=record,
        ),
    }


@app.post("/api/csv/privatize", response_model=CsvPrivatizeResponse)
def privatize_csv(request: CsvPrivatizeRequest) -> dict[str, Any]:
    rows, fieldnames = parse_csv_text(request.csv_text)
    validate_csv_request(request, fieldnames)
    cache_key, cache_options = csv_result_cache_key(request)
    cached_record = read_csv_result_cache(cache_key)
    if cached_record is not None:
        cached_response = cached_csv_response(
            cache_key=cache_key,
            options=cache_options,
            record=cached_record,
        )
        if cached_response is not None:
            return cached_response

    from contextsafe_hsd.auto import AutoPipelineConfig, AutoPipelineContext, AutoPipelineEngine

    disabled_models = (
        frozenset(request.disabled_models)
        if request.disabled_models
        else CSV_INSIGHT_DEFAULT_DISABLED_MODELS
    )

    context = AutoPipelineContext.create(
        AutoPipelineConfig(
            metric_depth=request.metric_depth,
            disabled_providers=frozenset(request.disabled_providers),
            disabled_models=disabled_models,
            audit_level="row",
            style_scrub=request.style_scrub,
            generalize_targets=(
                request.generalize_targets
                if request.generalize_targets is not None
                else False
            ),
            gliner_model=request.gliner_model,
            gliner_profile=request.gliner_profile,
        )
    )
    engine_result = AutoPipelineEngine(context).process_rows(
        rows,
        fieldnames,
        text_col=request.text_col,
        id_col=request.id_col,
        output_col=request.output_col,
        replace_text=request.replace_text,
    )
    output_csv = write_csv_text(engine_result.rows, engine_result.fieldnames)
    helper_columns = [
        column for column in engine_result.fieldnames if column not in fieldnames
    ]
    validation = {
        "valid": (
            len(engine_result.rows) == len(rows)
            and (
                not request.replace_text
                or engine_result.fieldnames == fieldnames
            )
        ),
        "source_row_count": len(rows),
        "output_row_count": len(engine_result.rows),
        "source_columns": fieldnames,
        "output_columns": engine_result.fieldnames,
        "replace_text": request.replace_text,
        "helper_columns": helper_columns,
    }
    summary = {
        **engine_result.summary,
        "artifact_type": "workbench_csv_audit",
        "validation": validation,
    }
    manifest = {
        "artifact_type": "workbench_csv_manifest",
        "row_count": len(rows),
        "mode": "auto",
        "metric_depth": request.metric_depth,
        "providers": context.provider_status,
        "models": context.model_status,
        "load_counts": {
            "providers": dict(sorted(context.provider_load_counts.items())),
            "models": dict(sorted(context.model_load_counts.items())),
        },
        "columns": {
            "text_col": request.text_col,
            "id_col": request.id_col,
            "output_col": request.text_col if request.replace_text else request.output_col,
            "preserved_columns": fieldnames,
        },
        "validation": validation,
        "metrics": summary["metrics"],
        "pipeline_profile": current_auto_pipeline_profile(
            disabled_models=disabled_models
        ),
    }
    insight_output_col = request.text_col if request.replace_text else request.output_col
    platform_insights = platform_insight_report(
        original_rows=rows,
        output_rows=engine_result.rows,
        text_col=request.text_col,
        output_col=insight_output_col,
        aggregate=summary["metrics"],
        audit_rows=engine_result.audit_rows,
        id_col=request.id_col,
    )
    preview_rows = [
        csv_preview_row(
            row,
            row_id=row.get(request.id_col) if request.id_col else str(index + 1),
            text_col=request.text_col,
            output_col=insight_output_col,
        )
        for index, row in enumerate(engine_result.rows[:MAX_PREVIEW_ROWS])
    ]
    response = {
        "output_csv": output_csv,
        "audit": {"summary": summary, "rows": engine_result.audit_rows},
        "manifest": manifest,
        "platform_insights": platform_insights,
        "preview_rows": preview_rows,
    }
    response["cache"] = write_csv_result_cache(
        cache_key=cache_key,
        options=cache_options,
        result=response,
    )
    return response
