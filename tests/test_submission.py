import csv
from dataclasses import dataclass
import json

import pytest

from privhsd.cli import build_parser
from privhsd.submission import (
    SubmissionError,
    create_submission,
    validate_submission,
)


@dataclass(frozen=True)
class FakePresidioResult:
    start: int
    end: int
    entity_type: str
    score: float = 0.85


class FakePresidioAnalyzer:
    def analyze(self, *, text, language):
        if "Amy" not in text:
            return []
        start = text.index("Amy")
        return [FakePresidioResult(start, start + len("Amy"), "PERSON")]


def write_source(path):
    rows = [
        {
            "id": "1",
            "text": "@mara emailed mara@example.test that immigrants should leave.",
            "label": "hate",
            "meta": "keep-a",
        },
        {
            "id": "2",
            "text": "Everyone deserves respect.",
            "label": "nothate",
            "meta": "keep-b",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "text", "label", "meta"])
        writer.writeheader()
        writer.writerows(rows)
    return rows


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_submission_commands_are_registered():
    parser = build_parser()

    create_args = parser.parse_args(
        [
            "create-submission",
            "--input",
            "input.csv",
            "--output",
            "submission.csv",
            "--text-col",
            "text",
            "--replace-text",
            "--presidio-augment",
        ]
    )
    validate_args = parser.parse_args(
        [
            "validate-submission",
            "--source",
            "input.csv",
            "--submission",
            "submission.csv",
            "--text-col",
            "text",
        ]
    )

    assert create_args.command == "create-submission"
    assert create_args.text_cols == ["text"]
    assert create_args.presidio_augment is True
    assert validate_args.command == "validate-submission"


def test_create_submission_privatizes_in_place_and_writes_manifest(tmp_path):
    source = tmp_path / "source.csv"
    output = tmp_path / "submission.csv"
    manifest_path = tmp_path / "manifest.json"
    original_rows = write_source(source)

    manifest = create_submission(
        source,
        output,
        text_cols=["text"],
        id_col="id",
        manifest_path=manifest_path,
        command=[
            "privhsd",
            "create-submission",
            "--input",
            str(source),
            "--replace-text",
        ],
        mode="balanced",
        replace_text=True,
    )

    rows = read_rows(output)
    written_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest == written_manifest
    assert list(rows[0]) == ["id", "text", "label", "meta"]
    assert [row["id"] for row in rows] == [row["id"] for row in original_rows]
    assert [row["label"] for row in rows] == [row["label"] for row in original_rows]
    assert [row["meta"] for row in rows] == [row["meta"] for row in original_rows]
    assert "[USER]" in rows[0]["text"]
    assert "[EMAIL]" in rows[0]["text"]
    assert "immigrants should leave" in rows[0]["text"]
    assert "privatized_text" not in rows[0]
    assert manifest["artifact_type"] == "exact_format_submission"
    assert manifest["input"]["sha256"]
    assert manifest["output"]["sha256"]
    assert manifest["validation"]["valid"] is True
    assert manifest["metrics"]["row_count"] == 2


def test_create_submission_can_use_filtered_presidio_augmentation(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "source.csv"
    output = tmp_path / "submission.csv"
    manifest_path = tmp_path / "manifest.json"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "text", "label", "meta"])
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "text": "i'm going to kill Amy",
                "label": "nothate",
                "meta": "keep",
            }
        )
    monkeypatch.setattr(
        "privhsd.submission.load_presidio_analyzer",
        lambda: FakePresidioAnalyzer(),
    )

    manifest = create_submission(
        source,
        output,
        text_cols=["text"],
        id_col="id",
        manifest_path=manifest_path,
        replace_text=True,
        presidio_augment=True,
    )

    rows = read_rows(output)
    assert rows[0]["text"] == "i'm going to kill [PERSON]"
    assert manifest["presidio_augment"]["accepted_counts_by_type"] == {"PERSON": 1}
    assert manifest["validation"]["valid"] is True


def test_create_submission_requires_replace_text(tmp_path):
    source = tmp_path / "source.csv"
    output = tmp_path / "submission.csv"
    write_source(source)

    with pytest.raises(SubmissionError, match="replace-text"):
        create_submission(
            source,
            output,
            text_cols=["text"],
            replace_text=False,
        )


def test_validate_submission_reports_helper_columns(tmp_path):
    source = tmp_path / "source.csv"
    submission = tmp_path / "submission.csv"
    write_source(source)
    with submission.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "text", "label", "meta", "privatized_text"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "text": "changed",
                "label": "hate",
                "meta": "keep-a",
                "privatized_text": "helper",
            }
        )
        writer.writerow(
            {
                "id": "2",
                "text": "changed",
                "label": "nothate",
                "meta": "keep-b",
                "privatized_text": "helper",
            }
        )

    report = validate_submission(
        source,
        submission,
        text_cols=["text"],
        id_col="id",
        strict=False,
    )

    assert report["valid"] is False
    assert {issue["code"] for issue in report["issues"]} >= {
        "helper_columns_present",
        "column_order_mismatch",
    }


def test_validate_submission_reports_reordered_ids(tmp_path):
    source = tmp_path / "source.csv"
    submission = tmp_path / "submission.csv"
    write_source(source)
    rows = read_rows(source)
    with submission.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "text", "label", "meta"])
        writer.writeheader()
        writer.writerows(reversed(rows))

    report = validate_submission(
        source,
        submission,
        text_cols=["text"],
        id_col="id",
        strict=False,
    )

    assert report["valid"] is False
    assert "id_order_mismatch" in {issue["code"] for issue in report["issues"]}
