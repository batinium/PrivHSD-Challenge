"""Command-line interface for the PrivHSD pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ablation import AblationError, run_ablation
from .author_risk import AuthorRiskError, run_author_risk_evaluation
from .classifier import (
    DEFAULT_EVALUATE_REPORT_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_PREDICTION_PATH,
    DEFAULT_TRAIN_REPORT_PATH,
    ClassifierError,
    evaluate_classifier,
    predict_classifier,
    train_classifier,
)
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
        "--style-scrub",
        action="store_true",
        help="Normalize style-bearing author cues after privacy masking.",
    )
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

    ablate = subparsers.add_parser(
        "ablate",
        help="Compare deterministic privatization variants on one CSV.",
    )
    ablate.add_argument("--input", type=Path, required=True)
    ablate.add_argument("--text-col", required=True)
    ablate.add_argument("--id-col")
    ablate.add_argument("--label-col")
    ablate.add_argument("--output", type=Path)
    ablate.add_argument("--output-dir", type=Path)
    ablate.add_argument("--test-size", type=float, default=0.25)
    ablate.add_argument("--random-state", type=int, default=13)

    author_risk = subparsers.add_parser(
        "evaluate-author-risk",
        help="Train a local author adversary and compare original vs privatized text.",
    )
    author_risk.add_argument("--input", type=Path, required=True)
    author_risk.add_argument("--text-col", required=True)
    author_risk.add_argument("--privatized-col", default="privatized_text")
    author_risk.add_argument("--author-col", default="author")
    author_risk.add_argument("--id-col")
    author_risk.add_argument("--label-col")
    author_risk.add_argument("--output", type=Path)
    author_risk.add_argument("--test-size", type=float, default=0.25)
    author_risk.add_argument("--random-state", type=int, default=13)

    train_classifier_parser = subparsers.add_parser(
        "train-classifier",
        help="Train a local baseline hate-speech classifier on a labeled CSV.",
    )
    train_classifier_parser.add_argument("--input", type=Path, required=True)
    train_classifier_parser.add_argument("--text-col", required=True)
    train_classifier_parser.add_argument("--label-col", default="label")
    train_classifier_parser.add_argument("--id-col")
    train_classifier_parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    train_classifier_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_TRAIN_REPORT_PATH,
    )
    train_classifier_parser.add_argument("--test-size", type=float, default=0.25)
    train_classifier_parser.add_argument("--random-state", type=int, default=13)

    evaluate_classifier_parser = subparsers.add_parser(
        "evaluate-classifier",
        help="Evaluate a trained local baseline classifier on a labeled CSV.",
    )
    evaluate_classifier_parser.add_argument("--input", type=Path, required=True)
    evaluate_classifier_parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    evaluate_classifier_parser.add_argument("--text-col", required=True)
    evaluate_classifier_parser.add_argument("--label-col", default="label")
    evaluate_classifier_parser.add_argument("--id-col")
    evaluate_classifier_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_EVALUATE_REPORT_PATH,
    )

    predict_classifier_parser = subparsers.add_parser(
        "predict-classifier",
        help="Write row-preserving predictions from a trained local classifier.",
    )
    predict_classifier_parser.add_argument("--input", type=Path, required=True)
    predict_classifier_parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    predict_classifier_parser.add_argument("--text-col", required=True)
    predict_classifier_parser.add_argument("--id-col")
    predict_classifier_parser.add_argument("--label-col", default="label")
    predict_classifier_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_PREDICTION_PATH,
    )
    predict_classifier_parser.add_argument("--prediction-col", default="predicted_label")
    predict_classifier_parser.add_argument(
        "--confidence-col",
        default="predicted_confidence",
    )

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
                style_scrub=args.style_scrub,
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
        elif args.command == "ablate":
            result = run_ablation(
                args.input,
                text_col=args.text_col,
                id_col=args.id_col,
                label_col=args.label_col,
                output_path=args.output,
                output_dir=args.output_dir,
                test_size=args.test_size,
                random_state=args.random_state,
            )
        elif args.command == "evaluate-author-risk":
            result = run_author_risk_evaluation(
                args.input,
                text_col=args.text_col,
                privatized_col=args.privatized_col,
                author_col=args.author_col,
                id_col=args.id_col,
                label_col=args.label_col,
                output_path=args.output,
                test_size=args.test_size,
                random_state=args.random_state,
            )
        elif args.command == "train-classifier":
            result = train_classifier(
                args.input,
                text_col=args.text_col,
                label_col=args.label_col,
                id_col=args.id_col,
                model_path=args.model,
                output_path=args.output,
                test_size=args.test_size,
                random_state=args.random_state,
            )
        elif args.command == "evaluate-classifier":
            result = evaluate_classifier(
                args.input,
                model_path=args.model,
                text_col=args.text_col,
                label_col=args.label_col,
                id_col=args.id_col,
                output_path=args.output,
            )
        elif args.command == "predict-classifier":
            result = predict_classifier(
                args.input,
                model_path=args.model,
                text_col=args.text_col,
                id_col=args.id_col,
                label_col=args.label_col,
                output_path=args.output,
                prediction_col=args.prediction_col,
                confidence_col=args.confidence_col,
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
    except (
        AblationError,
        AuthorRiskError,
        BenchmarkError,
        ClassifierError,
        CsvPipelineError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
