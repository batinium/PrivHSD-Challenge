import csv
import json

import pytest

from privhsd.cli import build_parser
from privhsd.dataset_profile import DatasetProfileError, profile_dataset


def test_profile_dataset_reports_aggregate_schema_without_raw_text(tmp_path):
    source = tmp_path / "incoming.csv"
    output = tmp_path / "profile.json"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["row_id", "body_text", "gold_label", "author_id", "split"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "row_id": "1",
                "body_text": "Private example one",
                "gold_label": "hate",
                "author_id": "a",
                "split": "train",
            }
        )
        writer.writerow(
            {
                "row_id": "2",
                "body_text": "Private example one",
                "gold_label": "not_hate",
                "author_id": "a",
                "split": "test",
            }
        )
        writer.writerow(
            {
                "row_id": "3",
                "body_text": "Different private example",
                "gold_label": "hate",
                "author_id": "b",
                "split": "train",
            }
        )

    result = profile_dataset(source, output_path=output)

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result == written
    assert result["row_count"] == 3
    assert result["detected_columns"]["text_col"] == "body_text"
    assert result["detected_columns"]["label_col"] == "gold_label"
    assert result["text_profile"]["duplicate_normalized_text"]["duplicate_rows"] == 2
    assert result["author_or_id_candidate_stats"]["author_id"]["duplicate_rows"] == 2
    assert "Private example one" not in json.dumps(result)


def test_profile_dataset_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "profile-dataset",
            "--input",
            "input.csv",
            "--text-col",
            "text",
            "--top-k",
            "5",
        ]
    )

    assert args.command == "profile-dataset"
    assert args.text_col == "text"
    assert args.top_k == 5


def test_profile_dataset_rejects_missing_explicit_column(tmp_path):
    source = tmp_path / "incoming.csv"
    source.write_text("id,text\n1,hello\n", encoding="utf-8")

    with pytest.raises(DatasetProfileError, match="missing requested column"):
        profile_dataset(source, text_col="missing")
