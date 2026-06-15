import csv
from pathlib import Path

import contextsafe_hsd
import contextsafe_hsd as hsd


def write_rows(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "label"])
        writer.writerow(["1", "Contact @alice before the meeting.", "not_hate"])
        writer.writerow(["2", "Immigrants should leave.", "hate"])


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_top_level_final_pipeline_and_validation_api(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    manifest = tmp_path / "manifest.json"
    validation = tmp_path / "validation.json"
    write_rows(source)

    result = hsd.run_final_csv_pipeline(
        source,
        output,
        text_col="text",
        id_col="id",
        manifest_path=manifest,
        llm_review="off",
        disabled_providers=["presidio", "scrubadub"],
    )
    report = hsd.validate_submission(
        source,
        output,
        text_cols=["text"],
        id_col="id",
        output_path=validation,
    )

    rows = read_rows(output)
    assert result["validation"]["valid"] is True
    assert report["valid"] is True
    assert manifest.exists()
    assert validation.exists()
    assert list(rows[0]) == ["id", "text", "label"]
    assert "[USER]" in rows[0]["text"]


def test_contextsafe_hsd_exposes_public_api():
    assert hsd.run_final_csv_pipeline is contextsafe_hsd.run_final_csv_pipeline
    assert hsd.validate_submission is contextsafe_hsd.validate_submission
    assert hsd.privatize_text is contextsafe_hsd.privatize_text
