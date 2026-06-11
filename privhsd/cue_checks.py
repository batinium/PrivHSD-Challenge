"""Conservative HSD cue retention checks."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from statistics import mean
from typing import Any

from .csv_pipeline import read_csv, write_json
from .detectors import TARGET_GROUP_TERMS
from .metrics import UTILITY_CUES
from .style import ACTION_TERMS, NEGATION_MODALITY_TERMS


DEFAULT_RETENTION_THRESHOLD = 1.0


class CueCheckError(ValueError):
    pass


def rounded(value: float) -> float:
    return round(float(value), 4)


def phrase_count(text: str, phrase: str) -> int:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"
    return len(re.findall(pattern, text.lower()))


def counts_for_terms(text: str, terms: list[str]) -> Counter[str]:
    return Counter(
        term
        for term in terms
        for _match in range(phrase_count(text, term))
    )


def retention(after_count: int, before_count: int) -> float:
    if before_count == 0:
        return 1.0
    return after_count / before_count


def sorted_terms(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def cue_terms() -> dict[str, list[str]]:
    target_terms = sorted(
        {
            term.lower()
            for terms in TARGET_GROUP_TERMS.values()
            for term in terms
        }
    )
    return {
        "target_terms": target_terms,
        "utility_cues": sorted({cue.lower() for cue in UTILITY_CUES}),
        "action_terms": sorted(ACTION_TERMS),
        "negation_modality_terms": sorted(NEGATION_MODALITY_TERMS),
    }


def row_cue_report(
    *,
    row_index: int,
    row_id: str,
    original: str,
    privatized: str,
    threshold: float,
) -> dict[str, Any]:
    groups = cue_terms()
    group_reports: dict[str, Any] = {}
    losses: list[str] = []
    for group_name, terms in groups.items():
        before = counts_for_terms(original, terms)
        after = counts_for_terms(privatized, terms)
        before_total = sum(before.values())
        after_total = sum(after.values())
        group_retention = rounded(retention(after_total, before_total))
        lost_terms = sorted(
            term
            for term, count in before.items()
            if after.get(term, 0) < count
        )
        if before_total and group_retention < threshold:
            losses.append(group_name)
        group_reports[group_name] = {
            "before": before_total,
            "after": after_total,
            "retention": group_retention,
            "lost_terms": lost_terms,
            "counts_before": sorted_terms(before),
            "counts_after": sorted_terms(after),
        }
    return {
        "row_index": row_index,
        "row_id": row_id,
        "loss_groups": losses,
        "groups": group_reports,
    }


def aggregate_reports(row_reports: list[dict[str, Any]]) -> dict[str, Any]:
    group_names = list(cue_terms())
    aggregate: dict[str, Any] = {
        "row_count": len(row_reports),
        "rows_with_loss": sum(1 for row in row_reports if row["loss_groups"]),
        "loss_group_counts": dict(
            sorted(
                Counter(
                    group
                    for row in row_reports
                    for group in row["loss_groups"]
                ).items()
            )
        ),
    }
    for group_name in group_names:
        retentions = [
            row["groups"][group_name]["retention"]
            for row in row_reports
            if row["groups"][group_name]["before"] > 0
        ]
        aggregate[f"{group_name}_retention_mean"] = (
            rounded(mean(retentions)) if retentions else 1.0
        )
        aggregate[f"{group_name}_before_total"] = sum(
            row["groups"][group_name]["before"] for row in row_reports
        )
        aggregate[f"{group_name}_after_total"] = sum(
            row["groups"][group_name]["after"] for row in row_reports
        )
    return aggregate


def run_cue_checks(
    input_path: Path,
    *,
    text_col: str,
    privatized_col: str,
    id_col: str | None = None,
    output_path: Path | None = None,
    retention_threshold: float = DEFAULT_RETENTION_THRESHOLD,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    missing = [
        column
        for column in (text_col, privatized_col, id_col)
        if column and column not in fieldnames
    ]
    if missing:
        raise CueCheckError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )
    if not 0 <= retention_threshold <= 1:
        raise CueCheckError("--retention-threshold must be between 0 and 1")
    row_reports = [
        row_cue_report(
            row_index=index,
            row_id=str(row.get(id_col, "") or index) if id_col else str(index),
            original=str(row.get(text_col, "") or ""),
            privatized=str(row.get(privatized_col, "") or ""),
            threshold=retention_threshold,
        )
        for index, row in enumerate(rows, start=1)
    ]
    result = {
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "check_type": "conservative_hsd_cue_retention",
        "columns": {
            "text_col": text_col,
            "privatized_col": privatized_col,
            "id_col": id_col,
        },
        "retention_threshold": retention_threshold,
        "cue_manifest": cue_terms(),
        "aggregate": aggregate_reports(row_reports),
        "rows_with_loss": [
            {
                "row_index": row["row_index"],
                "row_id": row["row_id"],
                "loss_groups": row["loss_groups"],
            }
            for row in row_reports
            if row["loss_groups"]
        ][:100],
        "rows": row_reports,
    }
    if output_path:
        write_json(output_path, result)
    return result
