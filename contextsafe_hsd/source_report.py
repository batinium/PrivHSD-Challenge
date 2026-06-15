"""Source-aware original/protected regression reports."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .context import analyze_context
from .csv_pipeline import read_csv, write_json
from .cue_checks import counts_for_terms
from .metrics import row_metric
from .rationale_checks import aggregate_rationale_reports, rationale_row_report
from .row_ids import report_row_id, safe_value_summary
from .style import ACTION_TERMS, NEGATION_MODALITY_TERMS


DEFAULT_GROUP_COLUMNS = ("source", "label")


class SourceReportError(ValueError):
    pass


def rounded(value: float) -> float:
    return round(float(value), 4)


def retention(after_count: int, before_count: int) -> float:
    if before_count == 0:
        return 1.0
    return after_count / before_count


def focused_cue_report(original: str, protected: str) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    losses: list[str] = []
    term_groups = {
        "action_terms": sorted(ACTION_TERMS),
        "negation_modality_terms": sorted(NEGATION_MODALITY_TERMS),
    }
    for group_name, terms in term_groups.items():
        before = counts_for_terms(original, terms)
        after = counts_for_terms(protected, terms)
        before_total = sum(before.values())
        after_total = sum(after.values())
        group_retention = rounded(retention(after_total, before_total))
        if before_total and group_retention < 1.0:
            losses.append(group_name)
        groups[group_name] = {
            "before": before_total,
            "after": after_total,
            "retention": group_retention,
        }
    return {"loss_groups": losses, "groups": groups}


@dataclass
class MeanTracker:
    total: float = 0.0
    count: int = 0

    def add(self, value: float, *, include: bool = True) -> None:
        if include:
            self.total += float(value)
            self.count += 1

    def value(self, *, default: float = 1.0) -> float:
        if not self.count:
            return default
        return round(self.total / self.count, 4)


@dataclass
class GroupAccumulator:
    row_count: int = 0
    changed_text_count: int = 0
    identifier_before: int = 0
    identifier_after: int = 0
    direct_before: int = 0
    direct_after: int = 0
    quasi_before: int = 0
    quasi_after: int = 0
    target_retention: MeanTracker = field(default_factory=MeanTracker)
    utility_retention: MeanTracker = field(default_factory=MeanTracker)
    action_retention: MeanTracker = field(default_factory=MeanTracker)
    negation_modality_retention: MeanTracker = field(default_factory=MeanTracker)
    character_retention: MeanTracker = field(default_factory=MeanTracker)
    privacy_warnings: Counter[str] = field(default_factory=Counter)
    overmasking_warnings: Counter[str] = field(default_factory=Counter)
    warning_counts: Counter[str] = field(default_factory=Counter)
    rows_with_privacy_warnings: int = 0
    rows_with_warnings: int = 0
    utility_loss_rows: int = 0
    context_loss_rows: int = 0
    rationale_loss_rows: int = 0
    context_before: Counter[str] = field(default_factory=Counter)
    context_after: Counter[str] = field(default_factory=Counter)
    context_lost: Counter[str] = field(default_factory=Counter)
    rationale_reports: list[dict[str, Any]] = field(default_factory=list)
    issue_row_ids: list[str] = field(default_factory=list)

    def add_issue_row(self, row_id: str) -> None:
        if len(self.issue_row_ids) < 50:
            self.issue_row_ids.append(row_id)

    def add(
        self,
        *,
        row_id: str,
        original: str,
        protected: str,
        metrics: dict[str, Any],
        cue_report: dict[str, Any],
        context_before: dict[str, Any],
        context_after: dict[str, Any],
        rationale_report: dict[str, Any],
    ) -> None:
        self.row_count += 1
        if original != protected:
            self.changed_text_count += 1
        self.identifier_before += int(metrics.get("privacy_identifier_count_before", 0))
        self.identifier_after += int(metrics.get("privacy_identifier_count_after", 0))
        self.direct_before += int(metrics.get("direct_identifier_count_before", 0))
        self.direct_after += int(metrics.get("direct_identifier_count_after", 0))
        self.quasi_before += int(metrics.get("quasi_identifier_count_before", 0))
        self.quasi_after += int(metrics.get("quasi_identifier_count_after", 0))
        self.target_retention.add(metrics.get("target_cue_retention", 1.0))
        self.utility_retention.add(metrics.get("utility_cue_retention", 1.0))
        self.character_retention.add(metrics.get("character_utility_retention", 1.0))

        action_group = cue_report["groups"]["action_terms"]
        negation_group = cue_report["groups"]["negation_modality_terms"]
        self.action_retention.add(
            action_group["retention"],
            include=action_group["before"] > 0,
        )
        self.negation_modality_retention.add(
            negation_group["retention"],
            include=negation_group["before"] > 0,
        )

        privacy_warnings = list(metrics.get("privacy_warnings", []))
        warnings = list(metrics.get("warnings", []))
        self.privacy_warnings.update(privacy_warnings)
        self.overmasking_warnings.update(metrics.get("overmasking_warnings", []))
        self.warning_counts.update(warnings)
        if privacy_warnings:
            self.rows_with_privacy_warnings += 1
        if warnings:
            self.rows_with_warnings += 1

        before_tags = set(context_before.get("context_tags", []))
        after_tags = set(context_after.get("context_tags", []))
        self.context_before.update(before_tags)
        self.context_after.update(after_tags)
        lost_tags = before_tags - after_tags
        if lost_tags:
            self.context_loss_rows += 1
            self.context_lost.update(lost_tags)

        cue_loss = bool(cue_report["loss_groups"]) or (
            float(metrics.get("target_cue_retention", 1.0)) < 1.0
            or float(metrics.get("utility_cue_retention", 1.0)) < 1.0
        )
        if cue_loss:
            self.utility_loss_rows += 1

        row_rationale_loss = False
        if rationale_report.get("has_rationale"):
            self.rationale_reports.append(rationale_report)
            if float(rationale_report.get("rationale_span_retention", 1.0)) < 1.0:
                self.rationale_loss_rows += 1
                row_rationale_loss = True

        if privacy_warnings or cue_loss or lost_tags or row_rationale_loss:
            self.add_issue_row(row_id)

    def summary(self, group: dict[str, str] | None = None) -> dict[str, Any]:
        row_count = self.row_count
        changed_rate = self.changed_text_count / row_count if row_count else 0.0
        rationale = aggregate_rationale_reports(self.rationale_reports)
        result = {
            "row_count": row_count,
            "changed_text_count": self.changed_text_count,
            "changed_text_rate": round(changed_rate, 4),
            "identifier_counts": {
                "before": self.identifier_before,
                "after": self.identifier_after,
            },
            "direct_identifier_counts": {
                "before": self.direct_before,
                "after": self.direct_after,
            },
            "quasi_identifier_counts": {
                "before": self.quasi_before,
                "after": self.quasi_after,
            },
            "target_cue_retention_mean": self.target_retention.value(),
            "utility_cue_retention_mean": self.utility_retention.value(),
            "action_cue_retention_mean": self.action_retention.value(),
            "negation_modality_retention_mean": (
                self.negation_modality_retention.value()
            ),
            "character_retention_mean": self.character_retention.value(default=0.0),
            "privacy_warning_counts": dict(sorted(self.privacy_warnings.items())),
            "overmasking_warning_counts": dict(
                sorted(self.overmasking_warnings.items())
            ),
            "warning_counts": dict(sorted(self.warning_counts.items())),
            "rows_with_privacy_warnings": self.rows_with_privacy_warnings,
            "rows_with_warnings": self.rows_with_warnings,
            "utility_loss_rows": self.utility_loss_rows,
            "context_loss_rows": self.context_loss_rows,
            "rationale_loss_rows": self.rationale_loss_rows,
            "context_tag_counts": {
                "before": dict(sorted(self.context_before.items())),
                "after": dict(sorted(self.context_after.items())),
                "lost": dict(sorted(self.context_lost.items())),
            },
            "rationale": rationale,
            "issue_row_ids_sample": self.issue_row_ids,
        }
        if group is not None:
            result["group"] = group
        return result


def validate_columns(
    *,
    original_path: Path,
    protected_path: Path,
    original_fields: list[str],
    protected_fields: list[str],
    original_text_col: str,
    protected_text_col: str,
    id_col: str | None,
    group_cols: list[str],
) -> None:
    if original_text_col not in original_fields:
        raise SourceReportError(
            f"{original_path}: missing original text column {original_text_col!r}"
        )
    if protected_text_col not in protected_fields:
        raise SourceReportError(
            f"{protected_path}: missing protected text column {protected_text_col!r}"
        )
    if id_col and id_col not in original_fields:
        raise SourceReportError(f"{original_path}: missing id column {id_col!r}")
    if id_col and id_col not in protected_fields:
        raise SourceReportError(f"{protected_path}: missing id column {id_col!r}")
    missing_groups = [column for column in group_cols if column not in original_fields]
    if missing_groups:
        raise SourceReportError(
            f"{original_path}: missing group column(s): {', '.join(missing_groups)}"
        )


def normalize_group_value(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "<blank>"


def group_key(row: dict[str, str], group_cols: list[str]) -> tuple[str, ...]:
    return tuple(normalize_group_value(row.get(column, "")) for column in group_cols)


def group_dict(key: tuple[str, ...], group_cols: list[str]) -> dict[str, str]:
    return dict(zip(group_cols, key))


def top_groups(
    summaries: list[dict[str, Any]],
    *,
    key: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return sorted(
        summaries,
        key=lambda item: (int(item.get(key, 0)), int(item.get("row_count", 0))),
        reverse=True,
    )[:limit]


def run_source_regression_report(
    original_path: Path,
    protected_path: Path,
    *,
    original_text_col: str,
    protected_text_col: str,
    id_col: str | None = None,
    group_cols: list[str] | None = None,
    source_col: str = "source",
    label_col: str = "label",
    rationale_col: str = "rationale_spans",
    output_path: Path | None = None,
) -> dict[str, Any]:
    original_rows, original_fields = read_csv(original_path)
    protected_rows, protected_fields = read_csv(protected_path)
    selected_group_cols = list(group_cols or DEFAULT_GROUP_COLUMNS)
    validate_columns(
        original_path=original_path,
        protected_path=protected_path,
        original_fields=original_fields,
        protected_fields=protected_fields,
        original_text_col=original_text_col,
        protected_text_col=protected_text_col,
        id_col=id_col,
        group_cols=selected_group_cols,
    )
    if len(original_rows) != len(protected_rows):
        raise SourceReportError(
            "original/protected row counts differ: "
            f"{len(original_rows)} != {len(protected_rows)}"
        )

    id_mismatches: list[dict[str, Any]] = []
    overall = GroupAccumulator()
    groups: dict[tuple[str, ...], GroupAccumulator] = {}

    for row_index, (original_row, protected_row) in enumerate(
        zip(original_rows, protected_rows),
        start=1,
    ):
        row_id = report_row_id(original_row, row_index=row_index, id_col=id_col)
        if id_col and original_row.get(id_col) != protected_row.get(id_col):
            id_mismatches.append(
                {
                    "row_index": row_index,
                    "original_id": safe_value_summary(original_row.get(id_col)),
                    "protected_id": safe_value_summary(protected_row.get(id_col)),
                }
            )
            continue

        original = str(original_row.get(original_text_col, "") or "")
        protected = str(protected_row.get(protected_text_col, "") or "")
        metrics = row_metric(original, protected)
        cue_report = focused_cue_report(original, protected)
        before_target_categories = metrics.get(
            "target_cue_counts_by_category_before",
            {},
        )
        after_target_categories = metrics.get(
            "target_cue_counts_by_category_after",
            {},
        )
        before_context = analyze_context(
            original,
            protected_target=metrics.get("target_cue_count_before", 0) > 0,
            historical_victim_group=before_target_categories.get(
                "historical_victim_group",
                0,
            )
            > 0,
        )
        after_context = analyze_context(
            protected,
            protected_target=metrics.get("target_cue_count_after", 0) > 0,
            historical_victim_group=after_target_categories.get(
                "historical_victim_group",
                0,
            )
            > 0,
        )
        rationale = rationale_row_report(
            row_index=row_index,
            row_id=row_id,
            source=str(original_row.get(source_col, "") or ""),
            label=str(original_row.get(label_col, "") or "") if label_col else None,
            original=original,
            protected=protected,
            raw_spans=str(original_row.get(rationale_col, "") or ""),
        )

        kwargs = {
            "row_id": row_id,
            "original": original,
            "protected": protected,
            "metrics": metrics,
            "cue_report": cue_report,
            "context_before": before_context,
            "context_after": after_context,
            "rationale_report": rationale,
        }
        overall.add(**kwargs)
        key = group_key(original_row, selected_group_cols)
        groups.setdefault(key, GroupAccumulator()).add(**kwargs)

    if id_mismatches:
        raise SourceReportError(
            f"ID order mismatch in {len(id_mismatches)} row(s); first mismatch: "
            f"{id_mismatches[0]}"
        )

    group_summaries = [
        accumulator.summary(group=group_dict(key, selected_group_cols))
        for key, accumulator in sorted(groups.items())
    ]
    result = {
        "artifact_type": "source_aware_regression_report",
        "original": str(original_path),
        "protected": str(protected_path),
        "columns": {
            "original_text_col": original_text_col,
            "protected_text_col": protected_text_col,
            "id_col": id_col,
            "group_cols": selected_group_cols,
            "source_col": source_col,
            "label_col": label_col,
            "rationale_col": rationale_col,
        },
        "row_count": len(original_rows),
        "row_order_valid": True,
        "notes": [
            "Aggregate report only; raw text is intentionally omitted.",
            "Labels and type fields are source-aware and are not collapsed.",
            "Rationale parsing branches on source: HateXplain token ranges and Toxic Spans character ranges.",
        ],
        "overall": overall.summary(),
        "groups": group_summaries,
        "top_risky_groups_by_privacy_warnings": top_groups(
            group_summaries,
            key="rows_with_privacy_warnings",
        ),
        "top_risky_groups_by_utility_loss": top_groups(
            group_summaries,
            key="utility_loss_rows",
        ),
        "top_risky_groups_by_rationale_loss": top_groups(
            group_summaries,
            key="rationale_loss_rows",
        ),
    }
    if output_path:
        write_json(output_path, result)
    return result
