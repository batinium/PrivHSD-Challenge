import csv
import json

from contextsafe_hsd.cli import build_parser
from contextsafe_hsd.semantic_triage import run_semantic_triage_report


def write_semantic_rows(path):
    rows = [
        (
            "1",
            "Do not attack Muslims.",
            "Do not attack Muslims.",
            "ambiguous",
            "hatecheck",
        ),
        (
            "2",
            'They reported "attack Muslims" while condemning hate.',
            'They reported "attack Muslims" while condemning hate.',
            "not_hate",
            "hatexplain",
        ),
        (
            "3",
            "Muslims should leave.",
            "They should leave.",
            "hate",
            "hatexplain",
        ),
        (
            "4",
            "The weather is calm today.",
            "The weather is calm today.",
            "not_hate",
            "synthetic",
        ),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "privatized_text", "label", "source"])
        writer.writerows(rows)


def test_semantic_triage_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "semantic-triage-report",
            "--input",
            "input.csv",
            "--text-col",
            "text",
            "--privatized-col",
            "privatized_text",
        ]
    )

    assert args.command == "semantic-triage-report"
    assert args.low_confidence == 0.65


def test_semantic_triage_flags_only_review_rows_without_raw_text(tmp_path):
    source = tmp_path / "triage.csv"
    output = tmp_path / "triage.json"
    queue = tmp_path / "queue.csv"
    write_semantic_rows(source)

    result = run_semantic_triage_report(
        source,
        text_col="text",
        privatized_col="privatized_text",
        id_col="id",
        label_col="label",
        source_col="source",
        output_path=output,
        queue_output_path=queue,
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result == written
    assert result["raw_text_included"] is False
    assert result["fallbacks"]["trained_classifier"] == "not_requested"
    assert result["aggregate"]["row_count"] == 4
    assert result["aggregate"]["review_route_counts"]["qwen_semantic_check"] == 2
    assert result["aggregate"]["review_route_counts"]["repair_before_model_review"] == 1
    assert result["aggregate"]["review_route_counts"]["no_review"] == 1
    assert result["aggregate"]["reason_counts"]["ambiguous_source_label"] == 1
    assert result["aggregate"]["reason_counts"]["semantic_context_marker"] == 2
    assert result["aggregate"]["reason_counts"]["cue_loss"] == 1

    serialized = json.dumps(result, ensure_ascii=False)
    assert "Do not attack Muslims" not in serialized
    assert "They reported" not in serialized
    assert queue.exists()
    queue_text = queue.read_text(encoding="utf-8")
    assert "qwen_semantic_check" in queue_text
    assert "Do not attack Muslims" not in queue_text


def test_semantic_triage_compares_separate_exact_format_files(tmp_path):
    original = tmp_path / "original.csv"
    protected = tmp_path / "protected.csv"
    output = tmp_path / "triage.json"
    with original.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "label", "source"])
        writer.writerow(["1", 'They quoted "hello".', "not_hate", "src"])
    with protected.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "label", "source"])
        writer.writerow(["1", "They mentioned hello.", "not_hate", "src"])

    result = run_semantic_triage_report(
        original,
        protected_path=protected,
        text_col="text",
        privatized_col="text",
        id_col="id",
        label_col="label",
        source_col="source",
        output_path=output,
    )

    assert result["protected"] == str(protected)
    assert result["row_alignment_valid"] is True
    assert result["aggregate"]["review_route_counts"]["repair_before_model_review"] == 1
    assert result["review_rows"][0]["lost_context_tags"] == ["quoted_or_reported"]


class FakeClassifier:
    classes_ = ["hate", "not_hate"]

    def predict_proba(self, texts):
        output = []
        for text in texts:
            if "original marker" in text:
                output.append([0.9, 0.1])
            elif "protected marker" in text:
                output.append([0.48, 0.52])
            else:
                output.append([0.8, 0.2])
        return output


def test_semantic_triage_uses_optional_classifier_confidence(monkeypatch, tmp_path):
    source = tmp_path / "classifier_triage.csv"
    model_path = tmp_path / "model.pkl"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "privatized_text", "label"])
        writer.writerow(["1", "original marker", "protected marker", "hate"])

    monkeypatch.setattr(
        "contextsafe_hsd.semantic_triage.load_model",
        lambda _path: (FakeClassifier(), {"model_type": "fake"}),
    )

    result = run_semantic_triage_report(
        source,
        text_col="text",
        privatized_col="privatized_text",
        id_col="id",
        label_col="label",
        classifier_model=model_path,
    )

    row = result["review_rows"][0]
    assert result["classifier"]["status"] == "ok"
    assert row["review_route"] == "qwen_semantic_check"
    assert row["priority"] == "high"
    assert "classifier_prediction_shift" in row["reasons"]
    assert "classifier_low_confidence" in row["reasons"]
    assert "classifier_low_margin" in row["reasons"]
    assert "classifier_confidence_drop" in row["reasons"]
