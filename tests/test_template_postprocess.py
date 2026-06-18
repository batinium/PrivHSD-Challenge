import csv
import json

import pytest

from contextsafe_hsd.cli import main
from contextsafe_hsd.template_postprocess import (
    TemplatePostprocessError,
    run_classifier_template_after_baseline,
    run_label_template_after_baseline,
)


def write_rows(path, rows, fieldnames=("ID", "author", "text", "hs")):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_template_after_baseline_writes_separate_exact_format_csv(tmp_path):
    source = tmp_path / "source.csv"
    baseline = tmp_path / "baseline.csv"
    output = tmp_path / "template.csv"
    manifest = tmp_path / "template.manifest.json"
    rows = [
        {"ID": "A", "author": "u1", "text": "raw positive", "hs": "1"},
        {"ID": "B", "author": "u2", "text": "raw negative", "hs": "0"},
    ]
    baseline_rows = [
        {"ID": "A", "author": "u1", "text": "baseline positive", "hs": "1"},
        {"ID": "B", "author": "u2", "text": "baseline negative", "hs": "0"},
    ]
    write_rows(source, rows)
    write_rows(baseline, baseline_rows)

    result = run_label_template_after_baseline(
        source_path=source,
        baseline_path=baseline,
        output_path=output,
        id_col="ID",
        manifest_path=manifest,
    )

    templated_rows = read_rows(output)
    assert [list(row) for row in templated_rows] == [
        ["ID", "author", "text", "hs"],
        ["ID", "author", "text", "hs"],
    ]
    assert templated_rows[0]["ID"] == "A"
    assert templated_rows[0]["author"] == "u1"
    assert templated_rows[0]["hs"] == "1"
    assert templated_rows[0]["text"] in result["positive_templates"]
    assert templated_rows[1]["text"] == result["negative_template"]
    assert result["validation"]["valid"] is True
    assert result["changed_text_cells"] == 2

    manifest_json = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_json["method"] == "label_guided_lexical_template_after_baseline"
    assert manifest_json["baseline"] == str(baseline)


def test_protect_can_emit_template_after_baseline_without_overwriting(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "source.csv"
    baseline = tmp_path / "baseline.csv"
    templated = tmp_path / "templated.csv"
    rows = [
        {"ID": "A", "author": "u1", "text": "raw positive", "hs": "1"},
        {"ID": "B", "author": "u2", "text": "raw negative", "hs": "0"},
    ]
    write_rows(source, rows)

    def fake_run_final_csv_pipeline(input_path, output_path, **kwargs):
        source_rows = read_rows(input_path)
        for row in source_rows:
            row["text"] = f"baseline: {row['text']}"
        write_rows(output_path, source_rows)
        return {"pipeline": "final_exact"}

    monkeypatch.setattr(
        "contextsafe_hsd.cli.run_final_csv_pipeline",
        fake_run_final_csv_pipeline,
    )

    exit_code = main(
        [
            "protect",
            "--input",
            str(source),
            "--output",
            str(baseline),
            "--text-col",
            "text",
            "--id-col",
            "ID",
            "--template-after-baseline-output",
            str(templated),
        ]
    )

    baseline_rows = read_rows(baseline)
    templated_rows = read_rows(templated)
    assert exit_code == 0
    assert baseline_rows[0]["text"] == "baseline: raw positive"
    assert templated_rows[0]["text"] != baseline_rows[0]["text"]
    assert templated_rows[1]["text"] == "General discussion without targeted abuse."
    assert templated.with_suffix(".manifest.json").exists()


def test_template_after_baseline_refuses_to_overwrite_baseline(tmp_path):
    source = tmp_path / "source.csv"
    baseline = tmp_path / "baseline.csv"
    rows = [{"ID": "A", "author": "u1", "text": "raw positive", "hs": "1"}]
    write_rows(source, rows)
    write_rows(baseline, rows)

    with pytest.raises(TemplatePostprocessError, match="refusing to overwrite"):
        run_label_template_after_baseline(
            source_path=source,
            baseline_path=baseline,
            output_path=baseline,
            id_col="ID",
        )


def test_classifier_template_after_baseline_can_run_without_gold_labels(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "source.csv"
    baseline = tmp_path / "baseline.csv"
    output = tmp_path / "classifier_template.csv"
    fieldnames = ("ID", "author", "text")
    source_rows = [
        {"ID": "A", "author": "u1", "text": "raw maybe positive"},
        {"ID": "B", "author": "u2", "text": "raw maybe negative"},
    ]
    baseline_rows = [
        {"ID": "A", "author": "u1", "text": "baseline positive"},
        {"ID": "B", "author": "u2", "text": "baseline negative"},
    ]
    write_rows(source, source_rows, fieldnames=fieldnames)
    write_rows(baseline, baseline_rows, fieldnames=fieldnames)

    class FakeClassifierRow:
        def __init__(self, hate):
            self.hate = hate

    class FakeClassifierResult:
        rows = (FakeClassifierRow(True), FakeClassifierRow(False))

        def summary(self):
            return {
                "backend": "hf_classifier",
                "prediction_counts": {"0": 1, "1": 1},
            }

    class FakeClassifier:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def classify_texts(self, rows, *, batch_size):
            assert [row["text"] for row in rows] == [
                "baseline positive",
                "baseline negative",
            ]
            return FakeClassifierResult()

    monkeypatch.setattr(
        "contextsafe_hsd.template_postprocess.HfHsdClassifierRuntime",
        FakeClassifier,
    )

    result = run_classifier_template_after_baseline(
        source_path=source,
        baseline_path=baseline,
        output_path=output,
        id_col="ID",
    )

    templated_rows = read_rows(output)
    assert templated_rows[0]["text"] in result["positive_templates"]
    assert templated_rows[1]["text"] == result["negative_template"]
    assert result["predicted_positive_rows"] == 1
    assert result["predicted_negative_rows"] == 1
    assert result["label_metrics_if_available"] is None
