"""Local baseline classifier workflows for hate-speech CSVs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from pathlib import Path
import pickle
from statistics import mean
from typing import Any

from .csv_pipeline import read_csv, write_csv, write_json
from .row_ids import report_row_id


INSTALL_HINT = (
    "Install optional classifier dependencies with: "
    "python -m pip install '.[classifier]'"
)
CLASSIFIER_WARNING = (
    "This is a lightweight local baseline classifier for reproducible "
    "development checks. It is not the official PrivHSD evaluator and should "
    "not be treated as a leaderboard score."
)
MODEL_FORMAT_VERSION = 1
DEFAULT_MODEL_PATH = Path("data/outputs/privhsd_classifier.pkl")
DEFAULT_TRAIN_REPORT_PATH = Path("data/outputs/privhsd_classifier.train.json")
DEFAULT_EVALUATE_REPORT_PATH = Path("data/outputs/privhsd_classifier.evaluate.json")
DEFAULT_PREDICTION_PATH = Path("data/outputs/privhsd_classifier.predictions.csv")


class ClassifierError(ValueError):
    pass


@dataclass(frozen=True)
class LabeledSample:
    row_index: int
    row_id: str
    text: str
    label: str


def load_sklearn() -> dict[str, Any]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import (
            accuracy_score,
            confusion_matrix,
            f1_score,
            precision_recall_fscore_support,
        )
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
    except ModuleNotFoundError as exc:
        if exc.name == "sklearn":
            raise ClassifierError(INSTALL_HINT) from exc
        raise
    return {
        "TfidfVectorizer": TfidfVectorizer,
        "LogisticRegression": LogisticRegression,
        "Pipeline": Pipeline,
        "accuracy_score": accuracy_score,
        "confusion_matrix": confusion_matrix,
        "f1_score": f1_score,
        "precision_recall_fscore_support": precision_recall_fscore_support,
        "train_test_split": train_test_split,
    }


def build_classifier(sklearn: dict[str, Any]) -> Any:
    return sklearn["Pipeline"](
        [
            (
                "tfidf",
                sklearn["TfidfVectorizer"](
                    lowercase=True,
                    ngram_range=(1, 2),
                    min_df=1,
                    sublinear_tf=True,
                ),
            ),
            (
                "classifier",
                sklearn["LogisticRegression"](
                    class_weight="balanced",
                    max_iter=1000,
                    random_state=0,
                ),
            ),
        ]
    )


def rounded(value: float) -> float:
    return round(float(value), 4)


def sorted_counts(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def validate_columns(
    input_path: Path,
    fieldnames: list[str],
    *,
    text_col: str,
    label_col: str | None = None,
    id_col: str | None = None,
) -> None:
    missing = [column for column in (text_col, label_col, id_col) if column]
    missing = [column for column in missing if column not in fieldnames]
    if missing:
        raise ClassifierError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )


def collect_labeled_samples(
    rows: list[dict[str, str]],
    *,
    text_col: str,
    label_col: str,
    id_col: str | None,
) -> list[LabeledSample]:
    samples: list[LabeledSample] = []
    for row_index, row in enumerate(rows, start=1):
        label = str(row.get(label_col, "") or "")
        if not label:
            raise ClassifierError(
                f"row {row_index}: missing label in column {label_col!r}"
            )
        row_id = report_row_id(row, row_index=row_index, id_col=id_col)
        samples.append(
            LabeledSample(
                row_index=row_index,
                row_id=row_id,
                text=str(row.get(text_col, "") or ""),
                label=label,
            )
        )
    return samples


def validate_split(labels: list[str], test_size: float) -> dict[str, Any]:
    if not 0 < test_size < 1:
        raise ClassifierError("--test-size must be greater than 0 and less than 1")
    counts = Counter(labels)
    if len(counts) < 2:
        raise ClassifierError("classifier training requires at least two labels")
    rare = sorted(label for label, count in counts.items() if count < 2)
    if rare:
        raise ClassifierError(
            "stratified classifier split requires at least two rows per label; "
            f"too few rows for: {', '.join(rare)}"
        )
    dev_count = math.ceil(len(labels) * test_size)
    train_count = len(labels) - dev_count
    if dev_count < len(counts):
        raise ClassifierError(
            "--test-size creates fewer dev rows than labels; increase --test-size"
        )
    if train_count < len(counts):
        raise ClassifierError(
            "--test-size leaves fewer training rows than labels; decrease --test-size"
        )
    return {
        "label_counts": dict(sorted(counts.items())),
        "dev_count": dev_count,
        "train_count": train_count,
    }


def confidence_values(model: Any, texts: list[str]) -> list[float]:
    if not texts:
        return []
    probabilities = model.predict_proba(texts)
    return [float(max(row_probs)) for row_probs in probabilities]


def confusion_counts(
    *,
    classes: list[str],
    matrix: list[list[int]],
) -> list[dict[str, Any]]:
    counts: list[dict[str, Any]] = []
    for true_index, true_label in enumerate(classes):
        for predicted_index, predicted_label in enumerate(classes):
            count = int(matrix[true_index][predicted_index])
            if count:
                counts.append(
                    {
                        "label": true_label,
                        "predicted_label": predicted_label,
                        "count": count,
                    }
                )
    return counts


def score_predictions(
    sklearn: dict[str, Any],
    *,
    labels: list[str],
    predictions: list[str],
    classes: list[str],
    confidences: list[float],
) -> dict[str, Any]:
    precision, recall, f1, support = sklearn["precision_recall_fscore_support"](
        labels,
        predictions,
        labels=classes,
        zero_division=0,
    )
    matrix = sklearn["confusion_matrix"](
        labels,
        predictions,
        labels=classes,
    ).tolist()
    return {
        "row_count": len(labels),
        "accuracy": rounded(sklearn["accuracy_score"](labels, predictions)),
        "macro_f1": rounded(
            sklearn["f1_score"](
                labels,
                predictions,
                labels=classes,
                average="macro",
                zero_division=0,
            )
        ),
        "per_label": {
            label: {
                "precision": rounded(precision[index]),
                "recall": rounded(recall[index]),
                "f1": rounded(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(classes)
        },
        "confusion_matrix": {
            "labels": classes,
            "matrix": [[int(value) for value in row] for row in matrix],
        },
        "confusion_counts": confusion_counts(classes=classes, matrix=matrix),
        "prediction_counts": sorted_counts(predictions),
        "label_counts": sorted_counts(labels),
        "confidence_mean": rounded(mean(confidences)) if confidences else 0.0,
    }


def model_metadata(
    *,
    text_col: str,
    label_col: str,
    id_col: str | None,
    classes: list[str],
    split: dict[str, Any],
) -> dict[str, Any]:
    return {
        "format_version": MODEL_FORMAT_VERSION,
        "model_type": "tfidf_logistic_regression",
        "vectorizer": "TfidfVectorizer",
        "classifier": "LogisticRegression",
        "text_col": text_col,
        "label_col": label_col,
        "id_col": id_col,
        "classes": classes,
        "trained_on": "csv_train_split",
        "split": split,
        "warning": CLASSIFIER_WARNING,
    }


def save_model(path: Path, *, model: Any, metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(
            {
                "format_version": MODEL_FORMAT_VERSION,
                "model": model,
                "metadata": metadata,
            },
            handle,
        )


def load_model(path: Path) -> tuple[Any, dict[str, Any]]:
    try:
        with path.open("rb") as handle:
            artifact = pickle.load(handle)
    except FileNotFoundError as exc:
        raise ClassifierError(f"missing classifier model: {path}") from exc
    if not isinstance(artifact, dict) or artifact.get("format_version") != MODEL_FORMAT_VERSION:
        raise ClassifierError(f"{path}: unsupported classifier model artifact")
    if "model" not in artifact or "metadata" not in artifact:
        raise ClassifierError(f"{path}: incomplete classifier model artifact")
    return artifact["model"], dict(artifact["metadata"])


def train_classifier(
    input_path: Path,
    *,
    text_col: str,
    label_col: str = "label",
    id_col: str | None = None,
    model_path: Path = DEFAULT_MODEL_PATH,
    output_path: Path | None = DEFAULT_TRAIN_REPORT_PATH,
    test_size: float = 0.25,
    random_state: int = 13,
) -> dict[str, Any]:
    sklearn = load_sklearn()
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        label_col=label_col,
        id_col=id_col,
    )
    samples = collect_labeled_samples(
        rows,
        text_col=text_col,
        label_col=label_col,
        id_col=id_col,
    )
    labels = [sample.label for sample in samples]
    split_info = validate_split(labels, test_size)
    indices = list(range(len(samples)))
    train_indices, dev_indices = sklearn["train_test_split"](
        indices,
        test_size=test_size,
        random_state=random_state,
        stratify=labels,
    )
    train_samples = [samples[index] for index in train_indices]
    dev_samples = [samples[index] for index in dev_indices]

    model = build_classifier(sklearn)
    model.fit(
        [sample.text for sample in train_samples],
        [sample.label for sample in train_samples],
    )
    classes = [str(label) for label in model.classes_]
    dev_texts = [sample.text for sample in dev_samples]
    dev_labels = [sample.label for sample in dev_samples]
    predictions = [str(value) for value in model.predict(dev_texts)]
    confidences = confidence_values(model, dev_texts)
    metrics = score_predictions(
        sklearn,
        labels=dev_labels,
        predictions=predictions,
        classes=classes,
        confidences=confidences,
    )
    split = {
        "random_state": random_state,
        "test_size": test_size,
        "stratified": True,
        "row_count": len(samples),
        "train_count": len(train_samples),
        "dev_count": len(dev_samples),
        "expected_train_count": split_info["train_count"],
        "expected_dev_count": split_info["dev_count"],
        "label_counts": split_info["label_counts"],
        "classes": classes,
    }
    metadata = model_metadata(
        text_col=text_col,
        label_col=label_col,
        id_col=id_col,
        classes=classes,
        split=split,
    )
    save_model(model_path, model=model, metadata=metadata)
    result = {
        "input": str(input_path),
        "model": str(model_path),
        "output": str(output_path) if output_path else None,
        "warning": CLASSIFIER_WARNING,
        "columns": {
            "text_col": text_col,
            "label_col": label_col,
            "id_col": id_col,
        },
        "model_info": metadata,
        "split": split,
        "metrics": metrics,
    }
    if output_path:
        write_json(output_path, result)
    return result


def evaluate_classifier(
    input_path: Path,
    *,
    model_path: Path = DEFAULT_MODEL_PATH,
    text_col: str,
    label_col: str = "label",
    id_col: str | None = None,
    output_path: Path | None = DEFAULT_EVALUATE_REPORT_PATH,
) -> dict[str, Any]:
    sklearn = load_sklearn()
    model, metadata = load_model(model_path)
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        label_col=label_col,
        id_col=id_col,
    )
    samples = collect_labeled_samples(
        rows,
        text_col=text_col,
        label_col=label_col,
        id_col=id_col,
    )
    texts = [sample.text for sample in samples]
    labels = [sample.label for sample in samples]
    classes = [str(label) for label in model.classes_]
    predictions = [str(value) for value in model.predict(texts)]
    confidences = confidence_values(model, texts)
    result = {
        "input": str(input_path),
        "model": str(model_path),
        "output": str(output_path) if output_path else None,
        "warning": CLASSIFIER_WARNING,
        "columns": {
            "text_col": text_col,
            "label_col": label_col,
            "id_col": id_col,
        },
        "model_info": metadata,
        "metrics": score_predictions(
            sklearn,
            labels=labels,
            predictions=predictions,
            classes=classes,
            confidences=confidences,
        ),
    }
    if output_path:
        write_json(output_path, result)
    return result


def output_fieldnames(
    fieldnames: list[str],
    *,
    prediction_col: str,
    confidence_col: str,
) -> list[str]:
    output = list(fieldnames)
    for column in (prediction_col, confidence_col):
        if column not in output:
            output.append(column)
    return output


def predict_classifier(
    input_path: Path,
    *,
    model_path: Path = DEFAULT_MODEL_PATH,
    text_col: str,
    id_col: str | None = None,
    label_col: str | None = "label",
    output_path: Path = DEFAULT_PREDICTION_PATH,
    prediction_col: str = "predicted_label",
    confidence_col: str = "predicted_confidence",
) -> dict[str, Any]:
    sklearn = load_sklearn()
    model, metadata = load_model(model_path)
    rows, fieldnames = read_csv(input_path)
    validate_columns(input_path, fieldnames, text_col=text_col, id_col=id_col)
    has_labels = label_col is not None and label_col in fieldnames
    if label_col and label_col not in fieldnames:
        label_col = None

    texts = [str(row.get(text_col, "") or "") for row in rows]
    predictions = [str(value) for value in model.predict(texts)]
    confidences = confidence_values(model, texts)
    output_rows: list[dict[str, Any]] = []
    for row, prediction, confidence in zip(rows, predictions, confidences):
        output_row = dict(row)
        output_row[prediction_col] = prediction
        output_row[confidence_col] = rounded(confidence)
        output_rows.append(output_row)
    write_csv(
        output_path,
        output_rows,
        output_fieldnames(
            fieldnames,
            prediction_col=prediction_col,
            confidence_col=confidence_col,
        ),
    )

    result: dict[str, Any] = {
        "input": str(input_path),
        "model": str(model_path),
        "output": str(output_path),
        "warning": CLASSIFIER_WARNING,
        "columns": {
            "text_col": text_col,
            "id_col": id_col,
            "label_col": label_col if has_labels else None,
            "prediction_col": prediction_col,
            "confidence_col": confidence_col,
        },
        "model_info": metadata,
        "row_count": len(rows),
        "prediction_counts": sorted_counts(predictions),
        "confidence_mean": rounded(mean(confidences)) if confidences else 0.0,
    }
    if has_labels and label_col:
        labels = [str(row.get(label_col, "") or "") for row in rows]
        classes = [str(label) for label in model.classes_]
        result["metrics"] = score_predictions(
            sklearn,
            labels=labels,
            predictions=predictions,
            classes=classes,
            confidences=confidences,
        )
    return result
