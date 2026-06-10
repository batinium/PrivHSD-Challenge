import csv

from scripts.prepare_dynahate import normalize


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

    count = normalize(raw, out)

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

