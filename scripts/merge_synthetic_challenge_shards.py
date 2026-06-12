#!/usr/bin/env python3
"""Merge generated synthetic challenge corpus shards into one deduped CSV."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT = Path("data/outputs/synthetic_challenge_corpus.merged.csv")
DEFAULT_REPORT = Path("data/outputs/synthetic_challenge_corpus.merged.report.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if not args.inputs:
        raise SystemExit("at least one input shard is required")

    fieldnames: list[str] | None = None
    seen_hashes: set[str] = set()
    input_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    validation_counts: Counter[str] = Counter()
    duplicate_count = 0
    written = 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as out_handle:
        writer: csv.DictWriter[str] | None = None
        for input_path in args.inputs:
            with input_path.open("r", encoding="utf-8", newline="") as in_handle:
                reader = csv.DictReader(in_handle)
                if reader.fieldnames is None:
                    continue
                if fieldnames is None:
                    fieldnames = list(reader.fieldnames)
                    writer = csv.DictWriter(out_handle, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                elif list(reader.fieldnames) != fieldnames:
                    raise SystemExit(f"{input_path}: fieldnames differ from first input")
                assert writer is not None
                for row in reader:
                    input_counts[str(input_path)] += 1
                    text_hash = str(row.get("text_hash", "") or "").strip()
                    if text_hash and text_hash in seen_hashes:
                        duplicate_count += 1
                        continue
                    if text_hash:
                        seen_hashes.add(text_hash)
                    writer.writerow(row)
                    written += 1
                    label_counts[str(row.get("label", "") or "")] += 1
                    validation_counts[str(row.get("validation_status", "") or "")] += 1

    report = {
        "artifact_type": "synthetic_challenge_corpus_merge_report",
        "inputs": [str(path) for path in args.inputs],
        "output": str(args.output),
        "input_counts": dict(sorted(input_counts.items())),
        "written": written,
        "duplicate_count": duplicate_count,
        "label_counts": dict(sorted(label_counts.items())),
        "validation_counts": dict(sorted(validation_counts.items())),
    }
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
