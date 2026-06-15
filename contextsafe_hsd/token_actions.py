"""Weakly supervised token-action tagger experiments."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from pathlib import Path
import pickle
import re
from statistics import mean
from typing import Any

from .csv_pipeline import read_csv, write_json
from .detectors import Span, detect_spans, target_group_spans
from .metrics import DIRECT_IDENTIFIER_TYPES, QUASI_IDENTIFIER_TYPES, UTILITY_CUES
from .row_ids import report_row_id
from .style import (
    ACTION_TERMS,
    HASHTAG_PATTERN,
    NEGATION_MODALITY_TERMS,
    REPEATED_LETTER_PATTERN,
    REPEATED_PUNCTUATION_PATTERN,
    STYLE_MARKER_PATTERN,
    SYMBOL_BURST_PATTERN,
)


INSTALL_HINT = (
    "Install optional token-action dependencies with: "
    "python -m pip install '.[token-actions]'"
)
TOKEN_ACTION_WARNING = (
    "This is a weakly supervised token-action experiment. Labels are generated "
    "from local detectors and cue protectors; they are not official PrivHSD "
    "privacy labels and should not replace deterministic anonymization unless "
    "reranking/evaluation proves a better privacy/HSD tradeoff."
)
MODEL_FORMAT_VERSION = 1
DEFAULT_MODEL_PATH = Path("data/outputs/privhsd_token_action_tagger.pkl")
DEFAULT_REPORT_PATH = Path("data/outputs/privhsd_token_action_tagger.train.json")

TOKEN_PATTERN = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
    r"@[A-Za-z0-9._-]+|#[A-Za-z][A-Za-z0-9_]*|"
    r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*|[!?.,]{2,}|[^\s]"
)

ACTION_KEEP = "KEEP"
ACTION_MASK = "MASK_IDENTIFIER"
ACTION_GENERALIZE = "GENERALIZE_CONTEXT"
ACTION_PROTECT_TARGET = "PROTECT_TARGET"
ACTION_PROTECT_HSD = "PROTECT_HSD"
ACTION_NORMALIZE = "NORMALIZE_STYLE"
ACTION_PRIORITY = {
    ACTION_KEEP: 0,
    ACTION_NORMALIZE: 1,
    ACTION_PROTECT_HSD: 2,
    ACTION_PROTECT_TARGET: 3,
    ACTION_GENERALIZE: 4,
    ACTION_MASK: 5,
}


class TokenActionError(ValueError):
    pass


@dataclass(frozen=True)
class TokenExample:
    row_index: int
    row_id: str
    token_index: int
    token: str
    start: int
    end: int
    action: str


def load_sklearn() -> dict[str, Any]:
    try:
        from sklearn.feature_extraction import DictVectorizer
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
            raise TokenActionError(INSTALL_HINT) from exc
        raise
    return {
        "DictVectorizer": DictVectorizer,
        "LogisticRegression": LogisticRegression,
        "Pipeline": Pipeline,
        "accuracy_score": accuracy_score,
        "confusion_matrix": confusion_matrix,
        "f1_score": f1_score,
        "precision_recall_fscore_support": precision_recall_fscore_support,
        "train_test_split": train_test_split,
    }


def rounded(value: float) -> float:
    return round(float(value), 4)


def sorted_counts(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def overlaps(start: int, end: int, span: Span) -> bool:
    return start < span.end and end > span.start


def phrase_spans(text: str, phrases: set[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for phrase in sorted(phrases, key=len, reverse=True):
        pattern = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])",
            re.I,
        )
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end()))
    return spans


def style_like(token: str) -> bool:
    return (
        bool(HASHTAG_PATTERN.fullmatch(token))
        or bool(STYLE_MARKER_PATTERN.fullmatch(token))
        or bool(REPEATED_LETTER_PATTERN.search(token))
        or bool(REPEATED_PUNCTUATION_PATTERN.fullmatch(token))
        or bool(SYMBOL_BURST_PATTERN.fullmatch(token))
    )


def strongest_action(actions: list[str]) -> str:
    if not actions:
        return ACTION_KEEP
    return max(actions, key=lambda action: ACTION_PRIORITY[action])


def token_action_for(
    token: str,
    *,
    start: int,
    end: int,
    identifier_spans: list[Span],
    target_spans: list[Span],
    hsd_spans: list[tuple[int, int]],
) -> str:
    actions: list[str] = []
    for span in identifier_spans:
        if not overlaps(start, end, span):
            continue
        if span.entity_type in DIRECT_IDENTIFIER_TYPES:
            actions.append(ACTION_MASK)
        elif span.entity_type in QUASI_IDENTIFIER_TYPES:
            actions.append(ACTION_GENERALIZE)
        else:
            actions.append(ACTION_MASK)
    if any(overlaps(start, end, span) for span in target_spans):
        actions.append(ACTION_PROTECT_TARGET)
    if any(start < hsd_end and end > hsd_start for hsd_start, hsd_end in hsd_spans):
        actions.append(ACTION_PROTECT_HSD)
    if style_like(token):
        actions.append(ACTION_NORMALIZE)
    return strongest_action(actions)


def weak_label_text(
    text: str,
    *,
    row_index: int = 1,
    row_id: str = "1",
) -> list[TokenExample]:
    identifier_spans = detect_spans(text, include_context=True, include_targets=False)
    target_spans = target_group_spans(text)
    hsd_phrases = {
        cue.lower() for cue in UTILITY_CUES
    } | {term.lower() for term in ACTION_TERMS | NEGATION_MODALITY_TERMS}
    hsd_spans = phrase_spans(text, hsd_phrases)
    examples: list[TokenExample] = []
    for token_index, match in enumerate(TOKEN_PATTERN.finditer(text), start=1):
        action = token_action_for(
            match.group(0),
            start=match.start(),
            end=match.end(),
            identifier_spans=identifier_spans,
            target_spans=target_spans,
            hsd_spans=hsd_spans,
        )
        examples.append(
            TokenExample(
                row_index=row_index,
                row_id=row_id,
                token_index=token_index,
                token=match.group(0),
                start=match.start(),
                end=match.end(),
                action=action,
            )
        )
    return examples


def validate_columns(
    input_path: Path,
    fieldnames: list[str],
    *,
    text_col: str,
    id_col: str | None,
) -> None:
    missing = [column for column in (text_col, id_col) if column]
    missing = [column for column in missing if column not in fieldnames]
    if missing:
        raise TokenActionError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )


def collect_examples(
    rows: list[dict[str, str]],
    *,
    text_col: str,
    id_col: str | None,
    sample_size: int,
) -> list[TokenExample]:
    limit = len(rows) if sample_size <= 0 else min(sample_size, len(rows))
    examples: list[TokenExample] = []
    for row_index, row in enumerate(rows[:limit], start=1):
        row_id = report_row_id(row, row_index=row_index, id_col=id_col)
        examples.extend(
            weak_label_text(
                str(row.get(text_col, "") or ""),
                row_index=row_index,
                row_id=row_id,
            )
        )
    return examples


def token_shape(token: str) -> str:
    shape = []
    for character in token:
        if character.isupper():
            shape.append("X")
        elif character.islower():
            shape.append("x")
        elif character.isdigit():
            shape.append("d")
        else:
            shape.append(character)
    collapsed = []
    for character in shape:
        if not collapsed or collapsed[-1] != character:
            collapsed.append(character)
    return "".join(collapsed)[:16]


def featurize(examples: list[TokenExample], index: int) -> dict[str, Any]:
    example = examples[index]
    token = example.token
    lowered = token.lower()
    previous_token = "<START>"
    next_token = "<END>"
    if index > 0 and examples[index - 1].row_index == example.row_index:
        previous_token = examples[index - 1].token.lower()
    if (
        index + 1 < len(examples)
        and examples[index + 1].row_index == example.row_index
    ):
        next_token = examples[index + 1].token.lower()
    return {
        "token.lower": lowered,
        "token.shape": token_shape(token),
        "token.prefix2": lowered[:2],
        "token.suffix2": lowered[-2:],
        "token.prefix3": lowered[:3],
        "token.suffix3": lowered[-3:],
        "token.length_bucket": min(len(token), 12),
        "token.is_upper": token.isupper(),
        "token.is_title": token.istitle(),
        "token.has_digit": any(character.isdigit() for character in token),
        "token.starts_at": token.startswith("@"),
        "token.starts_hash": token.startswith("#"),
        "token.has_repeat": bool(REPEATED_LETTER_PATTERN.search(token)),
        "token.is_punctuation": bool(re.fullmatch(r"\W+", token)),
        "prev.lower": previous_token,
        "next.lower": next_token,
    }


def feature_rows(examples: list[TokenExample]) -> list[dict[str, Any]]:
    return [featurize(examples, index) for index in range(len(examples))]


def validate_training(
    examples: list[TokenExample],
    *,
    test_size: float,
) -> dict[str, Any]:
    if not 0 < test_size < 1:
        raise TokenActionError("--test-size must be greater than 0 and less than 1")
    if not examples:
        raise TokenActionError("token-action training requires at least one token")
    label_counts = Counter(example.action for example in examples)
    if len(label_counts) < 2:
        raise TokenActionError("token-action training requires at least two actions")
    dev_count = math.ceil(len(examples) * test_size)
    train_count = len(examples) - dev_count
    if dev_count < 1 or train_count < 1:
        raise TokenActionError("--test-size creates an empty train or dev split")
    return {
        "token_count": len(examples),
        "label_counts": dict(sorted(label_counts.items())),
        "dev_count": dev_count,
        "train_count": train_count,
    }


def stratify_labels(labels: list[str], test_size: float) -> list[str] | None:
    counts = Counter(labels)
    dev_count = math.ceil(len(labels) * test_size)
    train_count = len(labels) - dev_count
    if min(counts.values()) < 2:
        return None
    if dev_count < len(counts) or train_count < len(counts):
        return None
    return labels


def build_tagger(sklearn: dict[str, Any]) -> Any:
    return sklearn["Pipeline"](
        [
            ("vectorizer", sklearn["DictVectorizer"]()),
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
        "token_count": len(labels),
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
        "per_action": {
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
    }


def save_model(path: Path, *, model: Any, metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(
            {
                "metadata": metadata,
                "model": model,
            },
            handle,
        )


def train_token_action_tagger(
    input_path: Path,
    *,
    text_col: str,
    id_col: str | None = None,
    model_path: Path | None = DEFAULT_MODEL_PATH,
    output_path: Path | None = DEFAULT_REPORT_PATH,
    sample_size: int = 5000,
    test_size: float = 0.25,
    random_state: int = 13,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    validate_columns(input_path, fieldnames, text_col=text_col, id_col=id_col)
    if sample_size < 0:
        raise TokenActionError("--sample-size must be non-negative")
    examples = collect_examples(
        rows,
        text_col=text_col,
        id_col=id_col,
        sample_size=sample_size,
    )
    split = validate_training(examples, test_size=test_size)
    sklearn = load_sklearn()
    features = feature_rows(examples)
    labels = [example.action for example in examples]
    stratify = stratify_labels(labels, test_size)
    train_features, dev_features, train_labels, dev_labels = sklearn[
        "train_test_split"
    ](
        features,
        labels,
        test_size=test_size,
        random_state=random_state,
        stratify=stratify,
    )
    model = build_tagger(sklearn)
    model.fit(train_features, train_labels)
    predictions = [str(label) for label in model.predict(dev_features)]
    classes = sorted(set(labels) | set(predictions))
    metrics = score_predictions(
        sklearn,
        labels=dev_labels,
        predictions=predictions,
        classes=classes,
    )
    metadata = {
        "format_version": MODEL_FORMAT_VERSION,
        "model_type": "dict_vectorizer_logistic_regression",
        "label_source": "weak_local_detectors_and_cue_protectors",
        "text_col": text_col,
        "id_col": id_col,
        "actions": sorted(set(labels)),
        "warning": TOKEN_ACTION_WARNING,
        "sample": {
            "requested_sample_size": sample_size,
            "row_count": len(rows) if sample_size <= 0 else min(sample_size, len(rows)),
            "source_row_count": len(rows),
            "strategy": "first_n_rows",
        },
        "split": split,
    }
    if model_path:
        save_model(model_path, model=model, metadata=metadata)
    result = {
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "model_path": str(model_path) if model_path else None,
        "training_type": "weak_token_action_tagger",
        "warning": TOKEN_ACTION_WARNING,
        "columns": {"text_col": text_col, "id_col": id_col},
        "sample": metadata["sample"],
        "split": split,
        "model": {
            "format_version": MODEL_FORMAT_VERSION,
            "model_type": metadata["model_type"],
            "saved": bool(model_path),
        },
        "metrics": metrics,
        "dev_action_counts": sorted_counts(dev_labels),
        "train_action_counts": sorted_counts(train_labels),
        "mean_token_length": rounded(mean(len(example.token) for example in examples)),
    }
    if output_path:
        write_json(output_path, result)
    return result
