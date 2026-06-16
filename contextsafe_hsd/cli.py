"""Command-line interface for the final ContextSafe-HSD pipeline."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .dataset_profile import DatasetProfileError, profile_dataset
from .mini_verifier_ablation import (
    DEFAULT_ENDPOINT as MINI_VERIFIER_DEFAULT_ENDPOINT,
    DEFAULT_MAIN_MODEL as MINI_VERIFIER_DEFAULT_MAIN_MODEL,
    DEFAULT_OUTPUT_DIR as MINI_VERIFIER_DEFAULT_OUTPUT_DIR,
    DEFAULT_RUN_DIR as MINI_VERIFIER_DEFAULT_RUN_DIR,
    DEFAULT_SOURCE_CSV as MINI_VERIFIER_DEFAULT_SOURCE_CSV,
    MiniVerifierAblationError,
    run_ablation,
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
        "--enable-author-group-masking",
        action="store_true",
        help=(
            "Mask detector-backed factual spans repeated across rows from the "
            "same author/user group after row-level sanitization. Off by default."
        ),
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
            "Presidio/scrubadub PII Assist, cue-safe candidate selection, and "
            "optional local LLM sidecar review on cleaned text only."
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
        default="local-llm",
        help="Run sidecar-only local LLM HSD review after sanitization.",
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

    ablation = subparsers.add_parser(
        "mini-4b-verifier-ablation",
        help="Run the 160-row local 3B-4B HSD verifier/router ablation.",
    )
    ablation.add_argument("--source-csv", type=Path, default=MINI_VERIFIER_DEFAULT_SOURCE_CSV)
    ablation.add_argument("--run-dir", type=Path, default=MINI_VERIFIER_DEFAULT_RUN_DIR)
    ablation.add_argument("--output-dir", type=Path, default=MINI_VERIFIER_DEFAULT_OUTPUT_DIR)
    ablation.add_argument("--endpoint", default=MINI_VERIFIER_DEFAULT_ENDPOINT)
    ablation.add_argument("--main-model", default=MINI_VERIFIER_DEFAULT_MAIN_MODEL)
    ablation.add_argument("--batch-size", type=int, default=10)
    ablation.add_argument("--timeout-seconds", type=float, default=120.0)
    ablation.add_argument("--candidate", action="append", dest="candidates", default=[])
    ablation.add_argument("--shortlist-size", type=int, default=3)
    ablation.add_argument("--rebuild-eval-set", action="store_true")
    ablation.add_argument("--include-cost-floor", action="store_true")
    ablation.add_argument(
        "--skip-uncensored-probe",
        action="store_true",
        help="Do not run the aggressive uncensored probe even if present.",
    )
    ablation.add_argument("--min-screen-parse-success", type=float, default=0.95)
    ablation.add_argument(
        "--progress",
        action="store_true",
        help="Print ablation progress to stderr.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(raw_argv)
    try:
        if args.command == "protect":
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
                local_llm_endpoint=args.local_llm_endpoint,
                local_llm_model=args.local_llm_model,
                local_llm_timeout_seconds=args.local_llm_timeout_seconds,
                local_llm_batch_size=args.local_llm_batch_size,
                local_llm_enable_pii_suggestions=(
                    not args.disable_local_llm_pii_suggestions
                ),
                require_hate_classification=args.require_llm_review,
                author_group_masking=args.enable_author_group_masking,
                author_group_col=args.author_group_col,
                author_group_min_repetitions=args.author_group_min_repetitions,
                author_group_min_author_rows=args.author_group_min_author_rows,
                generalize_targets=False,
                style_scrub=False,
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
        elif args.command == "mini-4b-verifier-ablation":
            result = run_ablation(
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
                        f"[ablation] {message}",
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
        MiniVerifierAblationError,
        OSError,
        SimplifiedPipelineError,
        SubmissionError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
