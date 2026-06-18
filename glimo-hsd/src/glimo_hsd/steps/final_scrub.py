"""Final direct-identifier cleanup for restatement outputs."""

from __future__ import annotations

from pathlib import Path

from .pii import scrub_csv


def final_scrub_csv(
    input_csv: str | Path,
    output_csv: str | Path,
    *,
    text_col: str = "text",
):
    result = scrub_csv(input_csv, output_csv, text_col=text_col)
    return type(result)(
        name="final_scrub",
        status=result.status,
        path=result.path,
        metadata=result.metadata,
    )
