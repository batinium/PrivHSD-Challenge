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
from .dpmlm_spike import (
    DEFAULT_EPSILONS,
    DEFAULT_SAMPLE_SIZE as DEFAULT_DPMLM_SAMPLE_SIZE,
    DpmlmSpikeError,
    run_dpmlm_spike,
)
from .hf_utility import (
    DEFAULT_DROP_THRESHOLD,
    DEFAULT_SAMPLE_SIZE,
    HfUtilityError,
    run_hf_utility_evaluation,
    write_model_registry,
)
from .local_llm import (
    DEFAULT_ENDPOINT as DEFAULT_LLM_ENDPOINT,
    DEFAULT_MODEL as DEFAULT_LLM_MODEL,
    DEFAULT_SAMPLE_SIZE as DEFAULT_LLM_SAMPLE_SIZE,
    LocalLlmError,
    run_local_llm_candidates,
)
from .presidio_compare import PresidioCompareError, run_presidio_comparison
from .rerank import RerankError, run_candidate_reranking
from .submission import SubmissionError, create_submission, validate_submission
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

    hf_registry = subparsers.add_parser(
        "hf-model-registry",
        help="Write the approved optional Hugging Face utility model registry.",
    )
    hf_registry.add_argument("--output", type=Path)

    hf_utility = subparsers.add_parser(
        "evaluate-hf-utility",
        help="Run optional Hugging Face HSD/toxicity utility probes.",
    )
    hf_utility.add_argument("--input", type=Path, required=True)
    hf_utility.add_argument("--text-col", required=True)
    hf_utility.add_argument("--privatized-col", default="privatized_text")
    hf_utility.add_argument("--id-col")
    hf_utility.add_argument("--label-col")
    hf_utility.add_argument("--output", type=Path)
    hf_utility.add_argument(
        "--model",
        dest="models",
        action="append",
        help="Approved HF model ID. Repeat to evaluate multiple models.",
    )
    hf_utility.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    hf_utility.add_argument("--device", default="cpu")
    hf_utility.add_argument("--batch-size", type=int, default=8)
    hf_utility.add_argument(
        "--drop-threshold",
        type=float,
        default=DEFAULT_DROP_THRESHOLD,
    )
    hf_utility.add_argument("--decision-threshold", type=float, default=0.5)

    rerank = subparsers.add_parser(
        "rerank-candidates",
        help="Generate row-local privatization candidates and choose the best tradeoff.",
    )
    rerank.add_argument("--input", type=Path, required=True)
    rerank.add_argument("--output", type=Path, required=True)
    rerank.add_argument("--text-col", required=True)
    rerank.add_argument("--id-col")
    rerank.add_argument("--output-col", default="privatized_text")
    rerank.add_argument("--replace-text", action="store_true")
    rerank.add_argument("--author-col")
    rerank.add_argument(
        "--candidate-col",
        dest="candidate_cols",
        action="append",
        default=[],
        help="Existing column containing an optional rewrite candidate. Repeatable.",
    )
    rerank.add_argument("--audit", type=Path)

    dpmlm = subparsers.add_parser(
        "dpmlm-spike",
        help="Run a bounded protected-cue DPMLM rewrite spike or blocker report.",
    )
    dpmlm.add_argument("--input", type=Path, required=True)
    dpmlm.add_argument("--text-col", required=True)
    dpmlm.add_argument("--id-col")
    dpmlm.add_argument("--privatized-col")
    dpmlm.add_argument("--output", type=Path)
    dpmlm.add_argument("--sample-size", type=int, default=DEFAULT_DPMLM_SAMPLE_SIZE)
    dpmlm.add_argument(
        "--epsilon",
        dest="epsilons",
        action="append",
        type=float,
        help=(
            "Privacy epsilon to test. Repeatable. Defaults to "
            + ", ".join(str(value) for value in DEFAULT_EPSILONS)
            + "."
        ),
    )
    dpmlm.add_argument("--backend", default="auto")
    dpmlm.add_argument("--random-seed", type=int, default=0)

    create_submission_parser = subparsers.add_parser(
        "create-submission",
        help="Create an exact-format upload CSV by privatizing text columns in place.",
    )
    create_submission_parser.add_argument("--input", type=Path, required=True)
    create_submission_parser.add_argument("--output", type=Path, required=True)
    create_submission_parser.add_argument(
        "--text-col",
        dest="text_cols",
        action="append",
        required=True,
        help="Text column to privatize in place. Repeatable.",
    )
    create_submission_parser.add_argument("--id-col")
    create_submission_parser.add_argument("--manifest", type=Path)
    create_submission_parser.add_argument("--replace-text", action="store_true")
    create_submission_parser.add_argument(
        "--mode",
        choices=["utility", "balanced", "privacy"],
        default="balanced",
    )
    create_submission_parser.add_argument("--style-scrub", action="store_true")
    create_submission_targets = create_submission_parser.add_mutually_exclusive_group()
    create_submission_targets.add_argument("--generalize-targets", action="store_true")
    create_submission_targets.add_argument("--preserve-targets", action="store_true")

    validate_submission_parser = subparsers.add_parser(
        "validate-submission",
        help="Validate row/order/ID/metadata shape for an exact-format upload CSV.",
    )
    validate_submission_parser.add_argument("--source", type=Path, required=True)
    validate_submission_parser.add_argument("--submission", type=Path, required=True)
    validate_submission_parser.add_argument(
        "--text-col",
        dest="text_cols",
        action="append",
        required=True,
        help="Text column privatized in place. Repeatable.",
    )
    validate_submission_parser.add_argument("--id-col")
    validate_submission_parser.add_argument("--output", type=Path)
    validate_submission_parser.add_argument(
        "--allow-helper-columns",
        action="store_true",
    )

    presidio = subparsers.add_parser(
        "compare-presidio",
        help="Run optional Presidio detector comparison as a baseline report.",
    )
    presidio.add_argument("--input", type=Path, required=True)
    presidio.add_argument("--text-col", required=True)
    presidio.add_argument("--id-col")
    presidio.add_argument("--output", type=Path)
    presidio.add_argument("--sample-size", type=int, default=100)
    presidio.add_argument("--language", default="en")

    llm_candidates = subparsers.add_parser(
        "generate-llm-candidates",
        help="Generate local LLM rewrite candidates for reranking only.",
    )
    llm_candidates.add_argument("--input", type=Path, required=True)
    llm_candidates.add_argument("--output", type=Path, required=True)
    llm_candidates.add_argument("--text-col", required=True)
    llm_candidates.add_argument("--id-col")
    llm_candidates.add_argument("--candidate-col", default="llm_candidate")
    llm_candidates.add_argument("--report", type=Path)
    llm_candidates.add_argument("--endpoint", default=DEFAULT_LLM_ENDPOINT)
    llm_candidates.add_argument("--model", default=DEFAULT_LLM_MODEL)
    llm_candidates.add_argument("--sample-size", type=int, default=DEFAULT_LLM_SAMPLE_SIZE)
    llm_candidates.add_argument("--timeout", type=float, default=10.0)
    llm_candidates.add_argument("--min-target-retention", type=float, default=1.0)
    llm_candidates.add_argument("--min-utility-retention", type=float, default=1.0)
    llm_candidates.add_argument("--max-length-drift", type=float, default=0.6)

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
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(raw_argv)
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
        elif args.command == "hf-model-registry":
            result = write_model_registry(args.output)
        elif args.command == "evaluate-hf-utility":
            result = run_hf_utility_evaluation(
                args.input,
                text_col=args.text_col,
                privatized_col=args.privatized_col,
                id_col=args.id_col,
                label_col=args.label_col,
                output_path=args.output,
                model_ids=args.models,
                sample_size=args.sample_size,
                device=args.device,
                batch_size=args.batch_size,
                drop_threshold=args.drop_threshold,
                decision_threshold=args.decision_threshold,
            )
        elif args.command == "rerank-candidates":
            result = run_candidate_reranking(
                args.input,
                args.output,
                text_col=args.text_col,
                id_col=args.id_col,
                output_col=args.output_col,
                replace_text=args.replace_text,
                author_col=args.author_col,
                candidate_cols=args.candidate_cols,
                audit_path=args.audit,
            )
        elif args.command == "dpmlm-spike":
            result = run_dpmlm_spike(
                args.input,
                text_col=args.text_col,
                id_col=args.id_col,
                privatized_col=args.privatized_col,
                output_path=args.output,
                sample_size=args.sample_size,
                epsilons=args.epsilons,
                backend=args.backend,
                random_seed=args.random_seed,
            )
        elif args.command == "create-submission":
            generalize_targets = None
            if args.generalize_targets:
                generalize_targets = True
            elif args.preserve_targets:
                generalize_targets = False
            result = create_submission(
                args.input,
                args.output,
                text_cols=args.text_cols,
                id_col=args.id_col,
                manifest_path=args.manifest,
                command=["privhsd", *raw_argv],
                mode=args.mode,
                generalize_targets=generalize_targets,
                style_scrub=args.style_scrub,
                replace_text=args.replace_text,
            )
        elif args.command == "validate-submission":
            result = validate_submission(
                args.source,
                args.submission,
                text_cols=args.text_cols,
                id_col=args.id_col,
                output_path=args.output,
                allow_helper_columns=args.allow_helper_columns,
            )
        elif args.command == "compare-presidio":
            result = run_presidio_comparison(
                args.input,
                text_col=args.text_col,
                id_col=args.id_col,
                output_path=args.output,
                sample_size=args.sample_size,
                language=args.language,
            )
        elif args.command == "generate-llm-candidates":
            result = run_local_llm_candidates(
                args.input,
                args.output,
                text_col=args.text_col,
                id_col=args.id_col,
                candidate_col=args.candidate_col,
                report_path=args.report,
                endpoint=args.endpoint,
                model=args.model,
                sample_size=args.sample_size,
                timeout=args.timeout,
                min_target_retention=args.min_target_retention,
                min_utility_retention=args.min_utility_retention,
                max_length_drift=args.max_length_drift,
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
        DpmlmSpikeError,
        HfUtilityError,
        LocalLlmError,
        OSError,
        PresidioCompareError,
        RerankError,
        SubmissionError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
