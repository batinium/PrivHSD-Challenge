"""Column names used by pipeline artifacts."""

from __future__ import annotations

LABEL_CANDIDATES = ("hs", "label", "hate", "is_hate", "predicted_hate", "hs_predicted")
PREDICTED_LABEL_COL = "hs_predicted"
PREDICTION_SCORE_COL = "hf_hsd_score"
THRESHOLD_COL = "hf_hsd_threshold"


def resolve_label_col(
    fieldnames: list[str],
    requested: str | None,
) -> str | None:
    if requested and requested in fieldnames:
        return requested
    if requested is not None:
        return None
    for candidate in LABEL_CANDIDATES:
        if candidate in fieldnames:
            return candidate
    return None
