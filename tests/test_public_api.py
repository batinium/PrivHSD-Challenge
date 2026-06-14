import csv
from pathlib import Path

import contextsafe_hsd as hsd
import contextsafe_hsd
import privhsd


def write_rows(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "label"])
        writer.writerow(["1", "Contact @alice before the meeting.", "not_hate"])
        writer.writerow(["2", "Immigrants should leave.", "hate"])


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_top_level_process_csv_api_writes_output(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    audit = tmp_path / "audit.json"
    write_rows(source)

    summary = hsd.process_csv(
        source,
        output,
        text_col="text",
        id_col="id",
        audit_path=audit,
        mode="balanced",
    )

    rows = read_rows(output)
    assert summary["output"] == str(output)
    assert audit.exists()
    assert [row["id"] for row in rows] == ["1", "2"]
    assert "privatized_text" in rows[0]
    assert "[USER]" in rows[0]["privatized_text"]
    assert "Immigrants" in rows[1]["privatized_text"]


def test_top_level_create_and_validate_submission_api(tmp_path):
    source = tmp_path / "input.csv"
    submission = tmp_path / "submission.csv"
    manifest = tmp_path / "manifest.json"
    validation = tmp_path / "validation.json"
    write_rows(source)

    result = hsd.create_submission(
        source,
        submission,
        text_cols=["text"],
        id_col="id",
        manifest_path=manifest,
        replace_text=True,
        mode="balanced",
    )
    report = hsd.validate_submission(
        source,
        submission,
        text_cols=["text"],
        id_col="id",
        output_path=validation,
    )

    rows = read_rows(submission)
    assert result["validation"]["valid"] is True
    assert report["valid"] is True
    assert manifest.exists()
    assert validation.exists()
    assert list(rows[0]) == ["id", "text", "label"]
    assert "[USER]" in rows[0]["text"]


def test_contextsafe_hsd_exposes_public_api():
    assert hsd.process_csv is contextsafe_hsd.process_csv
    assert hsd.create_submission is contextsafe_hsd.create_submission
    assert hsd.privatize_text is contextsafe_hsd.privatize_text


def test_legacy_privhsd_alias_exposes_public_api():
    assert hsd.process_csv is privhsd.process_csv
    assert hsd.create_submission is privhsd.create_submission
    assert hsd.privatize_text is privhsd.privatize_text
