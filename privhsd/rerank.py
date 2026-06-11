"""Row-local candidate generation and reranking."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
from statistics import mean
from typing import Any

from .author_risk import AuthorRiskError, build_author_classifier, load_sklearn
from .csv_pipeline import read_csv, write_csv, write_json
from .metrics import aggregate_metrics, row_metric
from .pipeline import PrivatizerConfig, privatize_text
from .style import (
    EMOJI_PATTERN,
    HASHTAG_PATTERN,
    REPEATED_LETTER_PATTERN,
    REPEATED_PUNCTUATION_PATTERN,
    SIGNATURE_PATTERNS,
    STYLE_MARKER_PATTERN,
    SYMBOL_BURST_PATTERN,
)


class RerankError(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    name: str
    text: str
    source: str


@dataclass
class AuthorScorer:
    model: Any
    classes: list[str]

    def true_author_confidence(self, text: str, author: str) -> float | None:
        if author not in self.classes:
            return None
        class_index = {label: index for index, label in enumerate(self.classes)}[author]
        probabilities = self.model.predict_proba([text])
        return float(probabilities[0][class_index])


STYLE_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("emoji", EMOJI_PATTERN),
    ("hashtag", HASHTAG_PATTERN),
    ("style_marker", STYLE_MARKER_PATTERN),
    ("symbol_burst", SYMBOL_BURST_PATTERN),
    ("repeated_punctuation", REPEATED_PUNCTUATION_PATTERN),
    ("repeated_letters", REPEATED_LETTER_PATTERN),
)


def rounded(value: float) -> float:
    return round(float(value), 4)


def validate_columns(
    input_path: Path,
    fieldnames: list[str],
    *,
    text_col: str,
    id_col: str | None,
    author_col: str | None,
    candidate_cols: list[str],
) -> None:
    missing = [column for column in (text_col, id_col, author_col) if column]
    missing.extend(candidate_cols)
    missing = [column for column in missing if column not in fieldnames]
    if missing:
        raise RerankError(
            f"{input_path}: missing required column(s): {', '.join(sorted(set(missing)))}"
        )


def style_risk_counts(text: str) -> dict[str, int]:
    counts = Counter(
        name
        for name, pattern in STYLE_RISK_PATTERNS
        for _match in pattern.finditer(text)
    )
    signature_count = 0
    for pattern in SIGNATURE_PATTERNS:
        signature_count += len(pattern.findall(text))
    if signature_count:
        counts["signature"] += signature_count
    return dict(sorted(counts.items()))


def style_risk_count(text: str) -> int:
    return sum(style_risk_counts(text).values())


def generate_candidates(
    text: str,
    *,
    rewrite_candidates: dict[str, str] | None = None,
) -> list[Candidate]:
    generated = [
        Candidate(
            name="balanced",
            text=privatize_text(text, PrivatizerConfig(mode="balanced")).text,
            source="deterministic",
        ),
        Candidate(
            name="style_scrubbed",
            text=privatize_text(
                text,
                PrivatizerConfig(mode="balanced", style_scrub=True),
            ).text,
            source="deterministic",
        ),
        Candidate(
            name="privacy",
            text=privatize_text(text, PrivatizerConfig(mode="privacy")).text,
            source="deterministic",
        ),
        Candidate(
            name="target_generalized",
            text=privatize_text(
                text,
                PrivatizerConfig(mode="balanced", generalize_targets=True),
            ).text,
            source="deterministic",
        ),
    ]
    seen = {(candidate.name, candidate.text) for candidate in generated}
    for column, value in (rewrite_candidates or {}).items():
        candidate = Candidate(
            name=f"rewrite:{column}",
            text=value,
            source="input_column",
        )
        if (candidate.name, candidate.text) not in seen:
            generated.append(candidate)
            seen.add((candidate.name, candidate.text))
    return generated


def length_drift(original: str, candidate: str) -> float:
    denominator = max(len(original), 1)
    return abs(len(candidate) - len(original)) / denominator


def score_candidate(
    original: str,
    candidate: Candidate,
    *,
    author: str | None = None,
    author_scorer: AuthorScorer | None = None,
) -> dict[str, Any]:
    metrics = row_metric(original, candidate.text)
    style_count = style_risk_count(candidate.text)
    author_confidence = None
    if author and author_scorer:
        author_confidence = author_scorer.true_author_confidence(candidate.text, author)

    privacy_penalty = (
        metrics["residual_direct_identifier_count"] * 3.0
        + metrics["residual_quasi_identifier_count"] * 1.5
        + style_count * 0.6
    )
    target_loss_penalty = (1.0 - metrics["target_cue_retention"]) * 4.0
    cue_loss_penalty = (1.0 - metrics["utility_cue_retention"]) * 4.0
    semantic_penalty = (1.0 - metrics["character_utility_retention"]) * 0.8
    drift_penalty = length_drift(original, candidate.text) * 0.5
    author_penalty = (author_confidence or 0.0) * 1.2
    utility_reward = (
        metrics["target_cue_retention"] * 2.0
        + metrics["utility_cue_retention"] * 2.0
        + metrics["character_utility_retention"] * 0.75
    )
    score = (
        utility_reward
        - privacy_penalty
        - target_loss_penalty
        - cue_loss_penalty
        - semantic_penalty
        - drift_penalty
        - author_penalty
    )
    return {
        "name": candidate.name,
        "source": candidate.source,
        "score": rounded(score),
        "metrics": {
            "residual_identifier_count": metrics["residual_identifier_count"],
            "residual_direct_identifier_count": metrics[
                "residual_direct_identifier_count"
            ],
            "residual_quasi_identifier_count": metrics[
                "residual_quasi_identifier_count"
            ],
            "target_cue_retention": metrics["target_cue_retention"],
            "utility_cue_retention": metrics["utility_cue_retention"],
            "character_utility_retention": metrics["character_utility_retention"],
            "length_drift": rounded(length_drift(original, candidate.text)),
            "style_risk_count": style_count,
            "style_risk_counts": style_risk_counts(candidate.text),
            "author_risk_confidence": (
                rounded(author_confidence) if author_confidence is not None else None
            ),
        },
    }


def choose_candidate(
    original: str,
    candidates: list[Candidate],
    *,
    author: str | None = None,
    author_scorer: AuthorScorer | None = None,
) -> tuple[Candidate, list[dict[str, Any]]]:
    scored = [
        score_candidate(
            original,
            candidate,
            author=author,
            author_scorer=author_scorer,
        )
        for candidate in candidates
    ]
    best_index = max(
        range(len(candidates)),
        key=lambda index: (
            scored[index]["score"],
            -scored[index]["metrics"]["residual_identifier_count"],
            scored[index]["metrics"]["target_cue_retention"],
            scored[index]["metrics"]["utility_cue_retention"],
            scored[index]["metrics"]["character_utility_retention"],
        ),
    )
    return candidates[best_index], scored


def build_author_scorer(
    rows: list[dict[str, str]],
    *,
    text_col: str,
    author_col: str | None,
) -> tuple[AuthorScorer | None, dict[str, Any]]:
    if not author_col:
        return None, {"status": "skipped", "skip_reason": "no_author_column_requested"}
    authors = [str(row.get(author_col, "") or "") for row in rows]
    counts = Counter(author for author in authors if author)
    if len(counts) < 2 or any(count < 2 for count in counts.values()):
        return None, {
            "status": "skipped",
            "skip_reason": "insufficient_author_rows",
            "author_counts": dict(sorted(counts.items())),
        }
    try:
        sklearn = load_sklearn()
    except AuthorRiskError as exc:
        return None, {
            "status": "skipped",
            "skip_reason": "missing_optional_dependency",
            "detail": str(exc),
        }

    samples = [
        (str(row.get(text_col, "") or ""), str(row.get(author_col, "") or ""))
        for row in rows
        if str(row.get(author_col, "") or "")
    ]
    model = build_author_classifier(sklearn)
    model.fit([text for text, _author in samples], [author for _text, author in samples])
    classes = [str(label) for label in model.classes_]
    return AuthorScorer(model=model, classes=classes), {
        "status": "ok",
        "model_type": "tfidf_logistic_regression",
        "trained_on": "all_original_rows_for_candidate_scoring",
        "author_counts": dict(sorted(counts.items())),
        "classes": classes,
    }


def run_candidate_reranking(
    input_path: Path,
    output_path: Path,
    *,
    text_col: str,
    id_col: str | None = None,
    output_col: str = "privatized_text",
    replace_text: bool = False,
    author_col: str | None = None,
    candidate_cols: list[str] | None = None,
    audit_path: Path | None = None,
) -> dict[str, Any]:
    candidate_cols = candidate_cols or []
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        author_col=author_col,
        candidate_cols=candidate_cols,
    )
    author_scorer, author_scorer_report = build_author_scorer(
        rows,
        text_col=text_col,
        author_col=author_col,
    )
    output_fieldnames = list(fieldnames)
    if not replace_text and output_col not in output_fieldnames:
        output_fieldnames.append(output_col)

    output_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    chosen_metrics: list[dict[str, Any]] = []
    chosen_counts: Counter[str] = Counter()
    for row_index, row in enumerate(rows, start=1):
        original = str(row.get(text_col, "") or "")
        rewrite_candidates = {
            column: str(row.get(column, "") or "")
            for column in candidate_cols
            if str(row.get(column, "") or "")
        }
        candidates = generate_candidates(
            original,
            rewrite_candidates=rewrite_candidates,
        )
        author = str(row.get(author_col, "") or "") if author_col else None
        chosen, scored = choose_candidate(
            original,
            candidates,
            author=author,
            author_scorer=author_scorer,
        )
        chosen_counts[chosen.name] += 1
        chosen_metrics.append(row_metric(original, chosen.text))
        output_row = dict(row)
        if replace_text:
            output_row[text_col] = chosen.text
        else:
            output_row[output_col] = chosen.text
        output_rows.append(output_row)
        row_id = row.get(id_col) if id_col else str(row_index)
        audit_rows.append(
            {
                "row_id": row_id,
                "row_index": row_index,
                "chosen": chosen.name,
                "candidate_count": len(candidates),
                "scores": scored,
            }
        )

    write_csv(output_path, output_rows, output_fieldnames)
    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "text_col": text_col,
        "id_col": id_col,
        "output_col": text_col if replace_text else output_col,
        "replace_text": replace_text,
        "candidate_cols": candidate_cols,
        "candidate_generation": [
            "balanced",
            "style_scrubbed",
            "privacy",
            "target_generalized",
            "rewrite:<candidate_col>",
        ],
        "author_scorer": author_scorer_report,
        "row_count": len(rows),
        "chosen_counts": dict(sorted(chosen_counts.items())),
        "metrics": aggregate_metrics(chosen_metrics),
    }
    if audit_path:
        write_json(
            audit_path,
            {
                "summary": summary,
                "rows": audit_rows,
            },
        )
    return summary
