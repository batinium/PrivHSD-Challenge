import csv
import json

from privhsd.cli import build_parser
from privhsd.presidio_compare import PresidioCompareError, run_presidio_comparison


class FakePresidioResult:
    def __init__(self, start, end, entity_type, score=0.8):
        self.start = start
        self.end = end
        self.entity_type = entity_type
        self.score = score


class FakeAnalyzer:
    def analyze(self, text, language="en"):
        results = []
        email = "alex@example.test"
        if email in text:
            start = text.index(email)
            results.append(FakePresidioResult(start, start + len(email), "EMAIL_ADDRESS"))
        target = "immigrants"
        if target in text.lower():
            start = text.lower().index(target)
            results.append(FakePresidioResult(start, start + len(target), "PERSON"))
        return results


def write_rows(path):
    rows = [
        ("1", "Email alex@example.test because immigrants should leave.", "hate"),
        ("2", "No identifiers here.", "nothate"),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "label"])
        writer.writerows(rows)


def test_compare_presidio_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "compare-presidio",
            "--input",
            "input.csv",
            "--text-col",
            "text",
        ]
    )

    assert args.command == "compare-presidio"
    assert args.sample_size == 100


def test_compare_presidio_skips_when_dependency_missing(monkeypatch, tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "presidio.json"
    write_rows(source)

    def fake_load():
        raise PresidioCompareError("missing optional dependency")

    monkeypatch.setattr("privhsd.presidio_compare.load_presidio", fake_load)

    result = run_presidio_comparison(
        source,
        text_col="text",
        id_col="id",
        output_path=output,
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result == written
    assert result["status"] == "skipped"
    assert result["skip_reason"] == "missing_optional_dependency"


def test_compare_presidio_reports_overlap_and_false_positive_risk(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.csv"
    write_rows(source)
    monkeypatch.setattr(
        "privhsd.presidio_compare.load_presidio",
        lambda: FakeAnalyzer(),
    )

    result = run_presidio_comparison(
        source,
        text_col="text",
        id_col="id",
        sample_size=2,
    )

    assert result["status"] == "ok"
    assert result["aggregate"]["presidio_span_count"] == 2
    assert result["aggregate"]["overlap_count"] >= 1
    assert result["aggregate"]["false_positive_risk_count"] == 1
    assert result["rows"][0]["row_id"] == "1"
    assert "text" not in result["rows"][0]
