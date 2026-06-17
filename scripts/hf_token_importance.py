"""Token occlusion attribution for the local HF HSD classifier.

This is an analysis tool, not part of the submission CSV path. It estimates
which raw-text tokens contribute to the classifier's hate probability by
masking one token at a time and re-scoring the row.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from contextsafe_hsd.models.hf_hsd_classifier_runtime import (
    DEFAULT_HF_HSD_MAX_LENGTH,
    DEFAULT_HF_HSD_MODEL_PATH,
    DEFAULT_HF_HSD_THRESHOLD,
    HfHsdClassifierRuntime,
)


TOKEN_PATTERN = re.compile(
    r"\[[A-Z][A-Z_]*(?::[A-Za-z0-9_/-]+)?\]"
    r"|https?://\S+"
    r"|@[A-Za-z0-9._-]+"
    r"|#[A-Za-z0-9_]{2,}"
    r"|[A-Za-z][A-Za-z'-]*"
    r"|\d+(?:[./-]\d+)*"
)


@dataclass(frozen=True)
class TokenSpan:
    index: int
    text: str
    start: int
    end: int


def iter_tokens(text: str) -> Iterable[TokenSpan]:
    for index, match in enumerate(TOKEN_PATTERN.finditer(text)):
        yield TokenSpan(
            index=index,
            text=match.group(0),
            start=match.start(),
            end=match.end(),
        )


def masked_text(text: str, token: TokenSpan, mask_token: str) -> str:
    return f"{text[: token.start]}{mask_token}{text[token.end :]}"


def read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
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
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def analyze_rows(
    rows: list[dict[str, str]],
    *,
    text_col: str,
    id_col: str | None,
    classifier: HfHsdClassifierRuntime,
    batch_size: int,
    protect_threshold: float,
    limit: int | None,
) -> list[dict[str, object]]:
    selected_rows = rows[:limit] if limit is not None else rows
    mask_token = classifier._tokenizer.mask_token or "[MASK]"
    output: list[dict[str, object]] = []
    for row_index, row in enumerate(selected_rows, start=1):
        row_id = str(row.get(id_col or "", "") or row_index)
        text = str(row.get(text_col, "") or "")
        tokens = list(iter_tokens(text))
        if not tokens:
            continue
        baseline_score = classifier._scores([text])[0]
        masked_scores: list[float] = []
        masked_texts = [masked_text(text, token, mask_token) for token in tokens]
        for offset in range(0, len(masked_texts), batch_size):
            masked_scores.extend(
                classifier._scores(masked_texts[offset : offset + batch_size])
            )
        predicted_hate = bool(baseline_score >= classifier.threshold)
        for token, masked_score in zip(tokens, masked_scores, strict=True):
            delta = float(baseline_score - masked_score)
            abs_delta = abs(delta)
            output.append(
                {
                    "row_index": row_index,
                    "row_id": row_id,
                    "token_index": token.index,
                    "token": token.text,
                    "start": token.start,
                    "end": token.end,
                    "baseline_hate_score": round(float(baseline_score), 6),
                    "masked_hate_score": round(float(masked_score), 6),
                    "delta_hate_score": round(delta, 6),
                    "abs_delta_hate_score": round(abs_delta, 6),
                    "predicted_hate": int(predicted_hate),
                    "protect_hsd_token": int(abs_delta >= protect_threshold),
                }
            )
    output.sort(
        key=lambda item: (
            int(item["row_index"]),
            -float(item["abs_delta_hate_score"]),
            int(item["token_index"]),
        )
    )
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute token occlusion importance for the local HSD classifier.",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--text-col", default="text")
    parser.add_argument("--id-col")
    parser.add_argument("--model-path", default=DEFAULT_HF_HSD_MODEL_PATH)
    parser.add_argument("--threshold", type=float, default=DEFAULT_HF_HSD_THRESHOLD)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--max-length", type=int, default=DEFAULT_HF_HSD_MAX_LENGTH)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--protect-threshold",
        type=float,
        default=0.03,
        help="Mark tokens with abs(delta hate probability) at or above this value.",
    )
    parser.add_argument("--limit", type=int)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows, _fieldnames = read_rows(args.input)
    classifier = HfHsdClassifierRuntime(
        model_path=args.model_path,
        threshold=args.threshold,
        device=args.device,
        max_length=args.max_length,
    )
    output_rows = analyze_rows(
        rows,
        text_col=args.text_col,
        id_col=args.id_col,
        classifier=classifier,
        batch_size=args.batch_size,
        protect_threshold=args.protect_threshold,
        limit=args.limit,
    )
    write_rows(args.output, output_rows)
    protected = sum(int(row["protect_hsd_token"]) for row in output_rows)
    print(
        {
            "rows": len(rows) if args.limit is None else min(args.limit, len(rows)),
            "token_rows": len(output_rows),
            "protected_tokens": protected,
            "output": str(args.output),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
