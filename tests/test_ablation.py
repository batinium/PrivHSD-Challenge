import csv
import importlib.util
import json

import pytest

from contextsafe_hsd.ablation import ABLATION_VARIANTS, run_ablation
from contextsafe_hsd.cli import main
from contextsafe_hsd.utility_benchmark import BenchmarkError, INSTALL_HINT


HAS_SKLEARN = importlib.util.find_spec("sklearn") is not None


EXPECTED_VARIANTS = [variant.name for variant in ABLATION_VARIANTS]


def write_ablation_rows(path):
    rows = [
        {
            "id": "1",
            "text": (
                "My name is Alex Vale and @alex emailed alex@example.test. "
                "Muslims should leave now."
            ),
            "label": "hate",
            "meta": "first",
        },
        {
            "id": "2",
            "text": "Call me Brian Stone at +1 202 555 0188. Refugees do not belong.",
            "label": "hate",
            "meta": "second",
        },
        {
            "id": "3",
            "text": "Case ID-123 says immigrants should be deported.",
            "label": "hate",
            "meta": "third",
        },
        {
            "id": "4",
            "text": "Visit https://example.test about the threat.",
            "label": "hate",
            "meta": "fourth",
        },
        {
            "id": "5",
            "text": "Welcome to the neighborhood.",
            "label": "nothate",
            "meta": "fifth",
        },
        {
            "id": "6",
            "text": "The weather is calm today.",
            "label": "nothate",
            "meta": "sixth",
        },
        {
            "id": "7",
            "text": "Please join the public meeting.",
            "label": "nothate",
            "meta": "seventh",
        },
        {
            "id": "8",
            "text": "Everyone deserves respect.",
            "label": "nothate",
            "meta": "eighth",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "text", "label", "meta"])
        writer.writeheader()
        writer.writerows(rows)
    return rows


def read_csv_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_run_ablation_writes_all_variants_and_preserves_rows(tmp_path):
    source = tmp_path / "input.csv"
    report_path = tmp_path / "ablation.json"
    output_dir = tmp_path / "variants"
    original_rows = write_ablation_rows(source)

    result = run_ablation(
        source,
        text_col="text",
        id_col="id",
        label_col="label",
        output_path=report_path,
        output_dir=output_dir,
        test_size=0.25,
        random_state=7,
    )

    assert report_path.exists()
    assert [variant["name"] for variant in result["variants"]] == EXPECTED_VARIANTS
    assert set(result["results"]) == set(EXPECTED_VARIANTS)

    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved_report["columns"]["privatized_col"] == "privatized_text"

    for variant in EXPECTED_VARIANTS:
        csv_path = output_dir / f"input.{variant}.csv"
        rows = read_csv_rows(csv_path)
        assert len(rows) == len(original_rows)
        assert [row["id"] for row in rows] == [row["id"] for row in original_rows]
        assert [row["label"] for row in rows] == [
            row["label"] for row in original_rows
        ]
        assert [row["meta"] for row in rows] == [row["meta"] for row in original_rows]
        assert result["results"][variant]["metrics"]["row_count"] == len(
            original_rows
        )

    identity_rows = read_csv_rows(output_dir / "input.identity.csv")
    assert identity_rows[0]["privatized_text"] == original_rows[0]["text"]

    regex_rows = read_csv_rows(output_dir / "input.regex_only.csv")
    assert "[USER]" in regex_rows[0]["privatized_text"]
    assert "[EMAIL]" in regex_rows[0]["privatized_text"]
    assert "Alex Vale" in regex_rows[0]["privatized_text"]

    balanced_rows = read_csv_rows(output_dir / "input.balanced.csv")
    assert "Alex Vale" not in balanced_rows[0]["privatized_text"]
    assert "[PERSON]" in balanced_rows[0]["privatized_text"]

    target_rows = read_csv_rows(output_dir / "input.balanced_with_targets.csv")
    assert "[TARGET_GROUP:religion]" in target_rows[0]["privatized_text"]
    assert "Muslims" not in target_rows[0]["privatized_text"]


def test_ablate_cli_writes_report(tmp_path):
    source = tmp_path / "input.csv"
    report_path = tmp_path / "ablation.json"
    write_ablation_rows(source)

    exit_code = main(
        [
            "ablate",
            "--input",
            str(source),
            "--text-col",
            "text",
            "--id-col",
            "id",
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert [variant["name"] for variant in report["variants"]] == EXPECTED_VARIANTS
    assert report["results"]["identity"]["rows"][0]["row_id"] == "1"
    assert report["utility_benchmark_skipped"]["reason"].startswith("No label")


def test_ablation_utility_benchmark_skip_path_when_sklearn_unavailable(
    tmp_path, monkeypatch
):
    source = tmp_path / "input.csv"
    write_ablation_rows(source)

    def missing_sklearn():
        raise BenchmarkError(INSTALL_HINT)

    monkeypatch.setattr("contextsafe_hsd.ablation.load_sklearn", missing_sklearn)

    result = run_ablation(
        source,
        text_col="text",
        id_col="id",
        label_col="label",
    )

    assert result["utility_benchmark"]["requested"] is True
    assert result["utility_benchmark"]["available"] is False
    assert result["utility_benchmark_skipped"]["install_hint"] == INSTALL_HINT
    assert ".[benchmark]" in result["utility_benchmark_skipped"]["reason"]


@pytest.mark.skipif(not HAS_SKLEARN, reason="requires optional benchmark extra")
def test_ablation_includes_utility_metrics_when_sklearn_is_available(tmp_path):
    source = tmp_path / "input.csv"
    write_ablation_rows(source)

    result = run_ablation(
        source,
        text_col="text",
        id_col="id",
        label_col="label",
        test_size=0.25,
        random_state=7,
    )

    assert result["utility_benchmark_skipped"] is None
    for variant in EXPECTED_VARIANTS:
        benchmark = result["results"][variant]["utility_benchmark"]
        assert benchmark["benchmark_type"] == "local_relative_utility_proxy"
        assert "macro_f1_delta" in benchmark["comparison"]
        assert benchmark["split"]["dev_count"] == 2
