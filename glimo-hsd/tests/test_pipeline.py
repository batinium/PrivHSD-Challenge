import json
import time

from glimo_hsd import PipelineConfig, process_csv
from glimo_hsd.io import read_csv


def test_process_labeled_csv_writes_expected_artifacts(tmp_path):
    result = process_csv(
        "tests/fixtures/sample_5.csv",
        config=PipelineConfig(
            text_col="text",
            label_col="hs",
            output_dir=tmp_path / "run",
            classifier_backend="keyword",
            restatement_backend="none",
            final_scrub=True,
        ),
    )

    assert result.restated_csv.name == "final_scrubbed.csv"
    assert result.manifest_json.exists()
    assert result.predictions_csv.exists()
    assert result.importances_csv.exists()
    rows, fieldnames = read_csv(result.restated_csv)
    assert fieldnames == ["id", "text", "hs", "meta"]
    assert len(rows) == 5
    assert "[EMAIL]" in rows[0]["text"]
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["steps"]["classification"]["status"] == "provided"
    assert manifest["steps"]["restatement"]["backend"] == "none"


def test_process_unlabeled_csv_materializes_predictions(tmp_path):
    result = process_csv(
        "tests/fixtures/sample_unlabeled.csv",
        config=PipelineConfig(
            text_col="text",
            label_col="hs",
            output_dir=tmp_path / "run",
            classifier_backend="keyword",
            restatement_backend="none",
            final_scrub=True,
        ),
    )

    restated_rows, restated_fields = read_csv(result.restated_csv)
    input_rows, input_fields = read_csv(result.restatement_input_csv)
    prediction_rows, _ = read_csv(result.predictions_csv)

    assert restated_fields == ["id", "text", "meta"]
    assert input_fields == ["id", "text", "meta", "hs", "hs_predicted", "hf_hsd_score"]
    assert input_rows[0]["hs"] == "1"
    assert prediction_rows[0]["hs_predicted"] == "1"
    assert "[EMAIL]" in restated_rows[2]["text"]


def test_process_cache_reuses_manifest(tmp_path):
    config = PipelineConfig(
        text_col="text",
        label_col="hs",
        output_dir=tmp_path / "run",
        classifier_backend="keyword",
        restatement_backend="none",
        final_scrub=True,
    )
    first = process_csv("tests/fixtures/sample_5.csv", config=config)
    first_manifest = first.manifest_json.read_text(encoding="utf-8")
    first_mtime = first.manifest_json.stat().st_mtime
    time.sleep(0.01)

    second = process_csv("tests/fixtures/sample_5.csv", config=config)

    assert second.manifest_json.read_text(encoding="utf-8") == first_manifest
    assert second.manifest_json.stat().st_mtime == first_mtime
