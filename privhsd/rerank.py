"""Row-local candidate generation and reranking."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from .author_risk import AuthorRiskError, build_author_classifier, load_sklearn
from .csv_pipeline import read_csv, write_csv, write_json
from .metrics import aggregate_metrics, row_metric
from .pipeline import PrivatizerConfig, privatize_text
from .presidio_augment import load_presidio_analyzer
from .span_providers.base import SpanProvider, SpanProviderOutput
from .span_providers.presidio import PresidioSpanProvider
from .span_providers.registry import load_span_providers
from .style import (
    ACTION_TERMS,
    EMOJI_PATTERN,
    HASHTAG_PATTERN,
    NEGATION_MODALITY_TERMS,
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
    metadata: dict[str, Any] = field(default_factory=dict)


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

DEFAULT_MIN_REWRITE_TARGET_RETENTION = 1.0
DEFAULT_MIN_REWRITE_UTILITY_RETENTION = 1.0
DEFAULT_MIN_REWRITE_CHARACTER_RETENTION = 0.35
DEFAULT_MAX_REWRITE_LENGTH_DRIFT = 0.65


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


def length_drift(original: str, candidate: str) -> float:
    denominator = max(len(original), 1)
    return abs(len(candidate) - len(original)) / denominator


def cue_term_count(text: str, terms: set[str]) -> int:
    lowered = text.lower()
    count = 0
    for term in terms:
        pattern = r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])"
        count += len(re.findall(pattern, lowered))
    return count


def cue_retention(original: str, candidate: str, terms: set[str]) -> float:
    before = cue_term_count(original, terms)
    if before == 0:
        return 1.0
    return cue_term_count(candidate, terms) / before


def validate_rewrite_candidate(
    original: str,
    candidate: str,
    *,
    min_target_retention: float = DEFAULT_MIN_REWRITE_TARGET_RETENTION,
    min_utility_retention: float = DEFAULT_MIN_REWRITE_UTILITY_RETENTION,
    min_character_retention: float = DEFAULT_MIN_REWRITE_CHARACTER_RETENTION,
    max_length_drift: float = DEFAULT_MAX_REWRITE_LENGTH_DRIFT,
    reject_unchanged: bool = False,
) -> tuple[bool, dict[str, Any]]:
    candidate = candidate.strip()
    reasons: list[str] = []
    if not candidate:
        reasons.append("empty_candidate")

    metrics = row_metric(original, candidate)
    drift = length_drift(original, candidate)
    original_style_risk = style_risk_count(original)
    candidate_style_risk = style_risk_count(candidate)
    action_retention = cue_retention(original, candidate, ACTION_TERMS)
    negation_modality_retention = cue_retention(
        original,
        candidate,
        NEGATION_MODALITY_TERMS,
    )

    if reject_unchanged and original == candidate:
        reasons.append("unchanged")
    if metrics["target_cue_retention"] < min_target_retention:
        reasons.append("target_cue_loss")
    if metrics["utility_cue_retention"] < min_utility_retention:
        reasons.append("utility_cue_loss")
    if action_retention < 1.0:
        reasons.append("action_cue_loss")
    if negation_modality_retention < 1.0:
        reasons.append("negation_modality_loss")
    if metrics["character_utility_retention"] < min_character_retention:
        reasons.append("low_character_retention")
    if drift > max_length_drift:
        reasons.append("length_drift")
    if metrics["residual_direct_identifier_count"]:
        reasons.append("residual_direct_identifier")
    if metrics["residual_quasi_identifier_count"]:
        reasons.append("residual_quasi_identifier")
    if (
        metrics["privacy_identifier_count_after"]
        > metrics["privacy_identifier_count_before"]
    ):
        reasons.append("new_identifier_signal")
    if candidate_style_risk > original_style_risk:
        reasons.append("style_risk_increase")

    checks = {
        "accepted": not reasons,
        "reasons": reasons,
        "target_cue_retention": metrics["target_cue_retention"],
        "utility_cue_retention": metrics["utility_cue_retention"],
        "action_cue_retention": rounded(action_retention),
        "negation_modality_retention": rounded(negation_modality_retention),
        "character_utility_retention": metrics["character_utility_retention"],
        "length_drift": rounded(drift),
        "privacy_identifier_count_before": metrics["privacy_identifier_count_before"],
        "privacy_identifier_count_after": metrics["privacy_identifier_count_after"],
        "residual_direct_identifier_count": metrics["residual_direct_identifier_count"],
        "residual_quasi_identifier_count": metrics["residual_quasi_identifier_count"],
        "style_risk_count_before": original_style_risk,
        "style_risk_count_after": candidate_style_risk,
        "min_target_retention": min_target_retention,
        "min_utility_retention": min_utility_retention,
        "min_character_retention": min_character_retention,
        "max_length_drift": max_length_drift,
    }
    return not reasons, checks


def generate_candidates(
    text: str,
    *,
    rewrite_candidates: dict[str, str] | None = None,
    presidio_analyzer: Any | None = None,
    presidio_language: str = "en",
    span_providers: list[SpanProvider] | None = None,
) -> list[Candidate]:
    candidates, _rejected_candidates = generate_candidates_with_rejections(
        text,
        rewrite_candidates=rewrite_candidates,
        presidio_analyzer=presidio_analyzer,
        presidio_language=presidio_language,
        span_providers=span_providers,
    )
    return candidates


def provider_candidate_name(provider_name: str) -> str:
    if provider_name == "scrubadub":
        return "scrubadub_augmented"
    return f"{provider_name}_augmented"


def provider_metadata(output: SpanProviderOutput, result_metadata: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(output.audit)
    metadata["provider_fusion"] = result_metadata
    fusion_report = result_metadata.get("fusion", {})
    metadata["fusion_accepted_span_count"] = fusion_report.get("accepted_span_count", 0)
    metadata["provider_accepted_span_count"] = output.audit.get(
        "accepted_span_count",
        len(output.spans),
    )
    metadata.setdefault("accepted_span_count", output.audit.get("accepted_span_count", 0))
    return metadata


def generate_candidates_with_rejections(
    text: str,
    *,
    rewrite_candidates: dict[str, str] | None = None,
    presidio_analyzer: Any | None = None,
    presidio_language: str = "en",
    span_providers: list[SpanProvider] | None = None,
) -> tuple[list[Candidate], list[dict[str, Any]]]:
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
    providers = list(span_providers or [])
    if presidio_analyzer:
        providers.append(
            PresidioSpanProvider(analyzer=presidio_analyzer, language=presidio_language)
        )
    provider_outputs: list[SpanProviderOutput] = []
    for provider in providers:
        output = provider.propose(text)
        provider_outputs.append(output)
        if not output.spans:
            continue
        result = privatize_text(
            text,
            PrivatizerConfig(mode="balanced"),
            provider_candidates=output.spans,
        )
        generated.append(
            Candidate(
                name=provider_candidate_name(output.provider),
                text=result.text,
                source=output.provider,
                metadata=provider_metadata(output, result.provider_audit),
            )
        )
    if len(provider_outputs) > 1:
        fused_spans = [
            span
            for output in provider_outputs
            for span in output.spans
        ]
        if fused_spans:
            result = privatize_text(
                text,
                PrivatizerConfig(mode="balanced"),
                provider_candidates=fused_spans,
            )
            generated.append(
                Candidate(
                    name="provider_fusion_augmented",
                    text=result.text,
                    source="provider_fusion",
                    metadata={
                        "providers": [output.provider for output in provider_outputs],
                        "provider_reports": {
                            output.provider: output.audit for output in provider_outputs
                        },
                        "provider_fusion": result.provider_audit,
                        "accepted_span_count": result.provider_audit.get(
                            "fusion",
                            {},
                        ).get("accepted_span_count", 0),
                    },
                )
            )
    seen = {(candidate.name, candidate.text) for candidate in generated}
    rejected: list[dict[str, Any]] = []
    for column, value in (rewrite_candidates or {}).items():
        candidate_text = value.strip()
        accepted, validation = validate_rewrite_candidate(text, candidate_text)
        if not accepted:
            rejected.append(
                {
                    "column": column,
                    "name": f"rewrite:{column}",
                    "source": "input_column",
                    "validation": validation,
                }
            )
            continue
        candidate = Candidate(
            name=f"rewrite:{column}",
            text=candidate_text,
            source="input_column",
            metadata={"validation": validation},
        )
        if (candidate.name, candidate.text) not in seen:
            generated.append(candidate)
            seen.add((candidate.name, candidate.text))
    return generated, rejected


def score_candidate(
    original: str,
    candidate: Candidate,
    *,
    author: str | None = None,
    author_scorer: AuthorScorer | None = None,
) -> dict[str, Any]:
    metrics = row_metric(original, candidate.text)
    style_count = style_risk_count(candidate.text)
    provider_accepted_count = int(
        candidate.metadata.get(
            "provider_accepted_span_count",
            candidate.metadata.get("accepted_span_count", 0),
        )
    )
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
    privacy_bonus = min(provider_accepted_count, 4) * 0.55
    score = (
        utility_reward
        + privacy_bonus
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
            "provider_accepted_span_count": provider_accepted_count,
            "presidio_accepted_span_count": int(
                candidate.metadata.get("accepted_span_count", 0)
                if candidate.source == "presidio"
                else 0
            ),
            "provider_disagreement_count": candidate.metadata.get(
                "provider_fusion",
                {},
            ).get("fusion", {}).get("provider_disagreement_count", 0),
            "presidio_rejected_counts_by_reason": candidate.metadata.get(
                "rejected_counts_by_reason",
                {},
            ),
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
    presidio_augment: bool = False,
    presidio_language: str = "en",
    providers: list[str] | None = None,
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
    provider_names = list(providers or [])
    span_providers = load_span_providers(
        provider_names,
        presidio_language=presidio_language,
    )
    if presidio_augment and "presidio" not in provider_names:
        provider_names.append("presidio")
        span_providers.append(
            PresidioSpanProvider(
                analyzer=load_presidio_analyzer(),
                language=presidio_language,
            )
        )
    output_fieldnames = list(fieldnames)
    if not replace_text and output_col not in output_fieldnames:
        output_fieldnames.append(output_col)

    output_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    chosen_metrics: list[dict[str, Any]] = []
    chosen_counts: Counter[str] = Counter()
    rejected_rewrite_candidate_counts: Counter[str] = Counter()
    rejected_rewrite_candidate_reason_counts: Counter[str] = Counter()
    for row_index, row in enumerate(rows, start=1):
        original = str(row.get(text_col, "") or "")
        rewrite_candidates = {
            column: str(row.get(column, "") or "")
            for column in candidate_cols
            if str(row.get(column, "") or "")
        }
        candidates, rejected_rewrite_candidates = generate_candidates_with_rejections(
            original,
            rewrite_candidates=rewrite_candidates,
            span_providers=span_providers,
        )
        for rejected in rejected_rewrite_candidates:
            rejected_rewrite_candidate_counts[str(rejected["column"])] += 1
            for reason in rejected["validation"]["reasons"]:
                rejected_rewrite_candidate_reason_counts[str(reason)] += 1
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
                "rejected_rewrite_candidates": rejected_rewrite_candidates,
                "candidate_metadata": {
                    candidate.name: candidate.metadata
                    for candidate in candidates
                    if candidate.metadata
                },
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
            name
            for name in [
                "balanced",
                "style_scrubbed",
                "privacy",
                "target_generalized",
                *[
                    provider_candidate_name(provider_name)
                    for provider_name in provider_names
                ],
                "provider_fusion_augmented" if len(provider_names) > 1 else None,
                "rewrite:<candidate_col>",
            ]
            if name
        ],
        "providers": {
            "enabled": bool(provider_names),
            "names": provider_names,
            "language": presidio_language if "presidio" in provider_names else None,
        },
        "presidio_augment": {
            "enabled": "presidio" in provider_names,
            "language": presidio_language if "presidio" in provider_names else None,
        },
        "author_scorer": author_scorer_report,
        "rewrite_candidate_validation": {
            "rejected_count": sum(rejected_rewrite_candidate_counts.values()),
            "rejected_counts_by_column": dict(
                sorted(rejected_rewrite_candidate_counts.items())
            ),
            "rejected_counts_by_reason": dict(
                sorted(rejected_rewrite_candidate_reason_counts.items())
            ),
            "min_target_retention": DEFAULT_MIN_REWRITE_TARGET_RETENTION,
            "min_utility_retention": DEFAULT_MIN_REWRITE_UTILITY_RETENTION,
            "min_character_retention": DEFAULT_MIN_REWRITE_CHARACTER_RETENTION,
            "max_length_drift": DEFAULT_MAX_REWRITE_LENGTH_DRIFT,
        },
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
