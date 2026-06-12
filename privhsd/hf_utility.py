"""Optional Hugging Face utility evaluator for privatized hate-speech text."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean
import time
from typing import Any

from .csv_pipeline import read_csv, write_json


INSTALL_HINT = (
    "Install optional Hugging Face evaluator dependencies with: "
    "python -m pip install '.[hf-utility]'"
)
HF_UTILITY_WARNING = (
    "This evaluator uses optional third-party Hugging Face classifiers as "
    "relative utility probes. It is not the official PrivHSD evaluator and "
    "model cards/licenses should be reviewed before full-dataset runs."
)
DEFAULT_SAMPLE_SIZE = 100
DEFAULT_DROP_THRESHOLD = 0.25
DEFAULT_DECISION_THRESHOLD = 0.5
DEFAULT_DEVICE = "auto"


class HfUtilityError(ValueError):
    pass


@dataclass(frozen=True)
class HfUtilityModel:
    model_id: str
    task: str
    default: bool
    positive_label_hints: tuple[str, ...]
    runtime_note: str
    license_note: str = "Review the live Hugging Face model card before full runs."

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task": self.task,
            "default": self.default,
            "positive_label_hints": list(self.positive_label_hints),
            "runtime_note": self.runtime_note,
            "license_note": self.license_note,
            "approved_use": "optional HSD/toxicity utility evaluation only",
        }


APPROVED_MODELS: tuple[HfUtilityModel, ...] = (
    HfUtilityModel(
        model_id="facebook/roberta-hate-speech-dynabench-r4-target",
        task="text-classification",
        default=True,
        positive_label_hints=("hate", "offensive", "toxic", "abusive"),
        runtime_note="Dynabench-aligned hate-speech utility probe.",
    ),
    HfUtilityModel(
        model_id="cardiffnlp/twitter-roberta-base-hate-latest",
        task="text-classification",
        default=True,
        positive_label_hints=("hate", "offensive", "toxic", "abusive"),
        runtime_note="Social-media hate/offensive utility probe.",
    ),
    HfUtilityModel(
        model_id="Hate-speech-CNERG/bert-base-uncased-hatexplain",
        task="text-classification",
        default=False,
        positive_label_hints=("hate", "offensive", "toxic", "abusive"),
        runtime_note="HateXplain-family utility and explainability probe.",
    ),
    HfUtilityModel(
        model_id="Hate-speech-CNERG/bert-base-uncased-hatexplain-rationale-two",
        task="text-classification",
        default=False,
        positive_label_hints=("hate", "offensive", "toxic", "abusive"),
        runtime_note="HateXplain rationale-family probe; may be slower or unavailable.",
    ),
    HfUtilityModel(
        model_id="unitary/toxic-bert",
        task="text-classification",
        default=False,
        positive_label_hints=("toxic", "severe", "obscene", "threat", "insult", "hate"),
        runtime_note="Toxicity proxy for weak-signal comparison, not HSD-specific.",
    ),
)


def approved_model_ids(*, defaults_only: bool = False) -> list[str]:
    models = APPROVED_MODELS
    if defaults_only:
        models = tuple(model for model in models if model.default)
    return [model.model_id for model in models]


def model_registry_manifest() -> dict[str, Any]:
    return {
        "registry_type": "hf_utility_models",
        "warning": HF_UTILITY_WARNING,
        "default_sample_size": DEFAULT_SAMPLE_SIZE,
        "models": [model.as_dict() for model in APPROVED_MODELS],
    }


def write_model_registry(output_path: Path | None = None) -> dict[str, Any]:
    manifest = model_registry_manifest()
    if output_path:
        write_json(output_path, manifest)
    return manifest


@dataclass(frozen=True)
class HfUtilitySample:
    row_index: int
    row_id: str
    original_text: str
    privatized_text: str
    label: str | None = None


def load_hf_stack() -> dict[str, Any]:
    try:
        from transformers import pipeline
    except ModuleNotFoundError as exc:
        if exc.name == "transformers":
            raise HfUtilityError(INSTALL_HINT) from exc
        raise
    return {"pipeline": pipeline}


def validate_columns(
    input_path: Path,
    fieldnames: list[str],
    *,
    text_col: str,
    privatized_col: str,
    id_col: str | None,
    label_col: str | None,
) -> None:
    missing = [column for column in (text_col, privatized_col, id_col, label_col) if column]
    missing = [column for column in missing if column not in fieldnames]
    if missing:
        raise HfUtilityError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )


def collect_samples(
    rows: list[dict[str, str]],
    *,
    text_col: str,
    privatized_col: str,
    id_col: str | None,
    label_col: str | None,
    sample_size: int | None,
) -> list[HfUtilitySample]:
    limit = len(rows) if sample_size is None or sample_size <= 0 else sample_size
    samples: list[HfUtilitySample] = []
    for row_index, row in enumerate(rows[:limit], start=1):
        row_id = str(row.get(id_col, "") or row_index) if id_col else str(row_index)
        samples.append(
            HfUtilitySample(
                row_index=row_index,
                row_id=row_id,
                original_text=str(row.get(text_col, "") or ""),
                privatized_text=str(row.get(privatized_col, "") or ""),
                label=str(row.get(label_col, "") or "") if label_col else None,
            )
        )
    return samples


def rounded(value: float) -> float:
    return round(float(value), 4)


def normalize_pipeline_output(output: Any) -> list[list[dict[str, float | str]]]:
    if not isinstance(output, list):
        return []
    if not output:
        return []
    if isinstance(output[0], dict):
        return [[dict(item)] for item in output]
    normalized: list[list[dict[str, float | str]]] = []
    for item in output:
        if isinstance(item, list):
            normalized.append([dict(score) for score in item if isinstance(score, dict)])
        elif isinstance(item, dict):
            normalized.append([dict(item)])
        else:
            normalized.append([])
    return normalized


def positive_score(
    scores: list[dict[str, Any]],
    *,
    positive_label_hints: tuple[str, ...],
) -> float:
    if not scores:
        return 0.0
    positive_candidates = []
    negative_hints = ("not", "non", "neutral", "normal", "clean", "none")
    for score in scores:
        label = str(score.get("label", "")).lower()
        value = float(score.get("score", 0.0) or 0.0)
        if any(hint in label for hint in positive_label_hints) and not any(
            hint in label for hint in negative_hints
        ):
            positive_candidates.append(value)
    if positive_candidates:
        return max(positive_candidates)
    if len(scores) == 2:
        for score in scores:
            if str(score.get("label", "")).lower() in {"label_1", "1"}:
                return float(score.get("score", 0.0) or 0.0)
    return max(float(score.get("score", 0.0) or 0.0) for score in scores)


def pipeline_revision(classifier: Any) -> str | None:
    model = getattr(classifier, "model", None)
    config = getattr(model, "config", None)
    revision = getattr(config, "_commit_hash", None)
    return str(revision) if revision else None


def skipped_model_result(
    model_id: str,
    *,
    reason: str,
    detail: str,
    device: str,
    sample_size: int,
) -> dict[str, Any]:
    return {
        "model": model_id,
        "status": "skipped",
        "skip_reason": reason,
        "detail": detail,
        "device": device,
        "runtime_seconds": 0.0,
        "sample_size": sample_size,
    }


def resolve_device(device: str) -> tuple[int | str, str]:
    requested = str(device or DEFAULT_DEVICE).strip().lower()
    if requested in {"cpu", "-1"}:
        return -1, "cpu"
    if requested == "auto":
        try:
            import torch
        except Exception:
            return -1, "cpu"
        if torch.cuda.is_available():
            return 0, "cuda:0"
        return -1, "cpu"
    if requested.startswith("cuda"):
        try:
            import torch
        except Exception as exc:
            raise HfUtilityError(
                "CUDA was requested but torch is unavailable or CPU-only"
            ) from exc
        if not torch.cuda.is_available():
            raise HfUtilityError(
                "CUDA was requested but torch.cuda.is_available() is false"
            )
        if ":" in requested:
            return int(requested.split(":", 1)[1]), requested
        return 0, "cuda:0"
    try:
        return int(requested), f"cuda:{int(requested)}"
    except ValueError:
        return requested, requested


def score_with_model(
    hf: dict[str, Any],
    model: HfUtilityModel,
    *,
    samples: list[HfUtilitySample],
    device: str,
    batch_size: int,
    drop_threshold: float,
    decision_threshold: float,
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        device_arg, resolved_device = resolve_device(device)
    except HfUtilityError as exc:
        return skipped_model_result(
            model.model_id,
            reason="device_unavailable",
            detail=str(exc),
            device=device,
            sample_size=len(samples),
        )
    try:
        classifier = hf["pipeline"](
            model.task,
            model=model.model_id,
            tokenizer=model.model_id,
            top_k=None,
            truncation=True,
            device=device_arg,
        )
    except Exception as exc:  # pragma: no cover - exercised through tests with fakes
        return skipped_model_result(
            model.model_id,
            reason="model_load_failed",
            detail=str(exc),
            device=resolved_device,
            sample_size=len(samples),
        )

    try:
        original_output = classifier(
            [sample.original_text for sample in samples],
            batch_size=batch_size,
            truncation=True,
        )
        privatized_output = classifier(
            [sample.privatized_text for sample in samples],
            batch_size=batch_size,
            truncation=True,
        )
    except Exception as exc:  # pragma: no cover - exercised through tests with fakes
        return skipped_model_result(
            model.model_id,
            reason="model_inference_failed",
            detail=str(exc),
            device=resolved_device,
            sample_size=len(samples),
        )

    original_scores = [
        positive_score(scores, positive_label_hints=model.positive_label_hints)
        for scores in normalize_pipeline_output(original_output)
    ]
    privatized_scores = [
        positive_score(scores, positive_label_hints=model.positive_label_hints)
        for scores in normalize_pipeline_output(privatized_output)
    ]
    if len(original_scores) != len(samples) or len(privatized_scores) != len(samples):
        return skipped_model_result(
            model.model_id,
            reason="unexpected_model_output",
            detail="pipeline returned a different number of rows than requested",
            device=resolved_device,
            sample_size=len(samples),
        )

    deltas = [
        protected - original
        for original, protected in zip(original_scores, privatized_scores)
    ]
    abs_drifts = [abs(delta) for delta in deltas]
    agreements = [
        (original >= decision_threshold) == (protected >= decision_threshold)
        for original, protected in zip(original_scores, privatized_scores)
    ]
    large_drops = [
        {
            "row_index": sample.row_index,
            "row_id": sample.row_id,
            "original_score": rounded(original),
            "privatized_score": rounded(protected),
            "drop": rounded(original - protected),
        }
        for sample, original, protected in zip(
            samples,
            original_scores,
            privatized_scores,
        )
        if original - protected >= drop_threshold
    ]
    large_drops.sort(key=lambda item: item["drop"], reverse=True)
    runtime = time.perf_counter() - start
    return {
        "model": model.model_id,
        "status": "ok",
        "revision": pipeline_revision(classifier),
        "device": resolved_device,
        "runtime_seconds": rounded(runtime),
        "sample_size": len(samples),
        "score_drift": {
            "original_mean": rounded(mean(original_scores)) if original_scores else 0.0,
            "privatized_mean": rounded(mean(privatized_scores)) if privatized_scores else 0.0,
            "mean_delta": rounded(mean(deltas)) if deltas else 0.0,
            "mean_abs_drift": rounded(mean(abs_drifts)) if abs_drifts else 0.0,
            "decision_threshold": decision_threshold,
            "large_drop_threshold": drop_threshold,
        },
        "agreement": rounded(mean(agreements)) if agreements else 0.0,
        "large_utility_drop_rows": large_drops[:20],
    }


def resolve_models(model_ids: list[str] | None) -> list[HfUtilityModel]:
    registry = {model.model_id: model for model in APPROVED_MODELS}
    requested = model_ids or approved_model_ids(defaults_only=True)
    unknown = [model_id for model_id in requested if model_id not in registry]
    if unknown:
        raise HfUtilityError(
            "unknown HF utility model(s); use hf-model-registry: "
            + ", ".join(unknown)
        )
    return [registry[model_id] for model_id in requested]


def run_hf_utility_evaluation(
    input_path: Path,
    *,
    text_col: str,
    privatized_col: str = "privatized_text",
    id_col: str | None = None,
    label_col: str | None = None,
    output_path: Path | None = None,
    model_ids: list[str] | None = None,
    sample_size: int | None = DEFAULT_SAMPLE_SIZE,
    device: str = DEFAULT_DEVICE,
    batch_size: int = 8,
    drop_threshold: float = DEFAULT_DROP_THRESHOLD,
    decision_threshold: float = DEFAULT_DECISION_THRESHOLD,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        privatized_col=privatized_col,
        id_col=id_col,
        label_col=label_col,
    )
    samples = collect_samples(
        rows,
        text_col=text_col,
        privatized_col=privatized_col,
        id_col=id_col,
        label_col=label_col,
        sample_size=sample_size,
    )
    models = resolve_models(model_ids)
    result: dict[str, Any] = {
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "evaluator_type": "hf_utility",
        "status": "ok",
        "warning": HF_UTILITY_WARNING,
        "columns": {
            "text_col": text_col,
            "privatized_col": privatized_col,
            "id_col": id_col,
            "label_col": label_col,
        },
        "sample": {
            "requested_sample_size": sample_size,
            "sample_size": len(samples),
            "source_row_count": len(rows),
            "strategy": "first_n_rows",
        },
        "registry": model_registry_manifest(),
        "models": [],
    }

    try:
        hf = load_hf_stack()
    except HfUtilityError as exc:
        result["status"] = "skipped"
        result["skip_reason"] = "missing_optional_dependency"
        result["detail"] = str(exc)
        result["models"] = [
            skipped_model_result(
                model.model_id,
                reason="missing_optional_dependency",
                detail=str(exc),
                device=device,
                sample_size=len(samples),
            )
            for model in models
        ]
        if output_path:
            write_json(output_path, result)
        return result

    result["models"] = [
        score_with_model(
            hf,
            model,
            samples=samples,
            device=device,
            batch_size=batch_size,
            drop_threshold=drop_threshold,
            decision_threshold=decision_threshold,
        )
        for model in models
    ]
    if output_path:
        write_json(output_path, result)
    return result
