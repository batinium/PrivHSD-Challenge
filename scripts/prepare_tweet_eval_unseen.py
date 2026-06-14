#!/usr/bin/env python3
"""Compatibility wrapper for the packaged TweetEval unseen preparation command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.error

from contextsafe_hsd.datasets import prepare_tweet_eval_unseen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch TweetEval hate/offensive test splits as external unseen data."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/external_unseen/tweet_eval_hate_offensive_test.csv"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/external_unseen/tweet_eval_hate_offensive_test.manifest.json"),
    )
    parser.add_argument("--config", dest="configs", action="append")
    parser.add_argument("--split", default="test")
    parser.add_argument("--max-rows-per-config", type=int)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--request-delay", type=float, default=0.0)
    args = parser.parse_args(argv)
    try:
        result = prepare_tweet_eval_unseen(
            output_path=args.output,
            manifest_path=args.manifest,
            configs=args.configs,
            split=args.split,
            max_rows_per_config=args.max_rows_per_config,
            page_size=args.page_size,
            request_delay=args.request_delay,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
