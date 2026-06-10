#!/usr/bin/env python3
"""Download and normalize the Dynamically Generated Hate Speech Dataset."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys
import urllib.request


DEFAULT_URL = (
    "https://raw.githubusercontent.com/bvidgen/"
    "Dynamically-Generated-Hate-Speech-Dataset/main/"
    "Dynamically%20Generated%20Hate%20Dataset%20v0.2.3.csv"
)


def download(url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        output.write_bytes(response.read())


def normalize(raw_path: Path, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("r", encoding="utf-8", newline="") as in_handle:
        reader = csv.DictReader(in_handle)
        if reader.fieldnames is None:
            raise ValueError(f"{raw_path}: CSV header is required")
        required = {"acl.id", "Text", "Label"}
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise ValueError(f"{raw_path}: missing column(s): {', '.join(missing)}")

        fieldnames = ["id", "text", "label", "source", "split", "target", "type"]
        with output_path.open("w", encoding="utf-8", newline="") as out_handle:
            writer = csv.DictWriter(out_handle, fieldnames=fieldnames)
            writer.writeheader()
            count = 0
            for row in reader:
                writer.writerow(
                    {
                        "id": row.get("acl.id", ""),
                        "text": row.get("Text", ""),
                        "label": row.get("Label", ""),
                        "source": "dynahate",
                        "split": row.get("Split", ""),
                        "target": row.get("Target", ""),
                        "type": row.get("Type", ""),
                    }
                )
                count += 1
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/public_dev/dynahate_raw.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/public_dev/dynahate.csv"))
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--url", default=DEFAULT_URL)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.download:
            download(args.url, args.raw)
        count = normalize(args.raw, args.output)
        print(f"Wrote {count} normalized row(s) to {args.output}")
        return 0
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

