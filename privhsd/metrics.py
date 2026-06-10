"""Local privacy/utility proxy metrics.

These metrics are not the official leaderboard formula. They are deliberately
simple so the team can compare runs before the official evaluator is available.
"""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import re
from statistics import mean
from typing import Any, Iterable

from .detectors import detect_spans


UTILITY_CUES = (
    "threat",
    "attack",
    "ban",
    "deport",
    "exclude",
    "inferior",
    "worthless",
    "should leave",
    "not belong",
    "hate",
    "violent",
    "violence",
)


def cue_count(text: str) -> int:
    lowered = text.lower()
    count = 0
    for cue in UTILITY_CUES:
        pattern = r"(?<![a-z0-9])" + re.escape(cue) + r"(?![a-z0-9])"
        count += len(re.findall(pattern, lowered))
    return count


def direct_identifier_count(text: str) -> int:
    return len(detect_spans(text, include_context=True, include_targets=False))


def row_metric(original: str, privatized: str) -> dict[str, Any]:
    before_privacy = direct_identifier_count(original)
    after_privacy = direct_identifier_count(privatized)
    before_cues = cue_count(original)
    after_cues = cue_count(privatized)
    privacy_gain = (
        (before_privacy - after_privacy) / before_privacy
        if before_privacy
        else 0.0
    )
    cue_retention = after_cues / before_cues if before_cues else 1.0
    utility_retention = SequenceMatcher(None, original, privatized).ratio()
    proxy_tradeoff = privacy_gain - (1 - max(cue_retention, utility_retention))
    return {
        "privacy_identifier_count_before": before_privacy,
        "privacy_identifier_count_after": after_privacy,
        "privacy_gain": round(privacy_gain, 4),
        "utility_cue_count_before": before_cues,
        "utility_cue_count_after": after_cues,
        "utility_cue_retention": round(cue_retention, 4),
        "character_utility_retention": round(utility_retention, 4),
        "proxy_tradeoff": round(max(-1.0, min(1.0, proxy_tradeoff)), 4),
    }


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
        }
    before = sum(row["privacy_identifier_count_before"] for row in materialized)
    after = sum(row["privacy_identifier_count_after"] for row in materialized)
    placeholders = Counter()
    for row in materialized:
        for key, value in row.get("counts_by_entity_type", {}).items():
            placeholders[str(key)] += int(value)
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
        "transformed_entity_counts": dict(sorted(placeholders.items())),
    }

