"""Token-importance generation by simple classifier occlusion."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config import DEFAULT_MODEL_ID, DEFAULT_THRESHOLD
from ..io import CsvError, read_csv, sha256_file, write_csv
from ..models import load_classifier
from ..results import StepResult

TOKEN_PATTERN = re.compile(
    r"\[[A-Z][A-Z_]*(?::[A-Za-z0-9_/-]+)?\]|https?://\S+|@[A-Za-z0-9._-]+|"
    r"#[A-Za-z0-9_]{2,}|[A-Za-z][A-Za-z'-]*|\d+(?:[./-]\d+)*"
)


def _masked(text: str, start: int, end: int, mask: str = "[MASK]") -> str:
    return f"{text[:start]}{mask}{text[end:]}"


def generate_token_importances(
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
    protect_threshold: float = 0.03,
    enabled: bool = True,
) -> StepResult:
    rows, fieldnames = read_csv(input_csv)
    if text_col not in fieldnames:
        raise CsvError(f"missing text column {text_col!r}")
    output_path = Path(output_csv)
    out_fields = [
        "row_index",
        "row_id",
        "token_index",
        "token",
        "start",
        "end",
        "baseline_hate_score",
        "masked_hate_score",
        "delta_hate_score",
        "abs_delta_hate_score",
        "predicted_hate",
        "protect_hsd_token",
    ]
    if not enabled or backend == "none":
        write_csv(output_path, [], out_fields)
        return StepResult(
            name="token_importance",
            status="skipped",
            path=output_path,
            metadata={"reason": "disabled", "sha256": sha256_file(output_path)},
        )
    classifier = load_classifier(
        backend=backend,
        model_id=model_id,
        revision=model_revision,
        threshold=threshold,
        device=device,
        max_length=max_length,
    )
    if classifier is None:
        raise ValueError("token importance requires classifier backend hf or keyword")

    output_rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows, start=1):
        row_id = str(row.get(id_col or "", "") or row_index)
        text = str(row.get(text_col, "") or "")
        matches = list(TOKEN_PATTERN.finditer(text))
        if not matches:
            continue
        baseline = classifier.score_texts([text])[0]
        masked_scores: list[float] = []
        masked_texts = [_masked(text, match.start(), match.end()) for match in matches]
        for offset in range(0, len(masked_texts), batch_size):
            masked_scores.extend(
                classifier.score_texts(masked_texts[offset : offset + batch_size])
            )
        for token_index, (match, masked_score) in enumerate(
            zip(matches, masked_scores, strict=True)
        ):
            delta = float(baseline - masked_score)
            abs_delta = abs(delta)
            output_rows.append(
                {
                    "row_index": row_index,
                    "row_id": row_id,
                    "token_index": token_index,
                    "token": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "baseline_hate_score": round(float(baseline), 6),
                    "masked_hate_score": round(float(masked_score), 6),
                    "delta_hate_score": round(delta, 6),
                    "abs_delta_hate_score": round(abs_delta, 6),
                    "predicted_hate": int(baseline >= classifier.threshold),
                    "protect_hsd_token": int(abs_delta >= protect_threshold),
                }
            )
    output_rows.sort(
        key=lambda item: (
            int(item["row_index"]),
            -float(item["abs_delta_hate_score"]),
            int(item["token_index"]),
        )
    )
    write_csv(output_path, output_rows, out_fields)
    return StepResult(
        name="token_importance",
        status="complete",
        path=output_path,
        metadata={
            "backend": backend,
            "model_id": model_id,
            "model_revision": model_revision,
            "token_rows": len(output_rows),
            "protected_tokens": sum(
                int(row["protect_hsd_token"]) for row in output_rows
            ),
            "sha256": sha256_file(output_path),
        },
    )
