from pathlib import Path

from glimo_hsd.io import read_csv
from glimo_hsd.steps import classify_csv, scrub_csv


def test_scrub_csv_masks_direct_identifiers(tmp_path):
    out = tmp_path / "scrubbed.csv"

    result = scrub_csv("tests/fixtures/sample_5.csv", out, text_col="text")

    rows, _ = read_csv(out)
    assert result.metadata["replacement_count"] >= 2
    assert "[EMAIL]" in rows[0]["text"]
    assert "[URL]" in rows[3]["text"]


def test_classify_keyword_backend(tmp_path):
    out = tmp_path / "predictions.csv"

    result = classify_csv(
        Path("tests/fixtures/sample_unlabeled.csv"),
        out,
        text_col="text",
        backend="keyword",
    )

    rows, _ = read_csv(out)
    assert result.metadata["positive_rows"] == 1
    assert rows[0]["hs_predicted"] == "1"
