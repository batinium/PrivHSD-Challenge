"""CSV classification step."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import DEFAULT_MODEL_ID, DEFAULT_THRESHOLD
from ..io import CsvError, read_csv, sha256_file, write_csv
from ..models import load_classifier
from ..results import StepResult
from ..schemas.columns import PREDICTED_LABEL_COL, PREDICTION_SCORE_COL, THRESHOLD_COL


def classify_csv(
    input_csv: str | Path,
    output_csv: str | Path,
    *,
    text_col: str = "text",
    id_col: str | None = None,
    model_id: str = DEFAULT_MODEL_ID,
    model_revision: str | None = None,
    backend: str = "hf",
    threshold: float = DEFAULT_THRESHOLD,
    device: str = "auto",
    batch_size: int = 64,
    max_length: int = 512,
) -> StepResult:
    rows, fieldnames = read_csv(input_csv)
    if text_col not in fieldnames:
        raise CsvError(f"missing text column {text_col!r}")
    if id_col and id_col not in fieldnames:
        raise CsvError(f"missing id column {id_col!r}")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    classifier = load_classifier(
        backend=backend,
        model_id=model_id,
        revision=model_revision,
        threshold=threshold,
        device=device,
        max_length=max_length,
    )
    if classifier is None:
        raise ValueError("classification requires classifier backend hf or keyword")

    output_rows: list[dict[str, Any]] = []
    positives = 0
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        predictions = classifier.predict_texts(
            [str(row.get(text_col, "") or "") for row in batch]
        )
        for batch_index, (row, prediction) in enumerate(
            zip(batch, predictions, strict=True),
            start=1,
        ):
            row_index = offset + batch_index
            positives += int(prediction.hate)
            output_rows.append(
                {
                    "row_index": row_index,
                    "row_id": str(row.get(id_col or "", "") or row_index),
                    PREDICTION_SCORE_COL: round(prediction.score, 6),
                    PREDICTED_LABEL_COL: prediction.label,
                    THRESHOLD_COL: round(prediction.threshold, 6),
                }
            )
    output_path = Path(output_csv)
    write_csv(
        output_path,
        output_rows,
        [
            "row_index",
            "row_id",
            PREDICTION_SCORE_COL,
            PREDICTED_LABEL_COL,
            THRESHOLD_COL,
        ],
    )
    return StepResult(
        name="classification",
        status="complete",
        path=output_path,
        metadata={
            "backend": backend,
            "model_id": model_id,
            "model_revision": model_revision,
            "threshold": threshold,
            "row_count": len(rows),
            "positive_rows": positives,
            "negative_rows": len(rows) - positives,
            "sha256": sha256_file(output_path),
        },
    )


def write_label_predictions(
    input_csv: str | Path,
    output_csv: str | Path,
    *,
    label_col: str,
    id_col: str | None = None,
) -> StepResult:
    rows, fieldnames = read_csv(input_csv)
    if label_col not in fieldnames:
        raise CsvError(f"missing label column {label_col!r}")
    output_rows: list[dict[str, Any]] = []
    positives = 0
    for index, row in enumerate(rows, start=1):
        label = (
            "1"
            if str(row.get(label_col, "")).strip() in {"1", "true", "True"}
            else "0"
        )
        positives += int(label == "1")
        output_rows.append(
            {
                "row_index": index,
                "row_id": str(row.get(id_col or "", "") or index),
                PREDICTION_SCORE_COL: "",
                PREDICTED_LABEL_COL: label,
                THRESHOLD_COL: "",
            }
        )
    output_path = Path(output_csv)
    write_csv(
        output_path,
        output_rows,
        [
            "row_index",
            "row_id",
            PREDICTION_SCORE_COL,
            PREDICTED_LABEL_COL,
            THRESHOLD_COL,
        ],
    )
    return StepResult(
        name="classification",
        status="provided",
        path=output_path,
        metadata={
            "label_col": label_col,
            "label_source": "provided",
            "row_count": len(rows),
            "positive_rows": positives,
            "negative_rows": len(rows) - positives,
            "sha256": sha256_file(output_path),
        },
    )
