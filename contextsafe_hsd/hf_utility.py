"""Optional Hugging Face utility evaluator for privatized hate-speech text."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean
import time
from typing import Any

from .csv_pipeline import read_csv, write_json
from .row_ids import report_row_id


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
DEFAULT_DEVICE = "cpu"
POSITIVE_GOLD_LABELS = frozenset(
    {
        "abuse",
        "abusive",
        "hate",
        "hateful",
        "offensive",
        "toxic",
    }
)
NEGATIVE_GOLD_LABELS = frozenset(
    {
        "clean",
        "neutral",
        "non_abuse",
        "non_abusive",
        "non_hate",
        "normal",
        "not_abuse",
        "not_abusive",
        "not_hate",
    }
)


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
    pipeline_compatible: bool = True
    custom_loader_note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task": self.task,
            "default": self.default,
            "positive_label_hints": list(self.positive_label_hints),
            "runtime_note": self.runtime_note,
            "license_note": self.license_note,
            "pipeline_compatible": self.pipeline_compatible,
            "custom_loader_note": self.custom_loader_note,
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
        model_id="cardiffnlp/twitter-roberta-base-hate-multiclass-latest",
        task="text-classification",
        default=False,
        positive_label_hints=(
            "sexism",
            "racism",
            "disability",
            "sexual_orientation",
            "religion",
            "other",
            "hate",
        ),
        runtime_note=(
            "Target-category drift probe for anonymization utility audits; "
            "opt-in for classification because it is multiclass."
        ),
        license_note="CC-BY 4.0. Review the live Hugging Face model card before full runs.",
    ),
    HfUtilityModel(
        model_id="Hate-speech-CNERG/bert-base-uncased-hatexplain",
        task="text-classification",
        default=False,
        positive_label_hints=("hate", "offensive", "toxic", "abusive"),
        runtime_note=(
            "HateXplain-family utility and explainability probe; generic "
            "Transformers pipeline failed in local smoke tests."
        ),
        pipeline_compatible=False,
        custom_loader_note=(
            "Local generic pipeline inference fails with tuple index out of range; "
            "add a validated custom loader before trusting scores."
        ),
    ),
    HfUtilityModel(
        model_id="Hate-speech-CNERG/bert-base-uncased-hatexplain-rationale-two",
        task="text-classification",
        default=False,
        positive_label_hints=("hate", "offensive", "toxic", "abusive"),
        runtime_note=(
            "HateXplain rationale-family probe; requires the repository's "
            "custom Model_Rational_Label loader for trustworthy scores."
        ),
        pipeline_compatible=False,
        custom_loader_note=(
            "Model card warns generic hosted/API predictions may be wrong due "
            "to different class initialisations."
        ),
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
        row_id = report_row_id(row, row_index=row_index, id_col=id_col)
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


def normalize_gold_label(label: str | None) -> bool | None:
    normalized = str(label or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized or "ambiguous" in normalized:
        return None
    if normalized in POSITIVE_GOLD_LABELS:
        return True
    if normalized in NEGATIVE_GOLD_LABELS:
        return False
    return None


def binary_confusion_metrics(
    gold: list[bool],
    predictions: list[bool],
) -> dict[str, Any]:
    tp = sum(expected and predicted for expected, predicted in zip(gold, predictions))
    tn = sum(
        (not expected) and (not predicted)
        for expected, predicted in zip(gold, predictions)
    )
    fp = sum(
        (not expected) and predicted
        for expected, predicted in zip(gold, predictions)
    )
    fn = sum(expected and (not predicted) for expected, predicted in zip(gold, predictions))
    total = len(gold)

    def divide(numerator: int, denominator: int) -> float:
        return float(numerator) / denominator if denominator else 0.0

    positive_precision = divide(tp, tp + fp)
    positive_recall = divide(tp, tp + fn)
    negative_precision = divide(tn, tn + fn)
    negative_recall = divide(tn, tn + fp)

    def f1(precision: float, recall: float) -> float:
        return 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    positive_f1 = f1(positive_precision, positive_recall)
    negative_f1 = f1(negative_precision, negative_recall)
    return {
        "accuracy": rounded(divide(tp + tn, total)) if total else 0.0,
        "macro_f1": rounded((positive_f1 + negative_f1) / 2.0) if total else 0.0,
        "positive_precision": rounded(positive_precision),
        "positive_recall": rounded(positive_recall),
        "negative_precision": rounded(negative_precision),
        "negative_recall": rounded(negative_recall),
        "confusion": {
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
        },
    }


def label_alignment_report(
    samples: list[HfUtilitySample],
    *,
    original_scores: list[float],
    privatized_scores: list[float],
    decision_threshold: float,
) -> dict[str, Any] | None:
    gold: list[bool] = []
    original_predictions: list[bool] = []
    privatized_predictions: list[bool] = []
    evaluated_rows: list[tuple[HfUtilitySample, bool, bool, bool, float, float]] = []
    skipped = 0
    for sample, original_score, privatized_score in zip(
        samples,
        original_scores,
        privatized_scores,
    ):
        expected = normalize_gold_label(sample.label)
        if expected is None:
            skipped += 1
            continue
        original_prediction = original_score >= decision_threshold
        privatized_prediction = privatized_score >= decision_threshold
        gold.append(expected)
        original_predictions.append(original_prediction)
        privatized_predictions.append(privatized_prediction)
        evaluated_rows.append(
            (
                sample,
                expected,
                original_prediction,
                privatized_prediction,
                original_score,
                privatized_score,
            )
        )
    if not gold and skipped == 0:
        return None
    original = binary_confusion_metrics(gold, original_predictions)
    privatized = binary_confusion_metrics(gold, privatized_predictions)
    utility_label_drop_rows = [
        {
            "row_index": sample.row_index,
            "row_id": sample.row_id,
            "label": sample.label,
            "original_score": rounded(original_score),
            "privatized_score": rounded(privatized_score),
            "original_prediction": "positive" if original_prediction else "negative",
            "privatized_prediction": "positive" if privatized_prediction else "negative",
        }
        for (
            sample,
            expected,
            original_prediction,
            privatized_prediction,
            original_score,
            privatized_score,
        ) in evaluated_rows
        if original_prediction == expected and privatized_prediction != expected
    ]
    utility_label_drop_rows.sort(
        key=lambda item: abs(item["original_score"] - item["privatized_score"]),
        reverse=True,
    )
    return {
        "evaluated_count": len(gold),
        "skipped_count": skipped,
        "positive_gold_count": sum(gold),
        "negative_gold_count": len(gold) - sum(gold),
        "decision_threshold": decision_threshold,
        "original": original,
        "privatized": privatized,
        "delta": {
            "accuracy": rounded(privatized["accuracy"] - original["accuracy"]),
            "macro_f1": rounded(privatized["macro_f1"] - original["macro_f1"]),
            "positive_recall": rounded(
                privatized["positive_recall"] - original["positive_recall"]
            ),
        },
        "utility_label_drop_rows": utility_label_drop_rows[:20],
    }


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
    if not model.pipeline_compatible:
        return skipped_model_result(
            model.model_id,
            reason="custom_loader_required",
            detail=model.custom_loader_note or model.runtime_note,
            device=device,
            sample_size=len(samples),
        )
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
        "label_alignment": label_alignment_report(
            samples,
            original_scores=original_scores,
            privatized_scores=privatized_scores,
            decision_threshold=decision_threshold,
        ),
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

    if not any(model.pipeline_compatible for model in models):
        result["models"] = [
            skipped_model_result(
                model.model_id,
                reason="custom_loader_required",
                detail=model.custom_loader_note or model.runtime_note,
                device=device,
                sample_size=len(samples),
            )
            for model in models
        ]
        if output_path:
            write_json(output_path, result)
        return result

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
