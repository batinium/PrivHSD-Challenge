import csv
import json

import pytest

from contextsafe_hsd.cli import build_parser
from contextsafe_hsd.metadata_leakage import MetadataLeakageError, scan_metadata_leakage


def write_rows(path):
    rows = [
        {
            "id": "row-1",
            "author": "Author_A",
            "text": "Author_A posted this.",
            "privatized_text": "[PERSON] posted this.",
        },
        {
            "id": "row-2",
            "author": "Author_B",
            "text": "No direct leak.",
            "privatized_text": "No direct leak from authorb.",
        },
        {
            "id": "row-3",
            "author": "xy",
            "text": "xy is short and ignored.",
            "privatized_text": "xy is short and ignored.",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "author", "text", "privatized_text"],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_check_metadata_leakage_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "check-metadata-leakage",
            "--input",
            "input.csv",
            "--text-col",
            "text",
            "--text-col",
            "privatized_text",
            "--metadata-col",
            "author",
        ]
    )

    assert args.command == "check-metadata-leakage"
    assert args.text_cols == ["text", "privatized_text"]
    assert args.metadata_cols == ["author"]


def test_scan_metadata_leakage_reports_exact_and_normalized_hits(tmp_path):
    source = tmp_path / "rows.csv"
    output = tmp_path / "leakage.json"
    write_rows(source)

    result = scan_metadata_leakage(
        source,
        text_cols=["text", "privatized_text"],
        metadata_cols=["author"],
        id_col="id",
        output_path=output,
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result == written
    assert result["status"] == "ok"
    assert result["leak_count"] == 2
    assert result["by_metadata_col"]["author"]["text_columns"]["text"] == {
        "exact": 1,
        "normalized": 0,
        "total": 1,
    }
    assert result["by_metadata_col"]["author"]["text_columns"]["privatized_text"] == {
        "exact": 0,
        "normalized": 1,
        "total": 1,
    }
    assert result["by_metadata_col"]["author"]["skipped_short_value_count"] == 1
    assert "value_hash" in result["examples"][0]
    assert "Author_A" not in json.dumps(result)


def test_scan_metadata_leakage_uses_row_index_for_sensitive_id_column(tmp_path):
    source = tmp_path / "rows.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["author_id", "text"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "author_id": "author-secret-1",
                "text": "author-secret-1 appears here.",
            }
        )

    result = scan_metadata_leakage(
        source,
        text_cols=["text"],
        metadata_cols=["author_id"],
        id_col="author_id",
    )

    assert result["examples"][0]["row_id"] == "1"
    assert "author-secret-1" not in json.dumps(result)


def test_scan_metadata_leakage_requires_metadata_columns(tmp_path):
    source = tmp_path / "rows.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["text"])
        writer.writeheader()
        writer.writerow({"text": "hello"})

    with pytest.raises(MetadataLeakageError, match="metadata"):
        scan_metadata_leakage(source, text_cols=["text"])
