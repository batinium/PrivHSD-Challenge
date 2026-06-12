import csv
import json

from privhsd.cli import build_parser
from privhsd.source_report import run_source_regression_report


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "text",
                "label",
                "source",
                "split",
                "platform",
                "type",
                "rationale_spans",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_source_regression_report_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "source-regression-report",
            "--original",
            "original.csv",
            "--protected",
            "protected.csv",
            "--original-text-col",
            "text",
            "--protected-text-col",
            "text",
            "--group-col",
            "source",
        ]
    )

    assert args.command == "source-regression-report"
    assert args.group_cols == ["source"]


def test_source_regression_report_groups_without_raw_text(tmp_path):
    original = tmp_path / "original.csv"
    protected = tmp_path / "protected.csv"
    output = tmp_path / "report.json"
    write_csv(
        original,
        [
            {
                "id": "1",
                "text": "Alex hates Muslims.",
                "label": "hate",
                "source": "hatexplain",
                "split": "test",
                "platform": "sample",
                "type": "hate",
                "rationale_spans": "[[1, 3]]",
            },
            {
                "id": "2",
                "text": "That official is a stupid idiot.",
                "label": "offensive",
                "source": "davidson",
                "split": "test",
                "platform": "sample",
                "type": "offensive",
                "rationale_spans": "",
            },
        ],
    )
    write_csv(
        protected,
        [
            {
                "id": "1",
                "text": "[PERSON] hates Muslims.",
                "label": "hate",
                "source": "hatexplain",
                "split": "test",
                "platform": "sample",
                "type": "hate",
                "rationale_spans": "[[1, 3]]",
            },
            {
                "id": "2",
                "text": "That official is a stupid idiot.",
                "label": "offensive",
                "source": "davidson",
                "split": "test",
                "platform": "sample",
                "type": "offensive",
                "rationale_spans": "",
            },
        ],
    )

    result = run_source_regression_report(
        original,
        protected,
        original_text_col="text",
        protected_text_col="text",
        id_col="id",
        group_cols=["source", "label"],
        output_path=output,
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result == written
    assert result["overall"]["row_count"] == 2
    assert result["overall"]["changed_text_count"] == 1
    assert result["overall"]["direct_identifier_counts"]["after"] == 0
    assert result["overall"]["rationale"]["rows_with_rationale"] == 1
    assert result["groups"][0]["group"]
    assert "Alex hates Muslims" not in output.read_text(encoding="utf-8")
