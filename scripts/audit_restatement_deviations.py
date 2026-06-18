#!/usr/bin/env python3
"""Audit source-vs-restatement drift for backend review CSVs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from contextsafe_hsd.restatement_audit import run_restatement_deviation_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit source-vs-restatement drift in an annotated CSV.",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--text-col", default="text")
    parser.add_argument(
        "--restatement-col",
        default="qwen35_descriptive_restatement",
        help="Column containing the generated restatement.",
    )
    parser.add_argument("--id-col")
    parser.add_argument("--label-col", default="hs")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = run_restatement_deviation_audit(
        args.input,
        args.output,
        summary_path=args.summary,
        text_col=args.text_col,
        restatement_col=args.restatement_col,
        id_col=args.id_col,
        label_col=args.label_col,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
