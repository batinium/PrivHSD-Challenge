"""Local downstream-utility benchmark.

This module intentionally treats the classifier as a relative proxy. It asks how
much predictions change after privatization for one fixed local model; it does
not claim to be a production hate-speech detector.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from pathlib import Path
from statistics import mean
from typing import Any

from .csv_pipeline import read_csv, write_json


INSTALL_HINT = "Install optional benchmark dependencies with: python -m pip install '.[benchmark]'"


class BenchmarkError(ValueError):
    pass


@dataclass(frozen=True)
class BenchmarkSample:
    row_index: int
    row_id: str
    original_text: str
    privatized_text: str
    label: str


def load_sklearn() -> dict[str, Any]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, f1_score, recall_score
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
    except ModuleNotFoundError as exc:
        if exc.name == "sklearn":
            raise BenchmarkError(INSTALL_HINT) from exc
        raise
    return {
        "TfidfVectorizer": TfidfVectorizer,
        "LogisticRegression": LogisticRegression,
        "Pipeline": Pipeline,
        "accuracy_score": accuracy_score,
        "f1_score": f1_score,
        "recall_score": recall_score,
        "train_test_split": train_test_split,
    }


def collect_samples(
    rows: list[dict[str, str]],
    *,
    text_col: str,
    privatized_col: str,
    label_col: str,
    id_col: str | None,
) -> list[BenchmarkSample]:
    samples: list[BenchmarkSample] = []
    for row_index, row in enumerate(rows, start=1):
        label = str(row.get(label_col, "") or "")
        if not label:
            raise BenchmarkError(
                f"row {row_index}: missing label in column {label_col!r}"
            )
        row_id = str(row.get(id_col, "") or row_index) if id_col else str(row_index)
        samples.append(
            BenchmarkSample(
                row_index=row_index,
                row_id=row_id,
                original_text=str(row.get(text_col, "") or ""),
                privatized_text=str(row.get(privatized_col, "") or ""),
                label=label,
            )
        )
    return samples


def validate_split(labels: list[str], test_size: float) -> dict[str, Any]:
    if not 0 < test_size < 1:
        raise BenchmarkError("--test-size must be greater than 0 and less than 1")
    counts = Counter(labels)
    if len(counts) < 2:
        raise BenchmarkError("utility benchmark requires at least two labels")
    rare = sorted(label for label, count in counts.items() if count < 2)
    if rare:
        raise BenchmarkError(
            "stratified benchmark requires at least two rows per label; "
            f"too few rows for: {', '.join(rare)}"
        )
    dev_count = math.ceil(len(labels) * test_size)
    train_count = len(labels) - dev_count
    if dev_count < len(counts):
        raise BenchmarkError(
            "--test-size creates fewer dev rows than labels; increase --test-size"
        )
    if train_count < len(counts):
        raise BenchmarkError(
            "--test-size leaves fewer training rows than labels; decrease --test-size"
        )
    return {
        "label_counts": dict(sorted(counts.items())),
        "dev_count": dev_count,
        "train_count": train_count,
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


def prediction_counts(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def true_label_probabilities(
    probabilities: Any,
    *,
    classes: list[str],
    labels: list[str],
) -> list[float]:
    class_indexes = {label: index for index, label in enumerate(classes)}
    values: list[float] = []
    for row_probs, label in zip(probabilities, labels):
        values.append(float(row_probs[class_indexes[label]]))
    return values


def score_predictions(
    sklearn: dict[str, Any],
    *,
    labels: list[str],
    classes: list[str],
    predictions: list[str],
    probabilities: Any,
) -> dict[str, Any]:
    recalls = sklearn["recall_score"](
        labels,
        predictions,
        labels=classes,
        average=None,
        zero_division=0,
    )
    true_confidences = true_label_probabilities(
        probabilities,
        classes=classes,
        labels=labels,
    )
    max_confidences = [float(max(row_probs)) for row_probs in probabilities]
    return {
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
        "recall_by_label": {
            label: rounded(value) for label, value in zip(classes, recalls)
        },
        "prediction_counts": prediction_counts(predictions),
        "true_label_confidence_mean": rounded(mean(true_confidences)),
        "max_confidence_mean": rounded(mean(max_confidences)),
    }


def compare_scores(
    *,
    original: dict[str, Any],
    privatized: dict[str, Any],
    classes: list[str],
    original_predictions: list[str],
    privatized_predictions: list[str],
    original_probabilities: Any,
    privatized_probabilities: Any,
    labels: list[str],
    samples: list[BenchmarkSample],
) -> dict[str, Any]:
    agreement_values = [
        left == right
        for left, right in zip(original_predictions, privatized_predictions)
    ]
    changed_rows = [
        {
            "row_index": sample.row_index,
            "row_id": sample.row_id,
            "label": sample.label,
            "original_prediction": original_prediction,
            "privatized_prediction": privatized_prediction,
        }
        for sample, original_prediction, privatized_prediction in zip(
            samples,
            original_predictions,
            privatized_predictions,
        )
        if original_prediction != privatized_prediction
    ]
    original_true_conf = true_label_probabilities(
        original_probabilities,
        classes=classes,
        labels=labels,
    )
    privatized_true_conf = true_label_probabilities(
        privatized_probabilities,
        classes=classes,
        labels=labels,
    )
    confidence_drifts = [
        abs(after - before)
        for before, after in zip(original_true_conf, privatized_true_conf)
    ]
    return {
        "accuracy_delta": rounded(privatized["accuracy"] - original["accuracy"]),
        "macro_f1_delta": rounded(privatized["macro_f1"] - original["macro_f1"]),
        "prediction_agreement": rounded(mean(agreement_values)),
        "changed_prediction_count": len(changed_rows),
        "label_recall_delta": {
            label: rounded(
                privatized["recall_by_label"][label]
                - original["recall_by_label"][label]
            )
            for label in classes
        },
        "true_label_confidence_delta": rounded(
            privatized["true_label_confidence_mean"]
            - original["true_label_confidence_mean"]
        ),
        "true_label_confidence_abs_drift_mean": rounded(mean(confidence_drifts)),
        "changed_prediction_examples": changed_rows[:20],
    }


def run_utility_benchmark(
    input_path: Path,
    *,
    text_col: str,
    privatized_col: str,
    label_col: str,
    id_col: str | None = None,
    output_path: Path | None = None,
    test_size: float = 0.25,
    random_state: int = 13,
) -> dict[str, Any]:
    sklearn = load_sklearn()
    rows, fieldnames = read_csv(input_path)
    missing = [
        column
        for column in (text_col, privatized_col, label_col)
        if column not in fieldnames
    ]
    if missing:
        raise BenchmarkError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )
    if id_col and id_col not in fieldnames:
        raise BenchmarkError(f"{input_path}: missing id column {id_col!r}")

    samples = collect_samples(
        rows,
        text_col=text_col,
        privatized_col=privatized_col,
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
        [sample.original_text for sample in train_samples],
        [sample.label for sample in train_samples],
    )

    classes = [str(label) for label in model.classes_]
    dev_labels = [sample.label for sample in dev_samples]
    original_predictions = [
        str(value) for value in model.predict([sample.original_text for sample in dev_samples])
    ]
    privatized_predictions = [
        str(value)
        for value in model.predict([sample.privatized_text for sample in dev_samples])
    ]
    original_probabilities = model.predict_proba(
        [sample.original_text for sample in dev_samples]
    )
    privatized_probabilities = model.predict_proba(
        [sample.privatized_text for sample in dev_samples]
    )

    original_scores = score_predictions(
        sklearn,
        labels=dev_labels,
        classes=classes,
        predictions=original_predictions,
        probabilities=original_probabilities,
    )
    privatized_scores = score_predictions(
        sklearn,
        labels=dev_labels,
        classes=classes,
        predictions=privatized_predictions,
        probabilities=privatized_probabilities,
    )
    comparison = compare_scores(
        original=original_scores,
        privatized=privatized_scores,
        classes=classes,
        original_predictions=original_predictions,
        privatized_predictions=privatized_predictions,
        original_probabilities=original_probabilities,
        privatized_probabilities=privatized_probabilities,
        labels=dev_labels,
        samples=dev_samples,
    )
    result = {
        "input": str(input_path),
        "benchmark_type": "local_relative_utility_proxy",
        "warning": (
            "This benchmark measures utility deltas for one local classifier. "
            "It is not a production hate-speech detector and does not replace "
            "the official PrivHSD evaluator."
        ),
        "columns": {
            "text_col": text_col,
            "privatized_col": privatized_col,
            "label_col": label_col,
            "id_col": id_col,
        },
        "model": {
            "vectorizer": "TfidfVectorizer",
            "classifier": "LogisticRegression",
            "trained_on": "original_text_train_split",
        },
        "split": {
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
        },
        "original": original_scores,
        "privatized": privatized_scores,
        "comparison": comparison,
    }
    if output_path:
        write_json(output_path, result)
    return result
