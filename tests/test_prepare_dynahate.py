import csv

from privhsd.datasets import normalize_dynahate


def test_normalize_dynahate_shape(tmp_path):
    raw = tmp_path / "raw.csv"
    out = tmp_path / "normalized.csv"
    with raw.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["acl.id", "Text", "Label", "Split", "Target", "Type"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "acl.id": "abc",
                "Text": "sample text",
                "Label": "nothate",
                "Split": "train",
                "Target": "none",
                "Type": "none",
            }
        )

    count = normalize_dynahate(raw, out)

    assert count == 1
    with out.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "id": "abc",
            "text": "sample text",
            "label": "nothate",
            "source": "dynahate",
            "split": "train",
            "target": "none",
            "type": "none",
        }
    ]


def test_normalize_dynahate_lowercase_shape(tmp_path):
    raw = tmp_path / "raw.csv"
    out = tmp_path / "normalized.csv"
    with raw.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["", "acl.id", "text", "label", "split", "target", "type"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "": "1",
                "acl.id": "acl1",
                "text": "sample text",
                "label": "hate",
                "split": "test",
                "target": "none",
                "type": "none",
            }
        )

    count = normalize_dynahate(raw, out)

    assert count == 1
    with out.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["id"] == "acl1"
    assert rows[0]["text"] == "sample text"
    assert rows[0]["label"] == "hate"
    assert rows[0]["split"] == "test"
