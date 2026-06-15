import csv
from dataclasses import dataclass
import json

from contextsafe_hsd.csv_pipeline import evaluate_csv, process_csv


def write_rows(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "text", "label"])
        writer.writeheader()
        writer.writerows(rows)


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


def test_process_csv_writes_privatized_text_and_audit(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    audit = tmp_path / "audit.json"
    write_rows(
        source,
        [
            {
                "id": "1",
                "text": "@user emailed user@example.test about a threat.",
                "label": "hate",
            },
            {
                "id": "2",
                "text": "No identifiers here.",
                "label": "nothate",
            },
        ],
    )

    summary = process_csv(
        source,
        output,
        text_col="text",
        id_col="id",
        audit_path=audit,
    )

    assert summary["metrics"]["row_count"] == 2
    with output.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["privatized_text"] == "[USER] emailed [EMAIL] about a threat."
    assert rows[0]["text"] != rows[0]["privatized_text"]
    assert rows[0]["label"] == "hate"

    audit_data = json.loads(audit.read_text(encoding="utf-8"))
    assert audit_data["rows"][0]["row_id"] == "1"
    assert audit_data["rows"][0]["transformations"]


def test_process_csv_uses_row_index_for_sensitive_id_column(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    audit = tmp_path / "audit.json"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["author_id", "text", "label"])
        writer.writeheader()
        writer.writerow(
            {
                "author_id": "author-secret-1",
                "text": "@user emailed user@example.test about a threat.",
                "label": "hate",
            }
        )

    process_csv(
        source,
        output,
        text_col="text",
        id_col="author_id",
        audit_path=audit,
    )

    audit_data = json.loads(audit.read_text(encoding="utf-8"))
    assert audit_data["rows"][0]["row_id"] == "1"
    assert "author-secret-1" not in json.dumps(audit_data)


def test_process_csv_can_use_filtered_presidio_augmentation(monkeypatch, tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    audit = tmp_path / "audit.json"
    write_rows(
        source,
        [{"id": "1", "text": "i'm going to kill Amy", "label": "nothate"}],
    )
    monkeypatch.setattr(
        "contextsafe_hsd.csv_pipeline.load_presidio_analyzer",
        lambda: FakePresidioAnalyzer(),
    )

    summary = process_csv(
        source,
        output,
        text_col="text",
        id_col="id",
        audit_path=audit,
        presidio_augment=True,
    )

    with output.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    audit_data = json.loads(audit.read_text(encoding="utf-8"))
    assert rows[0]["privatized_text"] == "i'm going to kill [PERSON]"
    assert summary["presidio_augment"]["accepted_counts_by_type"] == {"PERSON": 1}
    assert audit_data["rows"][0]["presidio_augment"]["accepted_span_count"] == 1


def test_evaluate_csv_returns_proxy_metrics(tmp_path):
    source = tmp_path / "output.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "text", "privatized_text"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "text": "@user said there was a threat.",
                "privatized_text": "[USER] said there was a threat.",
            }
        )

    result = evaluate_csv(source, text_col="text", privatized_col="privatized_text")

    assert result["metrics"]["row_count"] == 1
    assert result["metrics"]["identifier_counts"]["before"] >= 1
    assert result["metrics"]["identifier_counts"]["after"] == 0
