"""Lightweight source-vs-restatement deviation audit."""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ..io import CsvError, read_csv, sha256_file, write_csv
from ..results import StepResult

TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_/-]*(?:[-'][A-Za-z0-9_/-]+)*")
CONTEXT_TERMS = {
    "anti-semitism",
    "antisemitism",
    "genocide",
    "racism",
    "terrorism",
    "immigrant",
    "immigrants",
    "religion",
    "religious",
    "jewish",
    "muslim",
    "christian",
    "gay",
    "trans",
    "women",
    "disabled",
}
OFFENSIVE_ABSTRACTIONS = {
    "abuse",
    "attack",
    "attacks",
    "derogatory",
    "hate",
    "hateful",
    "hostile",
    "insult",
    "offensive",
    "profane",
    "slur",
    "threat",
}


def _terms(text: str) -> set[str]:
    lowered = text.lower()
    found = {term for term in CONTEXT_TERMS if term in lowered}
    found.update(
        match.group(0).lower()
        for match in TOKEN_PATTERN.finditer(text)
        if match.group(0).startswith("[TARGET_GROUP:")
    )
    return found


def _audit_row(
    source: str,
    restatement: str,
    *,
    row_id: str,
    label: str,
) -> dict[str, Any]:
    source_terms = _terms(source)
    restatement_terms = _terms(restatement)
    missing = sorted(source_terms - restatement_terms)
    similarity = SequenceMatcher(None, source, restatement).ratio()
    reasons: list[str] = []
    score = 0
    if missing:
        reasons.append("context_term_loss")
        score += 2 if label == "1" else 1
    if label == "1" and source_terms and not restatement_terms:
        reasons.append("target_cue_loss")
        score += 3
    if label == "1" and similarity < 0.25 and not any(
        term in restatement.lower() for term in OFFENSIVE_ABSTRACTIONS
    ):
        reasons.append("offensive_signal_loss")
        score += 2
    if not reasons and label == "1":
        reasons.append("no_heuristic_deviation")
    risk = (
        "high"
        if score >= 5
        else "medium"
        if score >= 3
        else "low"
        if score
        else "ok"
    )
    return {
        "ID": row_id,
        "hs": label,
        "deviation_risk": risk,
        "deviation_score": score,
        "deviation_reasons": "|".join(reasons),
        "source_context_terms": "|".join(sorted(source_terms)),
        "restatement_context_terms": "|".join(sorted(restatement_terms)),
        "missing_context_terms": "|".join(missing),
        "char_similarity": round(similarity, 4),
        "source_text": source,
        "restatement": restatement,
    }


def audit_restatements(
    source_csv: str | Path,
    restated_csv: str | Path,
    output_csv: str | Path,
    *,
    text_col: str = "text",
    id_col: str | None = None,
    label_col: str | None = "hs",
) -> StepResult:
    source_rows, source_fields = read_csv(source_csv)
    restated_rows, restated_fields = read_csv(restated_csv)
    if text_col not in source_fields or text_col not in restated_fields:
        raise CsvError(f"missing text column {text_col!r}")
    if len(source_rows) != len(restated_rows):
        raise CsvError("source and restated CSV row counts differ")
    audit_rows: list[dict[str, Any]] = []
    for index, (source, restated) in enumerate(
        zip(source_rows, restated_rows, strict=True),
        start=1,
    ):
        row_id = str(source.get(id_col or "", "") or index)
        label = str(
            source.get(label_col or "", "") or restated.get(label_col or "", "")
        )
        audit_rows.append(
            _audit_row(
                str(source.get(text_col, "") or ""),
                str(restated.get(text_col, "") or ""),
                row_id=row_id,
                label=label,
            )
        )
    fieldnames = [
        "ID",
        "hs",
        "deviation_risk",
        "deviation_score",
        "deviation_reasons",
        "source_context_terms",
        "restatement_context_terms",
        "missing_context_terms",
        "char_similarity",
        "source_text",
        "restatement",
    ]
    output_path = Path(output_csv)
    write_csv(output_path, audit_rows, fieldnames)
    risk_counts = Counter(str(row["deviation_risk"]) for row in audit_rows)
    return StepResult(
        name="deviation_audit",
        status="complete",
        path=output_path,
        metadata={
            "row_count": len(audit_rows),
            "risk_counts": dict(sorted(risk_counts.items())),
            "sha256": sha256_file(output_path),
        },
    )
