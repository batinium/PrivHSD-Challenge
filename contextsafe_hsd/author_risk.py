"""Local authorship-risk evaluation for privatized text."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from pathlib import Path
from statistics import mean
from typing import Any

from .csv_pipeline import read_csv, write_json
from .metrics import aggregate_metrics, row_metric


INSTALL_HINT = (
    "Install optional author-risk dependencies with: "
    "python -m pip install '.[author-risk]'"
)
AUTHOR_RISK_WARNING = (
    "This is a lightweight local authorship adversary for development checks. "
    "It is not the official PrivHSD privacy evaluator and should be interpreted "
    "as a relative privacy-signal test."
)


class AuthorRiskError(ValueError):
    pass


@dataclass(frozen=True)
class AuthorRiskSample:
    row_index: int
    row_id: str
    original_text: str
    privatized_text: str
    author: str
    label: str | None = None


def load_sklearn() -> dict[str, Any]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, f1_score
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
    except ModuleNotFoundError as exc:
        if exc.name == "sklearn":
            raise AuthorRiskError(INSTALL_HINT) from exc
        raise
    return {
        "TfidfVectorizer": TfidfVectorizer,
        "LogisticRegression": LogisticRegression,
        "Pipeline": Pipeline,
        "accuracy_score": accuracy_score,
        "f1_score": f1_score,
        "train_test_split": train_test_split,
    }


def build_author_classifier(sklearn: dict[str, Any]) -> Any:
    return sklearn["Pipeline"](
        [
            (
                "tfidf",
                sklearn["TfidfVectorizer"](
                    lowercase=True,
                    analyzer="char_wb",
                    ngram_range=(3, 5),
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


def safe_ratio(numerator: float, denominator: float, *, default: float = 0.0) -> float:
    return numerator / denominator if denominator else default


def sorted_counts(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def skipped_result(
    input_path: Path,
    *,
    text_col: str,
    privatized_col: str,
    author_col: str,
    id_col: str | None,
    label_col: str | None,
    row_count: int,
    reason: str,
    detail: str,
    output_path: Path | None,
) -> dict[str, Any]:
    result = {
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "evaluator_type": "local_author_risk",
        "status": "skipped",
        "skip_reason": reason,
        "detail": detail,
        "warning": AUTHOR_RISK_WARNING,
        "columns": {
            "text_col": text_col,
            "privatized_col": privatized_col,
            "author_col": author_col,
            "id_col": id_col,
            "label_col": label_col,
        },
        "row_count": row_count,
    }
    if output_path:
        write_json(output_path, result)
    return result


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
        raise AuthorRiskError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )


def collect_samples(
    rows: list[dict[str, str]],
    *,
    text_col: str,
    privatized_col: str,
    author_col: str,
    id_col: str | None,
    label_col: str | None,
) -> list[AuthorRiskSample]:
    samples: list[AuthorRiskSample] = []
    for row_index, row in enumerate(rows, start=1):
        author = str(row.get(author_col, "") or "")
        if not author:
            continue
        row_id = str(row.get(id_col, "") or row_index) if id_col else str(row_index)
        samples.append(
            AuthorRiskSample(
                row_index=row_index,
                row_id=row_id,
                original_text=str(row.get(text_col, "") or ""),
                privatized_text=str(row.get(privatized_col, "") or ""),
                author=author,
                label=str(row.get(label_col, "") or "") if label_col else None,
            )
        )
    return samples


def split_skip_detail(authors: list[str], test_size: float) -> tuple[str, str] | None:
    if not 0 < test_size < 1:
        raise AuthorRiskError("--test-size must be greater than 0 and less than 1")
    counts = Counter(authors)
    if len(counts) < 2:
        return (
            "insufficient_author_labels",
            "author-risk evaluation requires at least two distinct authors",
        )
    rare = sorted(author for author, count in counts.items() if count < 2)
    if rare:
        return (
            "insufficient_author_rows",
            "stratified author-risk split requires at least two rows per author",
        )
    dev_count = math.ceil(len(authors) * test_size)
    train_count = len(authors) - dev_count
    if dev_count < len(counts):
        return (
            "insufficient_dev_rows",
            "--test-size creates fewer dev rows than authors",
        )
    if train_count < len(counts):
        return (
            "insufficient_train_rows",
            "--test-size leaves fewer training rows than authors",
        )
    return None


def true_author_confidences(
    probabilities: Any,
    *,
    classes: list[str],
    authors: list[str],
) -> list[float]:
    class_indexes = {label: index for index, label in enumerate(classes)}
    return [
        float(row_probs[class_indexes[author]])
        for row_probs, author in zip(probabilities, authors)
    ]


def score_author_predictions(
    sklearn: dict[str, Any],
    *,
    authors: list[str],
    classes: list[str],
    predictions: list[str],
    probabilities: Any,
) -> dict[str, Any]:
    true_confidences = true_author_confidences(
        probabilities,
        classes=classes,
        authors=authors,
    )
    max_confidences = [float(max(row_probs)) for row_probs in probabilities]
    return {
        "accuracy": rounded(sklearn["accuracy_score"](authors, predictions)),
        "macro_f1": rounded(
            sklearn["f1_score"](
                authors,
                predictions,
                labels=classes,
                average="macro",
                zero_division=0,
            )
        ),
        "prediction_counts": sorted_counts(predictions),
        "true_author_confidence_mean": rounded(mean(true_confidences)),
        "max_confidence_mean": rounded(mean(max_confidences)),
    }


def compare_author_scores(
    *,
    original: dict[str, Any],
    privatized: dict[str, Any],
    original_predictions: list[str],
    privatized_predictions: list[str],
    original_probabilities: Any,
    privatized_probabilities: Any,
    authors: list[str],
    classes: list[str],
    samples: list[AuthorRiskSample],
) -> dict[str, Any]:
    agreements = [
        left == right
        for left, right in zip(original_predictions, privatized_predictions)
    ]
    original_true_conf = true_author_confidences(
        original_probabilities,
        classes=classes,
        authors=authors,
    )
    privatized_true_conf = true_author_confidences(
        privatized_probabilities,
        classes=classes,
        authors=authors,
    )
    residual_rows = [
        {
            "row_index": sample.row_index,
            "row_id": sample.row_id,
            "privatized_author_confidence": rounded(privatized_confidence),
            "original_author_confidence": rounded(original_confidence),
            "confidence_delta": rounded(privatized_confidence - original_confidence),
        }
        for sample, prediction, original_confidence, privatized_confidence in zip(
            samples,
            privatized_predictions,
            original_true_conf,
            privatized_true_conf,
        )
        if prediction == sample.author
    ]
    residual_rows.sort(
        key=lambda item: (
            item["privatized_author_confidence"],
            item["original_author_confidence"],
        ),
        reverse=True,
    )
    macro_ratio = safe_ratio(privatized["macro_f1"], original["macro_f1"])
    accuracy_ratio = safe_ratio(privatized["accuracy"], original["accuracy"])
    confidence_ratio = safe_ratio(
        privatized["true_author_confidence_mean"],
        original["true_author_confidence_mean"],
    )
    return {
        "accuracy_delta": rounded(privatized["accuracy"] - original["accuracy"]),
        "macro_f1_delta": rounded(privatized["macro_f1"] - original["macro_f1"]),
        "true_author_confidence_delta": rounded(
            privatized["true_author_confidence_mean"]
            - original["true_author_confidence_mean"]
        ),
        "prediction_agreement": rounded(mean(agreements)) if agreements else 0.0,
        "privacy_ratio_accuracy": rounded(accuracy_ratio),
        "privacy_ratio_macro_f1": rounded(macro_ratio),
        "privacy_ratio_true_author_confidence": rounded(confidence_ratio),
        "privacy_gain_accuracy": rounded(1.0 - accuracy_ratio),
        "privacy_gain_macro_f1": rounded(1.0 - macro_ratio),
        "privacy_gain_true_author_confidence": rounded(1.0 - confidence_ratio),
        "residual_high_risk_rows": residual_rows[:20],
    }


def hsd_proxy_summary(samples: list[AuthorRiskSample]) -> dict[str, Any]:
    metrics = [
        row_metric(sample.original_text, sample.privatized_text)
        for sample in samples
    ]
    aggregate = aggregate_metrics(metrics)
    return {
        "row_count": len(samples),
        "metrics": aggregate,
    }


def run_author_risk_evaluation(
    input_path: Path,
    *,
    text_col: str,
    privatized_col: str = "privatized_text",
    author_col: str = "author",
    id_col: str | None = None,
    label_col: str | None = None,
    output_path: Path | None = None,
    test_size: float = 0.25,
    random_state: int = 13,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    if author_col not in fieldnames:
        return skipped_result(
            input_path,
            text_col=text_col,
            privatized_col=privatized_col,
            author_col=author_col,
            id_col=id_col,
            label_col=label_col,
            row_count=len(rows),
            reason="missing_author_column",
            detail=f"{input_path}: no author column {author_col!r}",
            output_path=output_path,
        )
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
        author_col=author_col,
        id_col=id_col,
        label_col=label_col,
    )
    authors = [sample.author for sample in samples]
    skip = split_skip_detail(authors, test_size)
    if skip:
        reason, detail = skip
        return skipped_result(
            input_path,
            text_col=text_col,
            privatized_col=privatized_col,
            author_col=author_col,
            id_col=id_col,
            label_col=label_col,
            row_count=len(rows),
            reason=reason,
            detail=detail,
            output_path=output_path,
        )

    sklearn = load_sklearn()
    indices = list(range(len(samples)))
    train_indices, dev_indices = sklearn["train_test_split"](
        indices,
        test_size=test_size,
        random_state=random_state,
        stratify=authors,
    )
    train_samples = [samples[index] for index in train_indices]
    dev_samples = [samples[index] for index in dev_indices]

    model = build_author_classifier(sklearn)
    model.fit(
        [sample.original_text for sample in train_samples],
        [sample.author for sample in train_samples],
    )
    classes = [str(label) for label in model.classes_]
    dev_authors = [sample.author for sample in dev_samples]
    original_texts = [sample.original_text for sample in dev_samples]
    privatized_texts = [sample.privatized_text for sample in dev_samples]
    original_predictions = [str(value) for value in model.predict(original_texts)]
    privatized_predictions = [str(value) for value in model.predict(privatized_texts)]
    original_probabilities = model.predict_proba(original_texts)
    privatized_probabilities = model.predict_proba(privatized_texts)

    original_scores = score_author_predictions(
        sklearn,
        authors=dev_authors,
        classes=classes,
        predictions=original_predictions,
        probabilities=original_probabilities,
    )
    privatized_scores = score_author_predictions(
        sklearn,
        authors=dev_authors,
        classes=classes,
        predictions=privatized_predictions,
        probabilities=privatized_probabilities,
    )
    result = {
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "evaluator_type": "local_author_risk",
        "status": "ok",
        "warning": AUTHOR_RISK_WARNING,
        "columns": {
            "text_col": text_col,
            "privatized_col": privatized_col,
            "author_col": author_col,
            "id_col": id_col,
            "label_col": label_col,
        },
        "model": {
            "vectorizer": "TfidfVectorizer",
            "analyzer": "char_wb",
            "ngram_range": [3, 5],
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
            "author_counts": dict(sorted(Counter(authors).items())),
            "classes": classes,
        },
        "original": original_scores,
        "privatized": privatized_scores,
        "comparison": compare_author_scores(
            original=original_scores,
            privatized=privatized_scores,
            original_predictions=original_predictions,
            privatized_predictions=privatized_predictions,
            original_probabilities=original_probabilities,
            privatized_probabilities=privatized_probabilities,
            authors=dev_authors,
            classes=classes,
            samples=dev_samples,
        ),
        "hsd_proxy": hsd_proxy_summary(dev_samples),
    }
    if output_path:
        write_json(output_path, result)
    return result
