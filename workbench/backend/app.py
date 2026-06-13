"""FastAPI wrapper for the local Privacy Review Workbench."""

from __future__ import annotations

from collections import Counter
import csv
from functools import lru_cache
import importlib.util
import io
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from privhsd.context import analyze_context
from privhsd.cue_checks import row_cue_report
from privhsd.detectors import Span, target_group_spans
from privhsd.metrics import aggregate_metrics, row_metric, row_metric_for_depth
from privhsd.pipeline import MODES, PrivatizerConfig, privatize_text
from privhsd.rerank import choose_candidate, generate_candidates_with_rejections
from privhsd.span_providers.base import SpanProvider
from privhsd.span_providers.registry import (
    SUPPORTED_PROVIDER_NAMES,
    SpanProviderRegistryError,
    load_span_provider,
    load_span_providers,
)


MAX_TEXT_LENGTH = 20_000
MAX_CSV_LENGTH = 5_000_000
MAX_PREVIEW_ROWS = 25
ROOT = Path(__file__).resolve().parents[2]
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
    mode: Literal["auto", "utility", "balanced", "privacy", "rerank"] = "auto"
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
    preview_rows: list[dict[str, Any]]


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
    if request.mode not in {*MODES, "rerank", "auto"}:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {request.mode}")


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
                "active_by_default": False,
            },
            "gliner": {
                "available": module_available("gliner"),
                "active_by_default": False,
            },
            "scrubadub": {
                "available": module_available("scrubadub"),
                "active_by_default": False,
            },
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


@lru_cache(maxsize=1)
def load_hsd_classifier() -> Any:
    from privhsd.models.hsd_advisory_runtime import HsdAdvisoryRuntime

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


@app.post("/api/csv/privatize", response_model=CsvPrivatizeResponse)
def privatize_csv(request: CsvPrivatizeRequest) -> dict[str, Any]:
    rows, fieldnames = parse_csv_text(request.csv_text)
    validate_csv_request(request, fieldnames)
    if request.mode == "auto":
        from privhsd.auto import AutoPipelineConfig, AutoPipelineContext, AutoPipelineEngine

        context = AutoPipelineContext.create(
            AutoPipelineConfig(
                metric_depth=request.metric_depth,
                disabled_providers=frozenset(request.disabled_providers),
                disabled_models=frozenset(request.disabled_models),
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
        }
        preview_rows = [
            csv_preview_row(
                row,
                row_id=row.get(request.id_col) if request.id_col else str(index + 1),
                text_col=request.text_col,
                output_col=request.text_col if request.replace_text else request.output_col,
            )
            for index, row in enumerate(engine_result.rows[:MAX_PREVIEW_ROWS])
        ]
        return {
            "output_csv": output_csv,
            "audit": {"summary": summary, "rows": engine_result.audit_rows},
            "manifest": manifest,
            "preview_rows": preview_rows,
        }

    provider_names = [name.strip().lower() for name in request.providers if name.strip()]
    try:
        providers = load_span_providers(
            provider_names,
            gliner_model=request.gliner_model,
            gliner_profile=request.gliner_profile,
        )
    except (SpanProviderRegistryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    output_fieldnames = list(fieldnames)
    output_col = request.text_col if request.replace_text else request.output_col
    if not request.replace_text and output_col not in output_fieldnames:
        output_fieldnames.append(output_col)

    config = PrivatizerConfig(
        mode=request.mode if request.mode in MODES else "balanced",
        generalize_targets=request.generalize_targets,
        style_scrub=request.style_scrub,
    )
    output_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    chosen_counts: Counter[str] = Counter()
    provider_errors: Counter[str] = Counter()
    rejected_rewrite_counts: Counter[str] = Counter()

    for row_index, row in enumerate(rows, start=1):
        original = str(row.get(request.text_col, "") or "")
        row_id = row.get(request.id_col) if request.id_col else str(row_index)
        output_row = dict(row)
        candidate_metadata: dict[str, Any] = {}
        rejected_rewrite_candidates: list[dict[str, Any]] = []
        chosen_name = request.mode
        if request.mode == "rerank":
            try:
                candidates, rejected_rewrite_candidates = (
                    generate_candidates_with_rejections(
                        original,
                        span_providers=providers,
                    )
                )
            except Exception as exc:
                provider_errors[type(exc).__name__] += 1
                candidates, rejected_rewrite_candidates = (
                    generate_candidates_with_rejections(original)
                )
            chosen, scores = choose_candidate(original, candidates)
            chosen_counts[chosen.name] += 1
            chosen_name = chosen.name
            privatized = chosen.text
            candidate_metadata = {
                candidate.name: candidate.metadata
                for candidate in candidates
                if candidate.metadata
            }
        else:
            provider_candidates = []
            provider_reports = {}
            for provider in providers:
                try:
                    provider_output = provider.propose(original)
                except Exception as exc:
                    provider_errors[type(exc).__name__] += 1
                    continue
                provider_candidates.extend(provider_output.spans)
                provider_reports[provider_output.provider] = provider_output.audit
            result = privatize_text(
                original,
                config,
                provider_candidates=provider_candidates,
            )
            privatized = result.text
            chosen_counts[request.mode] += 1
            scores = []
            candidate_metadata = {
                "providers": provider_reports,
                "provider_fusion": result.provider_audit,
            }

        output_row[output_col] = privatized
        output_rows.append(output_row)
        metrics = row_metric_for_depth(
            original,
            privatized,
            metric_depth=request.metric_depth,
            row_index=row_index,
        )
        metric_rows.append(metrics)
        for rejected in rejected_rewrite_candidates:
            for reason in rejected.get("validation", {}).get("reasons", []):
                rejected_rewrite_counts[str(reason)] += 1
        audit_rows.append(
            {
                "row_id": row_id,
                "row_index": row_index,
                "changed": original != privatized,
                "chosen": chosen_name,
                "metrics": metrics,
                "scores": scores,
                "candidate_metadata": candidate_metadata,
                "rejected_rewrite_candidates": rejected_rewrite_candidates,
            }
        )

    output_csv = write_csv_text(output_rows, output_fieldnames)
    validation = {
        "valid": len(output_rows) == len(rows),
        "source_row_count": len(rows),
        "output_row_count": len(output_rows),
        "source_columns": fieldnames,
        "output_columns": output_fieldnames,
        "replace_text": request.replace_text,
        "helper_columns": [
            column for column in output_fieldnames if column not in fieldnames
        ],
    }
    summary = {
        "artifact_type": "workbench_csv_audit",
        "row_count": len(rows),
        "text_col": request.text_col,
        "id_col": request.id_col,
        "output_col": output_col,
        "mode": request.mode,
        "metric_depth": request.metric_depth,
        "style_scrub": request.style_scrub,
        "generalize_targets": config.target_generalization_enabled,
        "providers": provider_names,
        "provider_error_counts": dict(sorted(provider_errors.items())),
        "chosen_counts": dict(sorted(chosen_counts.items())),
        "rejected_rewrite_counts": dict(sorted(rejected_rewrite_counts.items())),
        "metrics": aggregate_metrics(metric_rows),
        "validation": validation,
    }
    manifest = {
        "artifact_type": "workbench_csv_manifest",
        "row_count": len(rows),
        "mode": request.mode,
        "providers": provider_names,
        "columns": {
            "text_col": request.text_col,
            "id_col": request.id_col,
            "output_col": output_col,
            "preserved_columns": fieldnames,
        },
        "validation": validation,
        "metrics": summary["metrics"],
    }
    preview_rows = [
        csv_preview_row(
            row,
            row_id=row.get(request.id_col) if request.id_col else str(index + 1),
            text_col=request.text_col,
            output_col=output_col,
        )
        for index, row in enumerate(output_rows[:MAX_PREVIEW_ROWS])
    ]
    return {
        "output_csv": output_csv,
        "audit": {"summary": summary, "rows": audit_rows},
        "manifest": manifest,
        "preview_rows": preview_rows,
    }
