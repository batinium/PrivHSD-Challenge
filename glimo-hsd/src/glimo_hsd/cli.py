"""Command line interface for glimo-hsd."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import (
    DEFAULT_MODEL_ID,
    DEFAULT_THRESHOLD,
    PipelineConfig,
    RestatementConfig,
)
from .io import GlimoHsdError
from .pipeline import process_csv
from .steps import (
    audit_restatements,
    classify_csv,
    final_scrub_csv,
    generate_token_importances,
    restate_csv,
    scrub_csv,
)


def _print(value: dict[str, object]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="glimo-hsd")
    subparsers = parser.add_subparsers(dest="command", required=True)

    process = subparsers.add_parser("process", help="Run the full CSV pipeline.")
    process.add_argument("input_csv", type=Path)
    process.add_argument("--text-col", default="text")
    process.add_argument("--label-col", default="hs")
    process.add_argument("--id-col")
    process.add_argument("--out", type=Path, required=True)
    process.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    process.add_argument("--model-revision")
    process.add_argument(
        "--classifier-backend",
        choices=["hf", "keyword", "none"],
        default="hf",
    )
    process.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    process.add_argument("--device", default="auto")
    process.add_argument("--batch-size", type=int, default=64)
    process.add_argument("--max-length", type=int, default=512)
    process.add_argument(
        "--restatement-backend",
        choices=["none", "qwen", "local-http"],
        default="none",
    )
    process.add_argument("--restatement-endpoint", default="http://localhost:1234/v1")
    process.add_argument("--restatement-model", default="qwen3.5-4b")
    process.add_argument("--restatement-batch-size", type=int, default=5)
    process.add_argument(
        "--final-scrub",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    process.add_argument("--force", action="store_true")

    scrub = subparsers.add_parser("scrub", help="Scrub direct identifiers in a CSV.")
    scrub.add_argument("input_csv", type=Path)
    scrub.add_argument("--text-col", default="text")
    scrub.add_argument("--out", type=Path, required=True)

    classify = subparsers.add_parser("classify", help="Classify CSV rows.")
    classify.add_argument("input_csv", type=Path)
    classify.add_argument("--text-col", default="text")
    classify.add_argument("--id-col")
    classify.add_argument("--out", type=Path, required=True)
    classify.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    classify.add_argument("--model-revision")
    classify.add_argument(
        "--classifier-backend",
        choices=["hf", "keyword"],
        default="hf",
    )
    classify.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)

    importances = subparsers.add_parser(
        "importances",
        help="Generate token importances.",
    )
    importances.add_argument("input_csv", type=Path)
    importances.add_argument("--text-col", default="text")
    importances.add_argument("--id-col")
    importances.add_argument("--out", type=Path, required=True)
    importances.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    importances.add_argument("--model-revision")
    importances.add_argument(
        "--classifier-backend",
        choices=["hf", "keyword"],
        default="hf",
    )
    importances.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)

    restate = subparsers.add_parser("restate", help="Restate a labeled CSV.")
    restate.add_argument("input_csv", type=Path)
    restate.add_argument("--text-col", default="text")
    restate.add_argument("--label-col", default="hs")
    restate.add_argument("--id-col")
    restate.add_argument("--out", type=Path, required=True)
    restate.add_argument("--annotated-out", type=Path)
    restate.add_argument(
        "--restatement-backend",
        choices=["none", "qwen", "local-http"],
        default="none",
    )
    restate.add_argument("--restatement-endpoint", default="http://localhost:1234/v1")
    restate.add_argument("--restatement-model", default="qwen3.5-4b")

    audit = subparsers.add_parser("audit", help="Audit source-vs-restatement drift.")
    audit.add_argument("source_csv", type=Path)
    audit.add_argument("restated_csv", type=Path)
    audit.add_argument("--text-col", default="text")
    audit.add_argument("--id-col")
    audit.add_argument("--label-col", default="hs")
    audit.add_argument("--out", type=Path, required=True)

    final = subparsers.add_parser("final-scrub", help="Final identifier scrub.")
    final.add_argument("input_csv", type=Path)
    final.add_argument("--text-col", default="text")
    final.add_argument("--out", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "process":
        result = process_csv(
            args.input_csv,
            config=PipelineConfig(
                text_col=args.text_col,
                label_col=args.label_col,
                id_col=args.id_col,
                output_dir=args.out,
                model_id=args.model_id,
                model_revision=args.model_revision,
                classifier_backend=args.classifier_backend,
                threshold=args.threshold,
                device=args.device,
                batch_size=args.batch_size,
                max_length=args.max_length,
                restatement_backend=args.restatement_backend,
                restatement_endpoint=args.restatement_endpoint,
                restatement_model=args.restatement_model,
                restatement_batch_size=args.restatement_batch_size,
                final_scrub=args.final_scrub,
                force=args.force,
            ),
        )
        return {
            "output_dir": str(result.output_dir),
            "restated_csv": str(result.restated_csv),
            "audit_csv": str(result.audit_csv),
            "manifest_json": str(result.manifest_json),
        }
    if args.command == "scrub":
        result = scrub_csv(args.input_csv, args.out, text_col=args.text_col)
        return result.to_manifest()
    if args.command == "classify":
        result = classify_csv(
            args.input_csv,
            args.out,
            text_col=args.text_col,
            id_col=args.id_col,
            model_id=args.model_id,
            model_revision=args.model_revision,
            backend=args.classifier_backend,
            threshold=args.threshold,
        )
        return result.to_manifest()
    if args.command == "importances":
        result = generate_token_importances(
            args.input_csv,
            args.out,
            text_col=args.text_col,
            id_col=args.id_col,
            model_id=args.model_id,
            model_revision=args.model_revision,
            backend=args.classifier_backend,
            threshold=args.threshold,
        )
        return result.to_manifest()
    if args.command == "restate":
        result = restate_csv(
            args.input_csv,
            args.out,
            annotated_csv=args.annotated_out,
            text_col=args.text_col,
            id_col=args.id_col,
            label_col=args.label_col,
            config=RestatementConfig(
                backend=args.restatement_backend,
                endpoint=args.restatement_endpoint,
                model=args.restatement_model,
            ),
        )
        return result.to_manifest()
    if args.command == "audit":
        result = audit_restatements(
            args.source_csv,
            args.restated_csv,
            args.out,
            text_col=args.text_col,
            id_col=args.id_col,
            label_col=args.label_col,
        )
        return result.to_manifest()
    if args.command == "final-scrub":
        result = final_scrub_csv(args.input_csv, args.out, text_col=args.text_col)
        return result.to_manifest()
    raise AssertionError(args.command)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _print(_run(args))
    except (GlimoHsdError, OSError, RuntimeError, ValueError) as exc:
        print(f"glimo-hsd: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
