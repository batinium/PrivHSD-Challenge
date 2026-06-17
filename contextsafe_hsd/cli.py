"""Command-line interface for the final ContextSafe-HSD pipeline."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .dataset_profile import DatasetProfileError, profile_dataset
from .mini_verifier import (
    DEFAULT_ENDPOINT as MINI_VERIFIER_DEFAULT_ENDPOINT,
    DEFAULT_MAIN_MODEL as MINI_VERIFIER_DEFAULT_MAIN_MODEL,
    DEFAULT_OUTPUT_DIR as MINI_VERIFIER_DEFAULT_OUTPUT_DIR,
    DEFAULT_RUN_DIR as MINI_VERIFIER_DEFAULT_RUN_DIR,
    DEFAULT_SOURCE_CSV as MINI_VERIFIER_DEFAULT_SOURCE_CSV,
    MiniVerifierError,
    run_verifier_eval,
)
from .models.hf_hsd_classifier_runtime import (
    DEFAULT_HF_HSD_BATCH_SIZE,
    DEFAULT_HF_HSD_MAX_LENGTH,
    DEFAULT_HF_HSD_MODEL_PATH,
    DEFAULT_HF_HSD_THRESHOLD,
)
from .simple_pipeline import SimplifiedPipelineError, run_final_csv_pipeline
from .submission import SubmissionError, validate_submission


def make_progress_printer():
    last_event = {"stage": None, "processed": -1, "timestamp": 0.0}

    def print_progress(event: dict[str, object]) -> None:
        stage = str(event.get("stage") or "unknown")
        processed = int(event.get("processed") or 0)
        total = int(event.get("total") or 0)
        now = time.monotonic()
        should_print = (
            stage != last_event["stage"]
            or processed == total
            or processed - int(last_event["processed"]) >= 50
            or now - float(last_event["timestamp"]) >= 10.0
        )
        if not should_print:
            return
        detail = str(event.get("detail") or "")
        suffix = f" {detail}" if detail else ""
        print(
            f"[progress] {stage} {processed}/{total}{suffix}",
            file=sys.stderr,
            flush=True,
        )
        last_event.update(stage=stage, processed=processed, timestamp=now)

    return print_progress


def add_author_group_masking_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--author-group-masking",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Mask detector-backed factual spans repeated across rows from the "
            "same author/user group after row-level sanitization. On by default."
        ),
    )
    parser.add_argument(
        "--enable-author-group-masking",
        dest="author_group_masking",
        action="store_true",
        help="Deprecated alias; author-group masking is on by default.",
    )
    parser.add_argument(
        "--author-group-col",
        help=(
            "Author/user grouping column for --enable-author-group-masking. "
            "Defaults to the first author/user-like column when omitted."
        ),
    )
    parser.add_argument("--author-group-min-repetitions", type=int, default=2)
    parser.add_argument("--author-group-min-author-rows", type=int, default=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextsafe-hsd",
        description=(
            "Protect exact-format HSD CSV files. The public path preserves the "
            "input schema and writes labels, diagnostics, and suggestions only "
            "to manifest/audit sidecars."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    protect = subparsers.add_parser(
        "protect",
        help="Protect a CSV while preserving row order, row count, and columns.",
        description=(
            "Run the final exact CSV pipeline: deterministic sanitization, "
            "Presidio/scrubadub PII Assist, cue-safe candidate selection, "
            "default HF sidecar classification, and optional local LLM audit "
            "extensions on cleaned text only."
        ),
    )
    protect.add_argument("--input", type=Path, required=True)
    protect.add_argument("--output", type=Path, required=True)
    protect.add_argument("--text-col", default="text")
    protect.add_argument("--id-col")
    protect.add_argument("--manifest", type=Path)
    protect.add_argument("--audit", type=Path)
    protect.add_argument(
        "--preset",
        choices=["exact", "audit"],
        default="exact",
        help="exact is the hand-in path; audit keeps the same CSV contract with deeper sidecars.",
    )
    protect.add_argument(
        "--llm-review",
        choices=["off", "local-llm"],
        default="off",
        help=(
            "Deprecated alias for --hsd-classifier local-llm when "
            "--hsd-classifier is omitted."
        ),
    )
    protect.add_argument(
        "--hsd-classifier",
        choices=["off", "hf", "hf-classifier", "local-llm"],
        help=(
            "Sidecar-only HSD classifier after sanitization. Defaults to hf "
            "for the fine-tuned local Transformers classifier; local-llm "
            "keeps GPT as the main classifier; off disables classification."
        ),
    )
    protect.add_argument(
        "--hf-hsd-model-path",
        default=DEFAULT_HF_HSD_MODEL_PATH,
        help="Local path or model id for --hsd-classifier hf.",
    )
    protect.add_argument(
        "--hf-hsd-threshold",
        type=float,
        default=DEFAULT_HF_HSD_THRESHOLD,
        help="Decision threshold for --hsd-classifier hf.",
    )
    protect.add_argument(
        "--hf-hsd-device",
        choices=["auto", "cpu", "cuda"],
        default="auto",
        help="Device for --hsd-classifier hf.",
    )
    protect.add_argument(
        "--hf-hsd-batch-size",
        type=int,
        default=DEFAULT_HF_HSD_BATCH_SIZE,
        help="Batch size for --hsd-classifier hf.",
    )
    protect.add_argument(
        "--hf-hsd-max-length",
        type=int,
        default=DEFAULT_HF_HSD_MAX_LENGTH,
        help="Tokenizer max length for --hsd-classifier hf.",
    )
    protect.add_argument(
        "--local-llm-endpoint",
        default="http://localhost:1234/v1/chat/completions",
        help="OpenAI-compatible local chat completions URL.",
    )
    protect.add_argument(
        "--local-llm-model",
        default="openai/gpt-oss-20b",
        help="Local LLM model identifier for sidecar-only HSD review.",
    )
    protect.add_argument("--local-llm-timeout-seconds", type=float, default=120.0)
    protect.add_argument("--local-llm-batch-size", type=int, default=10)
    protect.add_argument(
        "--llm-verifier",
        choices=["off", "local-llm"],
        default="off",
        help="Optional second-pass local LLM verifier on main positive labels.",
    )
    protect.add_argument(
        "--local-llm-verifier-model",
        help=(
            "Model identifier for --llm-verifier local-llm. Defaults to "
            "--local-llm-model when omitted."
        ),
    )
    protect.add_argument("--local-llm-verifier-timeout-seconds", type=float)
    protect.add_argument("--local-llm-verifier-batch-size", type=int)
    protect.add_argument(
        "--local-llm-verifier-prompt-style",
        choices=["current", "human-review-router"],
        default="current",
        help="Prompt style for the optional second-pass verifier.",
    )
    protect.add_argument(
        "--local-llm-verifier-reasoning-effort",
        help="Optional model-specific reasoning effort, for example 'minimal'.",
    )
    protect.add_argument(
        "--disable-local-llm-pii-suggestions",
        action="store_true",
        help="Disable advisory residual PII suggestions from local LLM review.",
    )
    protect.add_argument(
        "--require-llm-review",
        action="store_true",
        help="Fail if selected local LLM review cannot parse every row.",
    )
    protect.add_argument(
        "--progress",
        action="store_true",
        help="Print coarse raw-text-free pipeline progress to stderr.",
    )
    protect.add_argument(
        "--style-scrub",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Normalize author-identifying style markers while preserving HSD "
            "target/action/negation cues. On by default."
        ),
    )
    protect.add_argument(
        "--style-simplify-language",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "When style scrubbing is enabled, simplify a small deterministic "
            "set of high-register words and phrases. On by default."
        ),
    )
    add_author_group_masking_arguments(protect)

    validate = subparsers.add_parser(
        "validate-submission",
        help="Validate row/order/ID/metadata shape for an exact-format output CSV.",
    )
    validate.add_argument("--source", type=Path, required=True)
    validate.add_argument("--submission", type=Path, required=True)
    validate.add_argument(
        "--text-col",
        dest="text_cols",
        action="append",
        required=True,
        help="Text column privatized in place. Repeatable.",
    )
    validate.add_argument("--id-col")
    validate.add_argument("--output", type=Path)
    validate.add_argument("--allow-helper-columns", action="store_true")

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

    verifier_eval = subparsers.add_parser(
        "mini-verifier-eval",
        help="Run the 160-row local small-model HSD verifier/router evaluation.",
    )
    verifier_eval.add_argument(
        "--source-csv",
        type=Path,
        default=MINI_VERIFIER_DEFAULT_SOURCE_CSV,
    )
    verifier_eval.add_argument("--run-dir", type=Path, default=MINI_VERIFIER_DEFAULT_RUN_DIR)
    verifier_eval.add_argument(
        "--output-dir",
        type=Path,
        default=MINI_VERIFIER_DEFAULT_OUTPUT_DIR,
    )
    verifier_eval.add_argument("--endpoint", default=MINI_VERIFIER_DEFAULT_ENDPOINT)
    verifier_eval.add_argument("--main-model", default=MINI_VERIFIER_DEFAULT_MAIN_MODEL)
    verifier_eval.add_argument("--batch-size", type=int, default=10)
    verifier_eval.add_argument("--timeout-seconds", type=float, default=120.0)
    verifier_eval.add_argument("--candidate", action="append", dest="candidates", default=[])
    verifier_eval.add_argument("--shortlist-size", type=int, default=3)
    verifier_eval.add_argument("--rebuild-eval-set", action="store_true")
    verifier_eval.add_argument("--include-cost-floor", action="store_true")
    verifier_eval.add_argument(
        "--skip-uncensored-probe",
        action="store_true",
        help="Do not run the aggressive uncensored probe even if present.",
    )
    verifier_eval.add_argument("--min-screen-parse-success", type=float, default=0.95)
    verifier_eval.add_argument(
        "--progress",
        action="store_true",
        help="Print verifier evaluation progress to stderr.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(raw_argv)
    try:
        if args.command == "protect":
            hsd_classifier = (
                args.hsd_classifier.replace("-", "_")
                if args.hsd_classifier
                else (
                    "local_llm"
                    if args.llm_review.replace("-", "_") == "local_llm"
                    else "hf_classifier"
                )
            )
            if hsd_classifier == "hf":
                hsd_classifier = "hf_classifier"
            result = run_final_csv_pipeline(
                args.input,
                args.output,
                text_col=args.text_col,
                id_col=args.id_col,
                manifest_path=args.manifest,
                audit_path=args.audit,
                command=["contextsafe-hsd", *raw_argv],
                preset=args.preset,
                metric_depth="deep" if args.preset == "audit" else "fast",
                allow_model_download=False,
                audit_level="row" if args.preset == "audit" else "summary",
                llm_review=args.llm_review.replace("-", "_"),
                hsd_classification_backend=hsd_classifier,
                hf_hsd_model_path=args.hf_hsd_model_path,
                hf_hsd_threshold=args.hf_hsd_threshold,
                hf_hsd_device=args.hf_hsd_device,
                hf_hsd_batch_size=args.hf_hsd_batch_size,
                hf_hsd_max_length=args.hf_hsd_max_length,
                local_llm_endpoint=args.local_llm_endpoint,
                local_llm_model=args.local_llm_model,
                local_llm_timeout_seconds=args.local_llm_timeout_seconds,
                local_llm_batch_size=args.local_llm_batch_size,
                local_llm_enable_pii_suggestions=(
                    not args.disable_local_llm_pii_suggestions
                ),
                llm_verifier=args.llm_verifier.replace("-", "_"),
                local_llm_verifier_model=args.local_llm_verifier_model,
                local_llm_verifier_timeout_seconds=(
                    args.local_llm_verifier_timeout_seconds
                ),
                local_llm_verifier_batch_size=args.local_llm_verifier_batch_size,
                local_llm_verifier_prompt_style=(
                    args.local_llm_verifier_prompt_style.replace("-", "_")
                ),
                local_llm_verifier_reasoning_effort=(
                    args.local_llm_verifier_reasoning_effort
                ),
                require_hate_classification=args.require_llm_review,
                author_group_masking=args.author_group_masking,
                author_group_col=args.author_group_col,
                author_group_min_repetitions=args.author_group_min_repetitions,
                author_group_min_author_rows=args.author_group_min_author_rows,
                generalize_targets=False,
                style_scrub=args.style_scrub,
                style_simplify_language=args.style_simplify_language,
                progress_callback=make_progress_printer()
                if args.progress
                else None,
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
        elif args.command == "profile-dataset":
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
        elif args.command == "mini-verifier-eval":
            result = run_verifier_eval(
                source_csv=args.source_csv,
                run_dir=args.run_dir,
                output_dir=args.output_dir,
                endpoint=args.endpoint,
                main_model=args.main_model,
                batch_size=args.batch_size,
                timeout_seconds=args.timeout_seconds,
                candidates=args.candidates,
                shortlist_size=args.shortlist_size,
                rebuild_eval_set=args.rebuild_eval_set,
                include_uncensored_probe=not args.skip_uncensored_probe,
                include_cost_floor=args.include_cost_floor,
                min_screen_parse_success=args.min_screen_parse_success,
                progress_callback=(
                    lambda message: print(
                        f"[verifier-eval] {message}",
                        file=sys.stderr,
                        flush=True,
                    )
                )
                if args.progress
                else None,
            )
        else:  # pragma: no cover - argparse enforces command choices
            raise ValueError(f"unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (
        DatasetProfileError,
        MiniVerifierError,
        OSError,
        SimplifiedPipelineError,
        SubmissionError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
