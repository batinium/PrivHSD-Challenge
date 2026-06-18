"""Deterministic source-vs-restatement drift audit."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from typing import Any

from .context import OFFENSIVE_ONLY_TERMS
from .csv_pipeline import read_csv, write_csv, write_json
from .detectors import target_group_spans
from .metrics import row_metric_fast

try:
    from better_profanity import profanity
except Exception:  # pragma: no cover - optional in minimal installs.
    profanity = None


WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_/-]*(?:[-'][A-Za-z0-9_/-]+)*")
PHRASE_NORMALIZER = re.compile(r"[^a-z0-9]+")

CONTEXT_TERMS = {
    "anti-semitism",
    "antisemitism",
    "bigotry",
    "genocide",
    "globalist",
    "globalists",
    "leftist",
    "leftists",
    "liberal",
    "liberals",
    "right-wing",
    "rightwing",
    "conservative",
    "conservatives",
    "feminist",
    "feminists",
    "incel",
    "incels",
    "mra",
    "mras",
    "mtgow",
    "4chan",
    "t_d",
    "trump",
}

OFFENSIVE_ABSTRACTION_TERMS = {
    "abuse",
    "abusive",
    "attack",
    "attacks",
    "attacking",
    "derogatory",
    "hate",
    "hateful",
    "hostile",
    "insult",
    "insults",
    "insulting",
    "offensive",
    "profane",
    "profanity",
    "slur",
    "slurs",
    "threat",
    "threatening",
    "targets",
}

AUDIT_FIELDNAMES = [
    "ID",
    "hs",
    "deviation_risk",
    "deviation_score",
    "deviation_reasons",
    "target_category_retention",
    "target_cue_retention",
    "source_target_terms",
    "restatement_target_terms",
    "missing_target_terms",
    "source_offensive_terms",
    "restatement_offensive_terms",
    "missing_offensive_terms",
    "source_context_terms",
    "restatement_context_terms",
    "missing_context_terms",
    "source_text",
    "restatement",
]


class RestatementAuditError(ValueError):
    pass


def normalize_term(value: str) -> str:
    return PHRASE_NORMALIZER.sub(" ", value.lower()).strip()


def contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = f" {normalize_term(text)} "
    normalized_phrase = normalize_term(phrase)
    if not normalized_phrase:
        return False
    return f" {normalized_phrase} " in normalized_text


def target_terms(text: str) -> list[str]:
    terms = {
        normalize_term(span.text)
        for span in target_group_spans(text)
        if span.category != "slur_or_profanity"
    }
    return sorted(term for term in terms if term)


def offensive_terms(text: str) -> list[str]:
    terms = {
        normalize_term(term)
        for term in OFFENSIVE_ONLY_TERMS
        if contains_phrase(text, term)
    }
    if profanity is not None:
        for match in WORD_PATTERN.finditer(text):
            word = match.group(0)
            if profanity.contains_profanity(word):
                terms.add(normalize_term(word))
    return sorted(term for term in terms if term)


def context_terms(text: str) -> list[str]:
    return sorted(
        normalize_term(term) for term in CONTEXT_TERMS if contains_phrase(text, term)
    )


def missing_terms(source_terms: list[str], restatement: str) -> list[str]:
    return sorted(term for term in source_terms if not contains_phrase(restatement, term))


def offensive_abstracted(restatement: str) -> bool:
    return any(contains_phrase(restatement, term) for term in OFFENSIVE_ABSTRACTION_TERMS)


def audit_row(
    row: dict[str, str],
    *,
    text_col: str,
    restatement_col: str,
    id_col: str | None = None,
    label_col: str = "hs",
) -> dict[str, Any]:
    source = str(row.get(text_col, "") or "")
    restatement = str(row.get(restatement_col, "") or "")
    label = str(row.get(label_col, "")).strip()
    is_hate = label == "1"
    metrics = row_metric_fast(source, restatement)

    source_targets = target_terms(source)
    restatement_targets = target_terms(restatement)
    source_offensive = offensive_terms(source)
    restatement_offensive = offensive_terms(restatement)
    source_context = context_terms(source)
    restatement_context = context_terms(restatement)

    missing_targets = missing_terms(source_targets, restatement)
    missing_offensive = missing_terms(source_offensive, restatement)
    missing_context = missing_terms(source_context, restatement)

    reasons: list[str] = []
    score = 0
    target_category_retention = float(metrics.get("target_category_retention", 1.0))
    target_cue_retention = float(metrics.get("target_cue_retention", 1.0))

    if target_category_retention < 0.95:
        reasons.append("target_category_loss")
        score += 4 if is_hate else 2
    if target_cue_retention < 0.95:
        reasons.append("target_cue_loss")
        score += 3 if is_hate else 1
    if missing_targets:
        reasons.append("target_term_loss")
        score += 3 if is_hate else 1
    if missing_context:
        reasons.append("context_term_loss")
        score += 2 if is_hate else 1
    if source_offensive:
        offensive_retention = (
            len(source_offensive) - len(missing_offensive)
        ) / len(source_offensive)
        if offensive_retention < 0.75 and not offensive_abstracted(restatement):
            reasons.append("offensive_cue_loss")
            score += 3 if is_hate else 1
        elif offensive_retention < 0.75:
            reasons.append("offensive_cue_abstracted")
            score += 1 if is_hate else 0
    if is_hate and not reasons:
        reasons.append("no_heuristic_deviation")

    if score >= 5:
        risk = "high"
    elif score >= 3:
        risk = "medium"
    elif score >= 1:
        risk = "low"
    else:
        risk = "ok"

    return {
        "ID": row.get(id_col or "ID", ""),
        "hs": label,
        "deviation_risk": risk,
        "deviation_score": score,
        "deviation_reasons": "|".join(reasons),
        "target_category_retention": round(target_category_retention, 4),
        "target_cue_retention": round(target_cue_retention, 4),
        "source_target_terms": "|".join(source_targets),
        "restatement_target_terms": "|".join(restatement_targets),
        "missing_target_terms": "|".join(missing_targets),
        "source_offensive_terms": "|".join(source_offensive),
        "restatement_offensive_terms": "|".join(restatement_offensive),
        "missing_offensive_terms": "|".join(missing_offensive),
        "source_context_terms": "|".join(source_context),
        "restatement_context_terms": "|".join(restatement_context),
        "missing_context_terms": "|".join(missing_context),
        "source_text": source,
        "restatement": restatement,
    }


def summarize_audit(
    audit_rows: list[dict[str, Any]],
    *,
    input_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    risk_counts = Counter(str(row["deviation_risk"]) for row in audit_rows)
    reason_counts: Counter[str] = Counter()
    for row in audit_rows:
        for reason in str(row["deviation_reasons"]).split("|"):
            if reason and reason != "no_heuristic_deviation":
                reason_counts[reason] += 1
    return {
        "input": str(input_path),
        "output": str(output_path),
        "rows": len(audit_rows),
        "risk_counts": dict(sorted(risk_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "high_or_medium_ids": [
            str(row["ID"])
            for row in audit_rows
            if row["deviation_risk"] in {"high", "medium"}
        ],
    }


def run_restatement_deviation_audit(
    input_path: Path,
    output_path: Path,
    *,
    summary_path: Path | None = None,
    text_col: str = "text",
    restatement_col: str = "qwen35_descriptive_restatement",
    id_col: str | None = None,
    label_col: str = "hs",
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    for column in (text_col, restatement_col):
        if column not in fieldnames:
            raise RestatementAuditError(f"missing required column: {column}")
    if id_col and id_col not in fieldnames:
        raise RestatementAuditError(f"missing id column: {id_col}")
    if label_col not in fieldnames:
        raise RestatementAuditError(f"missing label column: {label_col}")

    audit_rows = [
        audit_row(
            row,
            text_col=text_col,
            restatement_col=restatement_col,
            id_col=id_col,
            label_col=label_col,
        )
        for row in rows
    ]
    write_csv(output_path, audit_rows, AUDIT_FIELDNAMES)
    summary = summarize_audit(
        audit_rows,
        input_path=input_path,
        output_path=output_path,
    )
    if summary_path:
        write_json(summary_path, summary)
    return summary
