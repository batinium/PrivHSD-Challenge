"""Local privacy/utility proxy metrics.

These metrics are not the official leaderboard formula. They are deliberately
simple so the team can compare runs before the official evaluator is available.
"""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
import re
from statistics import mean
from typing import Any, Iterable

from .detectors import (
    TAGS,
    TARGET_GROUP_CATEGORIES,
    Span,
    detect_spans,
    target_group_term_patterns,
)
from .resource_config import load_utility_cue_terms


UTILITY_CUES = load_utility_cue_terms("utility_cues")

DIRECT_IDENTIFIER_TYPES = frozenset(
    {
        "ALIAS",
        "PERSON",
        "USER",
        "EMAIL",
        "PHONE",
        "URL",
        "IP_ADDRESS",
        "IDENTIFIER",
    }
)
QUASI_IDENTIFIER_TYPES = frozenset(
    {
        "AGE",
        "DATE",
        "LOCATION",
        "ORGANIZATION",
    }
)
KNOWN_PLACEHOLDER_TYPES = frozenset(
    {tag.strip("[]") for tag in TAGS.values()}
    | {f"TARGET_GROUP:{category}" for category in TARGET_GROUP_CATEGORIES}
)

PLACEHOLDER_PATTERN = re.compile(
    r"\[(?P<kind>[A-Z][A-Z_]*(?::[A-Za-z0-9_/-]+)?)\]"
)
TOKEN_PATTERN = re.compile(r"\[[^\]]+\]|[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")

HIGH_PLACEHOLDER_DENSITY = 0.4
HIGH_MASK_DENSITY = 0.5
LOW_CHARACTER_UTILITY_RETENTION = 0.55
TARGET_CUE_LOSS_THRESHOLD = 0.8
METRIC_DEPTHS = frozenset({"fast", "sampled", "deep"})
DEFAULT_SAMPLED_DEEP_ROWS = 100


@lru_cache(maxsize=1)
def utility_cue_patterns() -> tuple[re.Pattern[str], ...]:
    return tuple(
        re.compile(
            r"(?<![a-z0-9])" + re.escape(cue) + r"(?![a-z0-9])",
            re.I,
        )
        for cue in sorted(UTILITY_CUES, key=lambda value: (-len(value), value))
    )


def cue_count(text: str) -> int:
    count = 0
    for pattern in utility_cue_patterns():
        count += len(pattern.findall(text))
    return count


def safe_ratio(numerator: float, denominator: float, *, default: float = 0.0) -> float:
    return numerator / denominator if denominator else default


def round_ratio(numerator: float, denominator: float, *, default: float = 0.0) -> float:
    return round(safe_ratio(numerator, denominator, default=default), 4)


def sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def span_counts(spans: Iterable[Span]) -> Counter[str]:
    return Counter(span.entity_type for span in spans)


def identifier_spans(text: str) -> list[Span]:
    return detect_spans(text, include_context=True, include_targets=False)


def direct_spans(spans: Iterable[Span]) -> list[Span]:
    return [span for span in spans if span.entity_type in DIRECT_IDENTIFIER_TYPES]


def quasi_spans(spans: Iterable[Span]) -> list[Span]:
    return [span for span in spans if span.entity_type in QUASI_IDENTIFIER_TYPES]


def target_term_spans(text: str) -> list[Span]:
    return [
        span
        for span in detect_spans(text, include_context=False, include_targets=True)
        if span.entity_type == "TARGET_GROUP"
    ]


def placeholder_counts(text: str) -> tuple[Counter[str], int]:
    counts: Counter[str] = Counter()
    placeholder_characters = 0
    for match in PLACEHOLDER_PATTERN.finditer(text):
        kind = match.group("kind")
        if kind not in KNOWN_PLACEHOLDER_TYPES:
            continue
        counts[kind] += 1
        placeholder_characters += match.end() - match.start()
    return counts, placeholder_characters


def target_placeholder_counts(placeholders: Counter[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for placeholder_type, count in placeholders.items():
        if placeholder_type.startswith("TARGET_GROUP:"):
            category = placeholder_type.split(":", 1)[1]
            counts[category] += count
    return counts


def target_cue_counts(text: str) -> tuple[Counter[str], Counter[str]]:
    term_counts = Counter(
        span.category
        for span in target_term_spans(text)
        if span.category is not None
    )
    placeholders, _ = placeholder_counts(text)
    cue_counts = term_counts + target_placeholder_counts(placeholders)
    return term_counts, cue_counts


def target_cue_counts_fast(text: str) -> tuple[Counter[str], Counter[str]]:
    """Count explicit target cue terms without variant/profanity scans."""
    term_counts: Counter[str] = Counter()
    for category, _term, pattern in target_group_term_patterns():
        term_counts[category] += len(pattern.findall(text))
    placeholders, _ = placeholder_counts(text)
    cue_counts = term_counts + target_placeholder_counts(placeholders)
    return term_counts, cue_counts


def quasi_flags(counts: Counter[str]) -> dict[str, bool]:
    return {
        entity_type: counts.get(entity_type, 0) > 0
        for entity_type in sorted(QUASI_IDENTIFIER_TYPES)
    }


def warning_codes(
    *,
    before_privacy: int,
    after_privacy: int,
    after_direct: int,
    after_quasi: int,
    after_quasi_type_count: int,
    placeholder_count: int,
    placeholder_density: float,
    mask_density: float,
    utility_retention: float,
    target_cues_before: int,
    target_cue_retention: float,
    original: str,
    privatized: str,
) -> tuple[list[str], list[str], list[str]]:
    privacy_warnings: list[str] = []
    overmasking_warnings: list[str] = []

    if after_privacy:
        privacy_warnings.append("residual_identifier_detected")
    if after_direct:
        privacy_warnings.append("residual_direct_identifier_detected")
    if after_quasi:
        privacy_warnings.append("residual_quasi_identifier_detected")
    if after_quasi_type_count >= 2:
        privacy_warnings.append("residual_quasi_identifier_combination")

    if placeholder_count >= 3 and placeholder_density >= HIGH_PLACEHOLDER_DENSITY:
        overmasking_warnings.append("high_placeholder_density")
    if placeholder_count and mask_density >= HIGH_MASK_DENSITY:
        overmasking_warnings.append("high_mask_density")
    if original and utility_retention < LOW_CHARACTER_UTILITY_RETENTION:
        overmasking_warnings.append("low_character_utility_retention")
    if target_cues_before and target_cue_retention < TARGET_CUE_LOSS_THRESHOLD:
        overmasking_warnings.append("target_cue_loss")
    if (
        original != privatized
        and placeholder_count
        and before_privacy == 0
        and target_cues_before == 0
    ):
        overmasking_warnings.append("changed_without_detected_sensitive_span")

    return (
        privacy_warnings,
        overmasking_warnings,
        [*privacy_warnings, *overmasking_warnings],
    )


def _row_metric_impl(
    original: str,
    privatized: str,
    *,
    deep_target_scan: bool,
) -> dict[str, Any]:
    before_spans = identifier_spans(original)
    after_spans = identifier_spans(privatized)
    before_direct_spans = direct_spans(before_spans)
    after_direct_spans = direct_spans(after_spans)
    before_quasi_spans = quasi_spans(before_spans)
    after_quasi_spans = quasi_spans(after_spans)
    before_counts = span_counts(before_spans)
    after_counts = span_counts(after_spans)
    before_direct_counts = span_counts(before_direct_spans)
    after_direct_counts = span_counts(after_direct_spans)
    before_quasi_counts = span_counts(before_quasi_spans)
    after_quasi_counts = span_counts(after_quasi_spans)

    before_privacy = len(before_spans)
    after_privacy = len(after_spans)
    before_direct = len(before_direct_spans)
    after_direct = len(after_direct_spans)
    before_quasi = len(before_quasi_spans)
    after_quasi = len(after_quasi_spans)
    before_cues = cue_count(original)
    after_cues = cue_count(privatized)
    placeholders, placeholder_characters = placeholder_counts(privatized)
    placeholder_count = sum(placeholders.values())
    token_count = len(TOKEN_PATTERN.findall(privatized))
    mask_density = round_ratio(placeholder_characters, len(privatized))
    placeholder_density = round_ratio(placeholder_count, token_count)
    target_count_fn = target_cue_counts if deep_target_scan else target_cue_counts_fast
    target_terms_before, target_cues_by_category_before = target_count_fn(original)
    target_terms_after, target_cues_by_category_after = target_count_fn(privatized)
    target_cues_before = sum(target_cues_by_category_before.values())
    target_cues_after = sum(target_cues_by_category_after.values())
    target_terms_before_count = sum(target_terms_before.values())
    target_terms_after_count = sum(target_terms_after.values())
    target_categories_before = set(target_cues_by_category_before)
    target_categories_after = set(target_cues_by_category_after)
    target_category_retention = (
        len(target_categories_before & target_categories_after)
        / len(target_categories_before)
        if target_categories_before
        else 1.0
    )
    privacy_gain = (
        (before_privacy - after_privacy) / before_privacy
        if before_privacy
        else 0.0
    )
    cue_retention = after_cues / before_cues if before_cues else 1.0
    utility_retention = SequenceMatcher(None, original, privatized).ratio()
    target_cue_retention = safe_ratio(
        target_cues_after,
        target_cues_before,
        default=1.0,
    )
    target_term_retention = safe_ratio(
        target_terms_after_count,
        target_terms_before_count,
        default=1.0,
    )
    proxy_tradeoff = privacy_gain - (1 - max(cue_retention, utility_retention))
    privacy_warnings, overmasking_warnings, warnings = warning_codes(
        before_privacy=before_privacy,
        after_privacy=after_privacy,
        after_direct=after_direct,
        after_quasi=after_quasi,
        after_quasi_type_count=len(after_quasi_counts),
        placeholder_count=placeholder_count,
        placeholder_density=placeholder_density,
        mask_density=mask_density,
        utility_retention=utility_retention,
        target_cues_before=target_cues_before,
        target_cue_retention=target_cue_retention,
        original=original,
        privatized=privatized,
    )
    return {
        "metric_depth": "deep" if deep_target_scan else "fast",
        "privacy_identifier_count_before": before_privacy,
        "privacy_identifier_count_after": after_privacy,
        "privacy_gain": round(privacy_gain, 4),
        "identifier_counts_by_entity_type_before": sorted_counter(before_counts),
        "identifier_counts_by_entity_type_after": sorted_counter(after_counts),
        "residual_identifier_count": after_privacy,
        "residual_identifier_counts_by_entity_type": sorted_counter(after_counts),
        "direct_identifier_count_before": before_direct,
        "direct_identifier_count_after": after_direct,
        "direct_identifier_counts_by_entity_type_before": sorted_counter(
            before_direct_counts
        ),
        "direct_identifier_counts_by_entity_type_after": sorted_counter(
            after_direct_counts
        ),
        "residual_direct_identifier_count": after_direct,
        "quasi_identifier_count_before": before_quasi,
        "quasi_identifier_count_after": after_quasi,
        "quasi_identifier_counts_by_entity_type_before": sorted_counter(
            before_quasi_counts
        ),
        "quasi_identifier_counts_by_entity_type_after": sorted_counter(
            after_quasi_counts
        ),
        "quasi_identifier_flags": {
            "before": quasi_flags(before_quasi_counts),
            "after": quasi_flags(after_quasi_counts),
        },
        "residual_quasi_identifier_count": after_quasi,
        "residual_quasi_identifier_type_count": len(after_quasi_counts),
        "utility_cue_count_before": before_cues,
        "utility_cue_count_after": after_cues,
        "utility_cue_retention": round(cue_retention, 4),
        "target_cue_count_before": target_cues_before,
        "target_cue_count_after": target_cues_after,
        "target_cue_retention": round(target_cue_retention, 4),
        "target_cue_counts_by_category_before": sorted_counter(
            target_cues_by_category_before
        ),
        "target_cue_counts_by_category_after": sorted_counter(
            target_cues_by_category_after
        ),
        "target_categories_before": sorted(target_categories_before),
        "target_categories_after": sorted(target_categories_after),
        "target_category_retention": round(target_category_retention, 4),
        "target_term_count_before": target_terms_before_count,
        "target_term_count_after": target_terms_after_count,
        "target_term_retention": round(target_term_retention, 4),
        "target_term_counts_by_category_before": sorted_counter(target_terms_before),
        "target_term_counts_by_category_after": sorted_counter(target_terms_after),
        "character_utility_retention": round(utility_retention, 4),
        "proxy_tradeoff": round(max(-1.0, min(1.0, proxy_tradeoff)), 4),
        "mask_density": mask_density,
        "placeholder_count": placeholder_count,
        "placeholder_density": placeholder_density,
        "placeholder_counts_by_type": sorted_counter(placeholders),
        "placeholder_character_count": placeholder_characters,
        "token_count": token_count,
        "privacy_warnings": privacy_warnings,
        "overmasking_warnings": overmasking_warnings,
        "warnings": warnings,
    }


def row_metric_deep(original: str, privatized: str) -> dict[str, Any]:
    return _row_metric_impl(original, privatized, deep_target_scan=True)


def row_metric_fast(original: str, privatized: str) -> dict[str, Any]:
    return _row_metric_impl(original, privatized, deep_target_scan=False)


def row_metric_for_depth(
    original: str,
    privatized: str,
    *,
    metric_depth: str = "deep",
    row_index: int | None = None,
    deep_sample_size: int = DEFAULT_SAMPLED_DEEP_ROWS,
) -> dict[str, Any]:
    if metric_depth not in METRIC_DEPTHS:
        raise ValueError(f"metric_depth must be one of {sorted(METRIC_DEPTHS)}")
    if metric_depth == "deep":
        return row_metric_deep(original, privatized)
    if metric_depth == "fast":
        return row_metric_fast(original, privatized)
    if row_index is not None and row_index <= max(0, deep_sample_size):
        metric = row_metric_deep(original, privatized)
        metric["metric_depth"] = "sampled_deep"
        return metric
    metric = row_metric_fast(original, privatized)
    metric["metric_depth"] = "sampled_fast"
    return metric


def row_metric(
    original: str,
    privatized: str,
    *,
    metric_depth: str = "deep",
) -> dict[str, Any]:
    return row_metric_for_depth(
        original,
        privatized,
        metric_depth=metric_depth,
    )


def counter_sum(rows: Iterable[dict[str, Any]], key: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        for entity_type, value in row.get(key, {}).items():
            counts[str(entity_type)] += int(value)
    return counts


def warning_sum(rows: Iterable[dict[str, Any]], key: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        for warning in row.get(key, []):
            counts[str(warning)] += 1
    return counts


def mean_metric(rows: list[dict[str, Any]], key: str, *, default: float = 0.0) -> float:
    return round(mean(float(row.get(key, default)) for row in rows), 4)


def aggregate_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    if not materialized:
        return {
            "row_count": 0,
            "privacy_gain_mean": 0.0,
            "utility_cue_retention_mean": 0.0,
            "character_utility_retention_mean": 0.0,
            "proxy_tradeoff_mean": 0.0,
            "identifier_counts": {"before": 0, "after": 0},
            "identifier_counts_by_entity_type": {"before": {}, "after": {}},
            "direct_identifier_counts": {"before": 0, "after": 0},
            "direct_identifier_counts_by_entity_type": {"before": {}, "after": {}},
            "residual_identifier_count": 0,
            "residual_identifier_counts_by_entity_type": {},
            "residual_direct_identifier_count": 0,
            "quasi_identifier_counts": {"before": 0, "after": 0},
            "quasi_identifier_counts_by_entity_type": {"before": {}, "after": {}},
            "residual_quasi_identifier_count": 0,
            "mask_density_mean": 0.0,
            "placeholder_density_mean": 0.0,
            "placeholder_count_total": 0,
            "placeholder_counts_by_type": {},
            "target_cue_retention_mean": 0.0,
            "target_term_retention_mean": 0.0,
            "target_cue_counts": {"before": 0, "after": 0},
            "target_cue_counts_by_category": {"before": {}, "after": {}},
            "target_term_counts": {"before": 0, "after": 0},
            "target_term_counts_by_category": {"before": {}, "after": {}},
            "privacy_warning_counts": {},
            "overmasking_warning_counts": {},
            "warning_counts": {},
            "rows_with_warnings": 0,
            "rows_with_privacy_warnings": 0,
            "rows_with_overmasking_warnings": 0,
            "metric_depth_counts": {},
            "transformed_entity_counts": {},
        }
    before = sum(row["privacy_identifier_count_before"] for row in materialized)
    after = sum(row["privacy_identifier_count_after"] for row in materialized)
    placeholders = Counter()
    for row in materialized:
        for key, value in row.get("counts_by_entity_type", {}).items():
            placeholders[str(key)] += int(value)
    direct_before = sum(
        row.get("direct_identifier_count_before", 0) for row in materialized
    )
    direct_after = sum(
        row.get("direct_identifier_count_after", 0) for row in materialized
    )
    quasi_before = sum(
        row.get("quasi_identifier_count_before", 0) for row in materialized
    )
    quasi_after = sum(
        row.get("quasi_identifier_count_after", 0) for row in materialized
    )
    target_cues_before = sum(
        row.get("target_cue_count_before", 0) for row in materialized
    )
    target_cues_after = sum(
        row.get("target_cue_count_after", 0) for row in materialized
    )
    target_terms_before = sum(
        row.get("target_term_count_before", 0) for row in materialized
    )
    target_terms_after = sum(
        row.get("target_term_count_after", 0) for row in materialized
    )
    return {
        "row_count": len(materialized),
        "privacy_gain_mean": round(mean(row["privacy_gain"] for row in materialized), 4),
        "utility_cue_retention_mean": round(
            mean(row["utility_cue_retention"] for row in materialized),
            4,
        ),
        "character_utility_retention_mean": round(
            mean(row["character_utility_retention"] for row in materialized),
            4,
        ),
        "proxy_tradeoff_mean": round(
            mean(row["proxy_tradeoff"] for row in materialized),
            4,
        ),
        "identifier_counts": {"before": before, "after": after},
        "identifier_counts_by_entity_type": {
            "before": sorted_counter(
                counter_sum(materialized, "identifier_counts_by_entity_type_before")
            ),
            "after": sorted_counter(
                counter_sum(materialized, "identifier_counts_by_entity_type_after")
            ),
        },
        "direct_identifier_counts": {"before": direct_before, "after": direct_after},
        "direct_identifier_counts_by_entity_type": {
            "before": sorted_counter(
                counter_sum(
                    materialized,
                    "direct_identifier_counts_by_entity_type_before",
                )
            ),
            "after": sorted_counter(
                counter_sum(
                    materialized,
                    "direct_identifier_counts_by_entity_type_after",
                )
            ),
        },
        "residual_identifier_count": sum(
            row.get("residual_identifier_count", row["privacy_identifier_count_after"])
            for row in materialized
        ),
        "residual_identifier_counts_by_entity_type": sorted_counter(
            counter_sum(materialized, "residual_identifier_counts_by_entity_type")
        ),
        "residual_direct_identifier_count": sum(
            row.get("residual_direct_identifier_count", 0) for row in materialized
        ),
        "quasi_identifier_counts": {"before": quasi_before, "after": quasi_after},
        "quasi_identifier_counts_by_entity_type": {
            "before": sorted_counter(
                counter_sum(
                    materialized,
                    "quasi_identifier_counts_by_entity_type_before",
                )
            ),
            "after": sorted_counter(
                counter_sum(
                    materialized,
                    "quasi_identifier_counts_by_entity_type_after",
                )
            ),
        },
        "residual_quasi_identifier_count": sum(
            row.get("residual_quasi_identifier_count", 0) for row in materialized
        ),
        "mask_density_mean": mean_metric(materialized, "mask_density"),
        "placeholder_density_mean": mean_metric(materialized, "placeholder_density"),
        "placeholder_count_total": sum(
            row.get("placeholder_count", 0) for row in materialized
        ),
        "placeholder_counts_by_type": sorted_counter(
            counter_sum(materialized, "placeholder_counts_by_type")
        ),
        "target_cue_retention_mean": mean_metric(
            materialized,
            "target_cue_retention",
            default=1.0,
        ),
        "target_term_retention_mean": mean_metric(
            materialized,
            "target_term_retention",
            default=1.0,
        ),
        "target_cue_counts": {
            "before": target_cues_before,
            "after": target_cues_after,
        },
        "target_cue_counts_by_category": {
            "before": sorted_counter(
                counter_sum(materialized, "target_cue_counts_by_category_before")
            ),
            "after": sorted_counter(
                counter_sum(materialized, "target_cue_counts_by_category_after")
            ),
        },
        "target_term_counts": {
            "before": target_terms_before,
            "after": target_terms_after,
        },
        "target_term_counts_by_category": {
            "before": sorted_counter(
                counter_sum(materialized, "target_term_counts_by_category_before")
            ),
            "after": sorted_counter(
                counter_sum(materialized, "target_term_counts_by_category_after")
            ),
        },
        "privacy_warning_counts": sorted_counter(
            warning_sum(materialized, "privacy_warnings")
        ),
        "overmasking_warning_counts": sorted_counter(
            warning_sum(materialized, "overmasking_warnings")
        ),
        "warning_counts": sorted_counter(warning_sum(materialized, "warnings")),
        "rows_with_warnings": sum(1 for row in materialized if row.get("warnings")),
        "rows_with_privacy_warnings": sum(
            1 for row in materialized if row.get("privacy_warnings")
        ),
        "rows_with_overmasking_warnings": sum(
            1 for row in materialized if row.get("overmasking_warnings")
        ),
        "metric_depth_counts": sorted_counter(
            Counter(str(row.get("metric_depth", "unknown")) for row in materialized)
        ),
        "transformed_entity_counts": dict(sorted(placeholders.items())),
    }
