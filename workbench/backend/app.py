"""FastAPI wrapper for the local Privacy Review Workbench."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from privhsd.context import analyze_context
from privhsd.cue_checks import row_cue_report
from privhsd.detectors import Span, target_group_spans
from privhsd.metrics import row_metric
from privhsd.pipeline import MODES, PrivatizerConfig, privatize_text
from privhsd.presidio_augment import (
    PresidioAugmentError,
    filtered_presidio_spans,
    load_presidio_analyzer,
)


MAX_TEXT_LENGTH = 20_000
ROOT = Path(__file__).resolve().parents[2]
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
    run_model_ensemble: bool = False


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
    llm_guidance: dict[str, Any]


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


@lru_cache(maxsize=1)
def cached_presidio_analyzer() -> Any:
    return load_presidio_analyzer()


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
        "deterministic": {
            "active": True,
            "label": "Deterministic privacy and cue checks",
            "role": "Always runs. This is the submission-safe layer.",
        },
        "token_policy_ensemble": {
            "available": available,
            "active_by_default": False,
            "role": (
                "Optional advisory token-action model. It does not replace "
                "deterministic masking unless a reranking/audit path accepts it."
            ),
            "members": model_dirs,
            "metrics": read_ensemble_metrics(),
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
    }


@lru_cache(maxsize=1)
def load_ensemble() -> tuple[list[dict[str, Any]], list[float]]:
    from privhsd.token_policy import (
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
        from privhsd.token_policy import (
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
    extra_spans: list[Span] = []
    presidio_report: dict[str, Any] = {
        "enabled": False,
        "available": presidio_available(),
    }
    if request.use_presidio:
        try:
            extra_spans, presidio_report = filtered_presidio_spans(
                request.text,
                cached_presidio_analyzer(),
            )
            presidio_report["available"] = True
        except PresidioAugmentError as exc:
            presidio_report = {
                "enabled": False,
                "available": False,
                "error": str(exc),
            }
    result = privatize_text(request.text, config, extra_spans=extra_spans)
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
        "llm_guidance": llm_guidance,
    }
