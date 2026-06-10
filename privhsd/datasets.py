"""Dataset preparation helpers."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys
import urllib.error
import urllib.request


DEFAULT_DYNAHATE_URL = (
    "https://raw.githubusercontent.com/bvidgen/"
    "Dynamically-Generated-Hate-Speech-Dataset/main/"
    "Dynamically%20Generated%20Hate%20Dataset%20v0.2.3.csv"
)


def download_file(url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        output.write_bytes(response.read())


def pick_column(fieldnames: list[str], *candidates: str) -> str:
    by_lower = {name.lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
        lowered = candidate.lower()
        if lowered in by_lower:
            return by_lower[lowered]
    raise ValueError(f"missing column; expected one of: {', '.join(candidates)}")


def optional_column(fieldnames: list[str], *candidates: str) -> str | None:
    by_lower = {name.lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
        lowered = candidate.lower()
        if lowered in by_lower:
            return by_lower[lowered]
    return None


def normalize_dynahate(raw_path: Path, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("r", encoding="utf-8", newline="") as in_handle:
        reader = csv.DictReader(in_handle)
        if reader.fieldnames is None:
            raise ValueError(f"{raw_path}: CSV header is required")
        fields = list(reader.fieldnames)
        id_col = pick_column(fields, "acl.id")
        text_col = pick_column(fields, "Text", "text")
        label_col = pick_column(fields, "Label", "label")
        split_col = optional_column(fields, "Split", "split")
        target_col = optional_column(fields, "Target", "target")
        type_col = optional_column(fields, "Type", "type")

        fieldnames = ["id", "text", "label", "source", "split", "target", "type"]
        with output_path.open("w", encoding="utf-8", newline="") as out_handle:
            writer = csv.DictWriter(out_handle, fieldnames=fieldnames)
            writer.writeheader()
            count = 0
            for row in reader:
                writer.writerow(
                    {
                        "id": row.get(id_col, ""),
                        "text": row.get(text_col, ""),
                        "label": row.get(label_col, ""),
                        "source": "dynahate",
                        "split": row.get(split_col, "") if split_col else "",
                        "target": row.get(target_col, "") if target_col else "",
                        "type": row.get(type_col, "") if type_col else "",
                    }
                )
                count += 1
    return count


def prepare_dynahate(
    *,
    raw_path: Path,
    output_path: Path,
    download: bool = False,
    url: str = DEFAULT_DYNAHATE_URL,
) -> int:
    if download:
        download_file(url, raw_path)
    return normalize_dynahate(raw_path, output_path)


def add_prepare_dynahate_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "prepare-dynahate",
        help="Download and normalize the public Dynahate dataset.",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path("data/public_dev/dynahate_raw.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/public_dev/dynahate.csv"),
    )
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--url", default=DEFAULT_DYNAHATE_URL)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download and normalize Dynahate.")
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path("data/public_dev/dynahate_raw.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/public_dev/dynahate.csv"),
    )
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--url", default=DEFAULT_DYNAHATE_URL)
    args = parser.parse_args(argv)
    try:
        count = prepare_dynahate(
            raw_path=args.raw,
            output_path=args.output,
            download=args.download,
            url=args.url,
        )
        print(f"Wrote {count} normalized row(s) to {args.output}")
        return 0
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

