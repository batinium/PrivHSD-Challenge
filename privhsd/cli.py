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
from .cue_checks import CueCheckError, run_cue_checks
from .datasets import (
    add_prepare_dynahate_parser,
    add_prepare_recommended_parser,
    prepare_dynahate,
    prepare_recommended_datasets,
)
from .dataset_profile import DatasetProfileError, profile_dataset
from .dpmlm_spike import (
    DEFAULT_EPSILONS,
    DEFAULT_SAMPLE_SIZE as DEFAULT_DPMLM_SAMPLE_SIZE,
    DpmlmSpikeError,
    run_dpmlm_spike,
)
from .dpmlm_candidates import (
    DEFAULT_BATCH_SIZE as DEFAULT_DPMLM_BATCH_SIZE,
    DEFAULT_EPSILON as DEFAULT_DPMLM_CANDIDATE_EPSILON,
    DEFAULT_MAX_LENGTH_DRIFT as DEFAULT_DPMLM_MAX_LENGTH_DRIFT,
    DEFAULT_MAX_REWRITE_TOKENS,
    DEFAULT_MIN_ELIGIBLE_SCORE,
    DEFAULT_MIN_CHARACTER_RETENTION,
    DEFAULT_MODEL as DEFAULT_DPMLM_MODEL,
    DEFAULT_SAMPLE_SIZE as DEFAULT_DPMLM_CANDIDATE_SAMPLE_SIZE,
    DpmlmCandidateError,
    run_dpmlm_candidates,
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
from .lm_context_benchmark import (
    DEFAULT_ENDPOINT as DEFAULT_LM_CONTEXT_ENDPOINT,
    DEFAULT_MAX_TOKENS as DEFAULT_LM_CONTEXT_MAX_TOKENS,
    DEFAULT_MODES as DEFAULT_LM_CONTEXT_MODES,
    DEFAULT_SAMPLE_SIZE as DEFAULT_LM_CONTEXT_SAMPLE_SIZE,
    DEFAULT_TIMEOUT as DEFAULT_LM_CONTEXT_TIMEOUT,
    LmContextBenchmarkError,
    run_lm_context_benchmark,
)
from .metadata_leakage import MetadataLeakageError, scan_metadata_leakage
from .presidio_compare import PresidioCompareError, run_presidio_comparison
from .presidio_augment import PresidioAugmentError
from .rerank import RerankError, run_candidate_reranking
from .source_report import SourceReportError, run_source_regression_report
from .submission import SubmissionError, create_submission, validate_submission
from .token_actions import (
    DEFAULT_MODEL_PATH as DEFAULT_TOKEN_ACTION_MODEL_PATH,
    DEFAULT_REPORT_PATH as DEFAULT_TOKEN_ACTION_REPORT_PATH,
    TokenActionError,
    train_token_action_tagger,
)
from .utility_benchmark import BenchmarkError, run_utility_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="privhsd")
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile = subparsers.add_parser(
        "profile-dataset",
        help="Safely inspect an incoming CSV without printing raw text examples.",
    )
    profile.add_argument("--input", type=Path, required=True)
    profile.add_argument("--output", type=Path)
    profile.add_argument("--text-col")
    profile.add_argument("--id-col")
    profile.add_argument("--label-col")
    profile.add_argument("--source-col")
    profile.add_argument("--split-col")
    profile.add_argument("--top-k", type=int, default=20)

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
        "--presidio-augment",
        action="store_true",
        help="Add filtered optional Presidio PERSON/LOCATION/DATE spans.",
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
    rerank.add_argument(
        "--presidio-augment",
        action="store_true",
        help="Add a filtered Presidio candidate when optional dependencies exist.",
    )
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

    dpmlm_candidates = subparsers.add_parser(
        "generate-dpmlm-candidates",
        help="Generate protected-token DPMLM rewrite candidates for reranking only.",
    )
    dpmlm_candidates.add_argument("--input", type=Path, required=True)
    dpmlm_candidates.add_argument("--output", type=Path, required=True)
    dpmlm_candidates.add_argument("--text-col", required=True)
    dpmlm_candidates.add_argument("--id-col")
    dpmlm_candidates.add_argument("--candidate-col", default="dpmlm_candidate")
    dpmlm_candidates.add_argument("--report", type=Path)
    dpmlm_candidates.add_argument("--model", default=DEFAULT_DPMLM_MODEL)
    dpmlm_candidates.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_DPMLM_CANDIDATE_SAMPLE_SIZE,
    )
    dpmlm_candidates.add_argument(
        "--epsilon",
        type=float,
        default=DEFAULT_DPMLM_CANDIDATE_EPSILON,
    )
    dpmlm_candidates.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_DPMLM_BATCH_SIZE,
    )
    dpmlm_candidates.add_argument(
        "--max-rewrite-tokens",
        type=int,
        default=DEFAULT_MAX_REWRITE_TOKENS,
    )
    dpmlm_candidates.add_argument(
        "--min-eligible-score",
        type=int,
        default=DEFAULT_MIN_ELIGIBLE_SCORE,
        help=(
            "Minimum protected-token risk score for DPMLM rewrite eligibility. "
            "Higher values rewrite fewer, riskier tokens."
        ),
    )
    dpmlm_candidates.add_argument("--random-seed", type=int, default=0)
    dpmlm_candidates.add_argument("--min-target-retention", type=float, default=1.0)
    dpmlm_candidates.add_argument("--min-utility-retention", type=float, default=1.0)
    dpmlm_candidates.add_argument(
        "--min-character-retention",
        type=float,
        default=DEFAULT_MIN_CHARACTER_RETENTION,
    )
    dpmlm_candidates.add_argument(
        "--max-length-drift",
        type=float,
        default=DEFAULT_DPMLM_MAX_LENGTH_DRIFT,
    )
    dpmlm_candidates.add_argument("--cue-retention-threshold", type=float, default=1.0)

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
    create_submission_parser.add_argument(
        "--presidio-augment",
        action="store_true",
        help="Add filtered optional Presidio PERSON/LOCATION/DATE spans.",
    )
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

    cue_checks = subparsers.add_parser(
        "check-hsd-cues",
        help="Check conservative HSD target/action/negation cue retention.",
    )
    cue_checks.add_argument("--input", type=Path, required=True)
    cue_checks.add_argument("--text-col", required=True)
    cue_checks.add_argument("--privatized-col", default="privatized_text")
    cue_checks.add_argument("--id-col")
    cue_checks.add_argument("--output", type=Path)
    cue_checks.add_argument("--retention-threshold", type=float, default=1.0)

    source_report = subparsers.add_parser(
        "source-regression-report",
        help="Compare original/protected CSVs by source-aware slices.",
    )
    source_report.add_argument("--original", type=Path, required=True)
    source_report.add_argument("--protected", type=Path, required=True)
    source_report.add_argument("--original-text-col", required=True)
    source_report.add_argument("--protected-text-col", required=True)
    source_report.add_argument("--id-col")
    source_report.add_argument(
        "--group-col",
        dest="group_cols",
        action="append",
        default=[],
        help="Original CSV column to group by. Repeat for source-aware slices.",
    )
    source_report.add_argument("--source-col", default="source")
    source_report.add_argument("--label-col", default="label")
    source_report.add_argument("--rationale-col", default="rationale_spans")
    source_report.add_argument("--output", type=Path)

    lm_context = subparsers.add_parser(
        "benchmark-lm-context",
        help="Benchmark a local LM Studio context-labeler on stratified rows.",
    )
    lm_context.add_argument("--input", type=Path, required=True)
    lm_context.add_argument("--text-col", required=True)
    lm_context.add_argument("--id-col")
    lm_context.add_argument("--source-col", default="source")
    lm_context.add_argument("--label-col", default="label")
    lm_context.add_argument("--endpoint", default=DEFAULT_LM_CONTEXT_ENDPOINT)
    lm_context.add_argument("--model", required=True)
    lm_context.add_argument("--sample-size", type=int, default=DEFAULT_LM_CONTEXT_SAMPLE_SIZE)
    lm_context.add_argument("--output", type=Path)
    lm_context.add_argument(
        "--mode",
        dest="modes",
        action="append",
        choices=list(DEFAULT_LM_CONTEXT_MODES),
        help="Output format to try. Repeat to override the default mode order.",
    )
    lm_context.add_argument("--timeout", type=float, default=DEFAULT_LM_CONTEXT_TIMEOUT)
    lm_context.add_argument("--max-tokens", type=int, default=DEFAULT_LM_CONTEXT_MAX_TOKENS)

    metadata_leakage = subparsers.add_parser(
        "check-metadata-leakage",
        help="Check whether metadata values such as id/author appear in text columns.",
    )
    metadata_leakage.add_argument("--input", type=Path, required=True)
    metadata_leakage.add_argument(
        "--text-col",
        dest="text_cols",
        action="append",
        required=True,
        help="Text column to scan. Repeat for original and privatized columns.",
    )
    metadata_leakage.add_argument(
        "--metadata-col",
        dest="metadata_cols",
        action="append",
        help="Metadata value column to search for. Defaults to present id/author columns.",
    )
    metadata_leakage.add_argument("--id-col")
    metadata_leakage.add_argument("--output", type=Path)
    metadata_leakage.add_argument("--min-value-length", type=int, default=3)
    metadata_leakage.add_argument(
        "--no-normalized",
        action="store_true",
        help="Disable alphanumeric-normalized matching.",
    )

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
    predict_classifier_parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL_PATH,
    )
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

    token_actions = subparsers.add_parser(
        "train-token-action-tagger",
        help="Train a weakly supervised token-action tagger from local rules.",
    )
    token_actions.add_argument("--input", type=Path, required=True)
    token_actions.add_argument("--text-col", required=True)
    token_actions.add_argument("--id-col")
    token_actions.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_TOKEN_ACTION_MODEL_PATH,
    )
    token_actions.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_TOKEN_ACTION_REPORT_PATH,
    )
    token_actions.add_argument("--sample-size", type=int, default=5000)
    token_actions.add_argument("--test-size", type=float, default=0.25)
    token_actions.add_argument("--random-state", type=int, default=13)

    add_prepare_dynahate_parser(subparsers)
    add_prepare_recommended_parser(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(raw_argv)
    try:
        if args.command == "profile-dataset":
            result = profile_dataset(
                args.input,
                output_path=args.output,
                text_col=args.text_col,
                id_col=args.id_col,
                label_col=args.label_col,
                source_col=args.source_col,
                split_col=args.split_col,
                top_k=args.top_k,
            )
        elif args.command == "anonymize":
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
                presidio_augment=args.presidio_augment,
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
                presidio_augment=args.presidio_augment,
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
        elif args.command == "generate-dpmlm-candidates":
            result = run_dpmlm_candidates(
                args.input,
                args.output,
                text_col=args.text_col,
                id_col=args.id_col,
                candidate_col=args.candidate_col,
                report_path=args.report,
                model_name=args.model,
                sample_size=args.sample_size,
                epsilon=args.epsilon,
                batch_size=args.batch_size,
                max_rewrite_tokens=args.max_rewrite_tokens,
                min_eligible_score=args.min_eligible_score,
                random_seed=args.random_seed,
                min_target_retention=args.min_target_retention,
                min_utility_retention=args.min_utility_retention,
                min_character_retention=args.min_character_retention,
                max_length_drift=args.max_length_drift,
                cue_retention_threshold=args.cue_retention_threshold,
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
                presidio_augment=args.presidio_augment,
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
        elif args.command == "check-hsd-cues":
            result = run_cue_checks(
                args.input,
                text_col=args.text_col,
                privatized_col=args.privatized_col,
                id_col=args.id_col,
                output_path=args.output,
                retention_threshold=args.retention_threshold,
            )
        elif args.command == "source-regression-report":
            result = run_source_regression_report(
                args.original,
                args.protected,
                original_text_col=args.original_text_col,
                protected_text_col=args.protected_text_col,
                id_col=args.id_col,
                group_cols=args.group_cols or None,
                source_col=args.source_col,
                label_col=args.label_col,
                rationale_col=args.rationale_col,
                output_path=args.output,
            )
        elif args.command == "benchmark-lm-context":
            result = run_lm_context_benchmark(
                args.input,
                text_col=args.text_col,
                id_col=args.id_col,
                source_col=args.source_col,
                label_col=args.label_col,
                endpoint=args.endpoint,
                model=args.model,
                sample_size=args.sample_size,
                output_path=args.output,
                modes=args.modes,
                timeout=args.timeout,
                max_tokens=args.max_tokens,
            )
        elif args.command == "check-metadata-leakage":
            result = scan_metadata_leakage(
                args.input,
                text_cols=args.text_cols,
                metadata_cols=args.metadata_cols,
                id_col=args.id_col,
                output_path=args.output,
                min_value_length=args.min_value_length,
                normalized=not args.no_normalized,
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
        elif args.command == "train-token-action-tagger":
            result = train_token_action_tagger(
                args.input,
                text_col=args.text_col,
                id_col=args.id_col,
                model_path=args.model,
                output_path=args.output,
                sample_size=args.sample_size,
                test_size=args.test_size,
                random_state=args.random_state,
            )
        elif args.command == "prepare-dynahate":
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
        elif args.command == "prepare-recommended-datasets":
            result = prepare_recommended_datasets(
                output_dir=args.output_dir,
                raw_dir=args.raw_dir,
                merged_output=args.merged_output,
                datasets=args.datasets,
                download=not args.no_download,
                measuring_max_rows=args.measuring_max_rows,
                measuring_page_size=args.measuring_page_size,
                measuring_request_delay=args.measuring_request_delay,
            )
        else:  # pragma: no cover - argparse enforces command choices
            raise ValueError(f"unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (
        AblationError,
        AuthorRiskError,
        BenchmarkError,
        ClassifierError,
        CsvPipelineError,
        CueCheckError,
        DatasetProfileError,
        DpmlmCandidateError,
        DpmlmSpikeError,
        HfUtilityError,
        LmContextBenchmarkError,
        LocalLlmError,
        MetadataLeakageError,
        OSError,
        PresidioAugmentError,
        PresidioCompareError,
        RerankError,
        SourceReportError,
        SubmissionError,
        TokenActionError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
