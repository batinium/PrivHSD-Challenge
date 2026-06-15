import csv
import json

import pytest

from contextsafe_hsd.cli import build_parser
from contextsafe_hsd.models.local_llm_hsd_review_runtime import (
    LocalLlmReviewResult,
    LocalLlmRowReview,
)
from contextsafe_hsd.simple_pipeline import (
    SimplifiedPipelineError,
    run_final_csv_pipeline,
    run_sanitize_classify,
)


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path, *, include_label=True):
    fieldnames = ["id", "text"]
    if include_label:
        fieldnames.append("is_hate_speech")
    rows = [
        {
            "id": "1",
            "text": "@mara emailed mara@example.test that Muslims should leave.",
            "is_hate_speech": "gold-positive",
        },
        {
            "id": "2",
            "text": "Everyone deserves respect.",
            "is_hate_speech": "gold-negative",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in fieldnames})


class FakeHsdAdvisory:
    decision_threshold = 0.5

    def __init__(self):
        self.calls = []

    def status_metadata(self):
        return {
            "model_ids": ["fake/hate-a", "fake/hate-b"],
            "member_count": 2,
            "device": "cpu",
        }

    def score_texts_by_model(self, texts, *, batch_size):
        self.calls.append({"count": len(texts), "batch_size": batch_size})
        scores_a = [0.9 if "leave" in text else 0.1 for text in texts]
        scores_b = [0.7 if "leave" in text else 0.2 for text in texts]
        return {
            "fake/hate-a": scores_a,
            "fake/hate-b": scores_b,
        }


class FakeLocalLlmReview:
    def __init__(self, *, skip_all=False):
        self.calls = []
        self.skip_all = skip_all

    def status_metadata(self):
        return {
            "model_id": "fake-local-llm",
            "endpoint": "http://local.test/v1/chat/completions",
        }

    def review_texts(self, rows, *, batch_size, progress_callback=None):
        self.calls.append({"rows": rows, "batch_size": batch_size})
        reviews = []
        for row in rows:
            if self.skip_all:
                reviews.append(
                    LocalLlmRowReview(
                        row_id=row["id"],
                        label="",
                        hate=None,
                        hsd_reasons=(),
                        review_needed=True,
                        pii_suggestions=(),
                        parse_status="skipped",
                        error_class="FakeParseError",
                    )
                )
                continue
            hate = "leave" in row["text"]
            reviews.append(
                LocalLlmRowReview(
                    row_id=row["id"],
                    label="1" if hate else "0",
                    hate=hate,
                    hsd_reasons=("protected_target",) if hate else ("none",),
                    review_needed=hate,
                    pii_suggestions=(),
                    parse_status="ok",
                )
            )
        return LocalLlmReviewResult(
            rows=tuple(reviews),
            model_id="fake-local-llm",
            endpoint="http://local.test/v1/chat/completions",
            elapsed_seconds=0.01,
            request_count=1,
            fallback_count=0,
        )


def test_final_pipeline_preserves_exact_csv_and_writes_llm_sidecar(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    manifest_path = tmp_path / "manifest.json"
    audit_path = tmp_path / "audit.json"
    fake_runtime = FakeLocalLlmReview()
    write_rows(source, include_label=True)

    manifest = run_final_csv_pipeline(
        source,
        output,
        text_col="text",
        id_col="id",
        manifest_path=manifest_path,
        audit_path=audit_path,
        disabled_providers=["presidio", "scrubadub", "gliner"],
        disabled_models=["token_policy_ensemble", "semantic", "hsd_advisory"],
        llm_review="local_llm",
        local_llm_batch_size=4,
        model_factories={"local_llm": lambda _context: fake_runtime},
    )

    rows = read_rows(output)
    written_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert manifest == written_manifest
    assert list(rows[0]) == ["id", "text", "is_hate_speech"]
    assert [row["id"] for row in rows] == ["1", "2"]
    assert [row["is_hate_speech"] for row in rows] == [
        "gold-positive",
        "gold-negative",
    ]
    assert "[USER]" in rows[0]["text"]
    assert "[EMAIL]" in rows[0]["text"]
    assert "Muslims should leave" in rows[0]["text"]
    assert "mara@example.test" not in rows[0]["text"]
    assert manifest["artifact_type"] == "final_exact_csv"
    assert manifest["exact_format_submission"] is True
    assert manifest["columns"]["output_columns"] == ["id", "text", "is_hate_speech"]
    assert manifest["columns"]["classification_columns"] == []
    assert manifest["validation"]["valid"] is True
    classification = manifest["classification"]
    assert classification["backend"] == "local_llm"
    assert classification["status"] == "ok"
    assert classification["parse_count"] == 2
    assert classification["fallback_count"] == 0
    assert classification["prediction_counts"] == {"0": 1, "1": 1}
    assert classification["reason_tag_counts"] == {"none": 1, "protected_target": 1}
    assert classification["validated_pii_suggestion_counts"] == {
        "total": 0,
        "accepted_for_review": 0,
        "rejected": 0,
    }
    verification = manifest["stages"]["verification"]
    assert verification["local_llm_hsd_review"]["status"] == "ok"
    assert audit["summary"]["artifact_type"] == "final_exact_csv"
    assert audit["classification_reviews"][0]["label"] == "1"
    serialized = json.dumps(manifest)
    assert "mara@example.test" not in serialized


def test_sanitize_classify_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "sanitize-classify",
            "--input",
            "input.csv",
            "--output",
            "output.csv",
            "--text-col",
            "body",
            "--allow-model-download",
            "--hsd-advisory-model",
            "facebook/roberta-hate-speech-dynabench-r4-target",
            "--hsd-advisory-model",
            "cardiffnlp/twitter-roberta-base-hate-latest",
        ]
    )

    assert args.command == "sanitize-classify"
    assert args.text_col == "body"
    assert args.device == "cpu"
    assert args.hsd_advisory_models == [
        "facebook/roberta-hate-speech-dynabench-r4-target",
        "cardiffnlp/twitter-roberta-base-hate-latest",
    ]


def test_sanitize_classify_command_maps_local_llm_backend():
    parser = build_parser()

    args = parser.parse_args(
        [
            "sanitize-classify",
            "--input",
            "input.csv",
            "--output",
            "output.csv",
            "--hsd-classification-backend",
            "local-llm",
            "--progress",
        ]
    )

    assert args.hsd_classification_backend.replace("-", "_") == "local_llm"
    assert args.progress is True


def test_sanitize_classify_replaces_text_and_appends_predictions(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    manifest_path = tmp_path / "manifest.json"
    audit_path = tmp_path / "audit.json"
    fake_runtime = FakeHsdAdvisory()
    write_rows(source, include_label=True)

    manifest = run_sanitize_classify(
        source,
        output,
        text_col="text",
        id_col="id",
        manifest_path=manifest_path,
        audit_path=audit_path,
        disabled_providers=["presidio", "scrubadub", "gliner"],
        disabled_models=["token_policy_ensemble", "semantic"],
        max_model_batch_size=4,
        model_factories={"hsd_advisory": lambda _context: fake_runtime},
    )

    rows = read_rows(output)
    written_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert manifest == written_manifest
    assert list(rows[0]) == [
        "id",
        "text",
        "is_hate_speech",
        "predicted_is_hate_speech",
        "hate_speech_score",
        "hate_speech_model_count",
    ]
    assert rows[0]["is_hate_speech"] == "gold-positive"
    assert rows[0]["predicted_is_hate_speech"] == "1"
    assert rows[0]["hate_speech_score"] == "0.8000"
    assert rows[0]["hate_speech_model_count"] == "2"
    assert rows[1]["predicted_is_hate_speech"] == "0"
    assert "[USER]" in rows[0]["text"]
    assert "[EMAIL]" in rows[0]["text"]
    assert "mara@example.test" not in rows[0]["text"]
    assert manifest["classification"]["status"] == "ok"
    assert manifest["classification"]["model_count"] == 2
    assert manifest["classification"]["prediction_counts"] == {"0": 1, "1": 1}
    assert manifest["pipeline"] == "auto"
    assert manifest["preset"] == "analysis"
    assert set(manifest["stages"]) == {
        "privacy_detection",
        "meaning_protection",
        "verification",
    }
    assert manifest["stages"]["privacy_detection"]["pii_assist"]["label"] == (
        "PII Assist"
    )
    verification = manifest["stages"]["verification"]
    assert verification["hsd_advisory_status"] == "ok"
    assert verification["hsd_advisory"]["use"] == "analysis_prediction_columns"
    assert verification["hsd_advisory"]["model_count"] == 2
    assert verification["author_risk"]["author_or_user_column_exists"] is False
    assert manifest["sanitization"]["stages"]["verification"][
        "hsd_advisory_status"
    ] == "ok"
    assert manifest["tradeoff"]["identifier_count_after"] == 0
    assert manifest["tradeoff"]["classification_decision_changed_count"] == 0
    assert manifest["validation"]["valid"] is True
    assert audit["summary"]["artifact_type"] == "sanitize_classify_csv"
    serialized = json.dumps(manifest)
    assert "mara@example.test" not in serialized
    assert "Everyone deserves respect" not in serialized


def test_sanitize_classify_adds_default_label_col_when_missing(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    fake_runtime = FakeHsdAdvisory()
    write_rows(source, include_label=False)

    run_sanitize_classify(
        source,
        output,
        text_col="text",
        id_col="id",
        disabled_providers=["presidio", "scrubadub", "gliner"],
        disabled_models=["token_policy_ensemble", "semantic"],
        model_factories={"hsd_advisory": lambda _context: fake_runtime},
    )

    rows = read_rows(output)
    assert "is_hate_speech" in rows[0]
    assert rows[0]["is_hate_speech"] == "1"


def test_sanitize_classify_local_llm_receives_sanitized_text_only(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    fake_runtime = FakeLocalLlmReview()
    write_rows(source, include_label=False)

    manifest = run_sanitize_classify(
        source,
        output,
        text_col="text",
        id_col="id",
        disabled_providers=["presidio", "scrubadub", "gliner"],
        disabled_models=["token_policy_ensemble", "semantic", "hsd_advisory"],
        hsd_classification_backend="local_llm",
        local_llm_batch_size=3,
        model_factories={"local_llm": lambda _context: fake_runtime},
    )

    rows = read_rows(output)
    assert rows[0]["is_hate_speech"] == "1"
    assert rows[1]["is_hate_speech"] == "0"
    assert manifest["classification"]["backend"] == "local_llm"
    assert manifest["classification"]["model_id"] == "fake-local-llm"
    assert manifest["classification"]["parse_count"] == 2
    assert manifest["stages"]["verification"]["hsd_classification"]["backend"] == (
        "local_llm"
    )
    assert fake_runtime.calls[0]["batch_size"] == 3
    sent_texts = [row["text"] for row in fake_runtime.calls[0]["rows"]]
    assert all("mara@example.test" not in text for text in sent_texts)
    assert "[EMAIL]" in sent_texts[0]
    serialized = json.dumps(manifest)
    assert "mara@example.test" not in serialized


def test_sanitize_classify_local_llm_required_fails_on_parse_skip(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    write_rows(source, include_label=False)

    with pytest.raises(SimplifiedPipelineError, match="could not be parsed"):
        run_sanitize_classify(
            source,
            output,
            text_col="text",
            id_col="id",
            require_hate_classification=True,
            disabled_providers=["presidio", "scrubadub", "gliner"],
            disabled_models=["token_policy_ensemble", "semantic", "hsd_advisory"],
            hsd_classification_backend="local_llm",
            model_factories={
                "local_llm": lambda _context: FakeLocalLlmReview(skip_all=True)
            },
        )


def test_sanitize_classify_can_require_classifier(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    write_rows(source, include_label=False)

    with pytest.raises(SimplifiedPipelineError, match="required"):
        run_sanitize_classify(
            source,
            output,
            text_col="text",
            require_hate_classification=True,
            disabled_providers=["presidio", "scrubadub", "gliner"],
            disabled_models=[
                "token_policy_ensemble",
                "semantic",
                "hsd_advisory",
            ],
        )
