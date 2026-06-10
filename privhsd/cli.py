"""Command-line interface for the PrivHSD pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .csv_pipeline import CsvPipelineError, evaluate_csv, process_csv
from .datasets import add_prepare_dynahate_parser, prepare_dynahate
from .utility_benchmark import BenchmarkError, run_utility_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="privhsd")
    subparsers = parser.add_subparsers(dest="command", required=True)

    anonymize = subparsers.add_parser(
        "anonymize",
        help="Privatize a CSV text column and write a challenge-ready CSV.",
    )
    anonymize.add_argument("--input", type=Path, required=True)
    anonymize.add_argument("--output", type=Path, required=True)
    anonymize.add_argument("--text-col", required=True)
    anonymize.add_argument("--id-col")
    anonymize.add_argument("--output-col", default="privatized_text")
    anonymize.add_argument("--replace-text", action="store_true")
    anonymize.add_argument("--audit", type=Path)
    anonymize.add_argument(
        "--mode",
        choices=["utility", "balanced", "privacy"],
        default="balanced",
    )
    target_group = anonymize.add_mutually_exclusive_group()
    target_group.add_argument("--generalize-targets", action="store_true")
    target_group.add_argument("--preserve-targets", action="store_true")

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Compute local proxy metrics for an already-privatized CSV.",
    )
    evaluate.add_argument("--input", type=Path, required=True)
    evaluate.add_argument("--text-col", required=True)
    evaluate.add_argument("--privatized-col", default="privatized_text")
    evaluate.add_argument("--output", type=Path)

    benchmark = subparsers.add_parser(
        "benchmark-utility",
        help="Run a local classifier utility-delta benchmark.",
    )
    benchmark.add_argument("--input", type=Path, required=True)
    benchmark.add_argument("--text-col", required=True)
    benchmark.add_argument("--privatized-col", default="privatized_text")
    benchmark.add_argument("--label-col", default="label")
    benchmark.add_argument("--id-col")
    benchmark.add_argument("--output", type=Path)
    benchmark.add_argument("--test-size", type=float, default=0.25)
    benchmark.add_argument("--random-state", type=int, default=13)

    add_prepare_dynahate_parser(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "anonymize":
            generalize_targets = None
            if args.generalize_targets:
                generalize_targets = True
            elif args.preserve_targets:
                generalize_targets = False
            result = process_csv(
                args.input,
                args.output,
                text_col=args.text_col,
                id_col=args.id_col,
                output_col=args.output_col,
                replace_text=args.replace_text,
                audit_path=args.audit,
                mode=args.mode,
                generalize_targets=generalize_targets,
            )
        elif args.command == "evaluate":
            result = evaluate_csv(
                args.input,
                text_col=args.text_col,
                privatized_col=args.privatized_col,
                output_path=args.output,
            )
        elif args.command == "benchmark-utility":
            result = run_utility_benchmark(
                args.input,
                text_col=args.text_col,
                privatized_col=args.privatized_col,
                label_col=args.label_col,
                id_col=args.id_col,
                output_path=args.output,
                test_size=args.test_size,
                random_state=args.random_state,
            )
        else:
            count = prepare_dynahate(
                raw_path=args.raw,
                output_path=args.output,
                download=args.download,
                url=args.url,
            )
            result = {
                "output": str(args.output),
                "raw": str(args.raw),
                "download": args.download,
                "row_count": count,
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BenchmarkError, CsvPipelineError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
