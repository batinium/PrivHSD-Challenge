import csv
import json

import pytest

from contextsafe_hsd.cli import build_parser
from contextsafe_hsd.models.hf_hsd_classifier_runtime import (
    HfHsdClassifierResult,
    HfHsdClassifierRow,
)
from contextsafe_hsd.models.local_llm_hsd_review_runtime import (
    LocalLlmReviewResult,
    LocalLlmRowReview,
)
from contextsafe_hsd.models.local_llm_hsd_verifier_runtime import (
    LocalLlmVerifierResult,
    LocalLlmVerifierRow,
)
from contextsafe_hsd.simple_pipeline import (
    SimplifiedPipelineError,
    run_final_csv_pipeline,
)


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path):
    fieldnames = ["id", "text", "is_hate_speech"]
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
        writer.writerows(rows)


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


class FakeLocalLlmVerifier:
    def __init__(self):
        self.calls = []

    def verify_texts(self, rows, *, batch_size, progress_callback=None):
        self.calls.append({"rows": rows, "batch_size": batch_size})
        return LocalLlmVerifierResult(
            rows=tuple(
                LocalLlmVerifierRow(
                    row_id=row["id"],
                    decision="disagree",
                    suggested_label=False,
                    reason="no_protected_target",
                    parse_status="ok",
                    action="human_review_candidate",
                )
                for row in rows
            ),
            model_id="fake-verifier",
            endpoint="http://local.test/v1/chat/completions",
            prompt_style="current",
            elapsed_seconds=0.01,
            request_count=1,
            fallback_count=0,
        )


class FakeHfClassifier:
    def __init__(self):
        self.calls = []
        self.model_id = "fake-hf-hsd"

    def status_metadata(self):
        return {
            "model_id": self.model_id,
            "model_path": "fake/model",
            "threshold": 0.7,
            "max_length": 512,
            "device": "cpu",
        }

    def classify_texts(self, rows, *, batch_size, progress_callback=None):
        self.calls.append({"rows": rows, "batch_size": batch_size})
        reviews = []
        for row in rows:
            score = 0.91 if "leave" in row["text"] else 0.08
            hate = score >= 0.7
            reviews.append(
                HfHsdClassifierRow(
                    row_id=row["id"],
                    label="1" if hate else "0",
                    hate=hate,
                    score=score,
                    threshold=0.7,
                )
            )
        return HfHsdClassifierResult(
            rows=tuple(reviews),
            model_id=self.model_id,
            model_path="fake/model",
            threshold=0.7,
            max_length=512,
            device="cpu",
            elapsed_seconds=0.01,
        )


def test_protect_parser_is_small_and_defaults_to_deterministic_review():
    parser = build_parser()

    assert set(parser._subparsers._actions[1].choices) == {
        "protect",
        "template-after-baseline",
        "evidence-after-baseline",
        "backend-bundle",
        "validate-submission",
        "profile-dataset",
        "mini-verifier-eval",
    }
    args = parser.parse_args(
        [
            "protect",
            "--input",
            "input.csv",
            "--output",
            "output.csv",
            "--text-col",
            "body",
        ]
    )

    assert args.command == "protect"
    assert args.text_col == "body"
    assert args.llm_review == "off"
    assert args.llm_verifier == "off"
    assert args.hsd_classifier is None
    assert args.pii_assist is True
    assert args.candidate_selection is True
    assert args.style_simplify_language is False


def test_final_pipeline_preserves_exact_csv_and_writes_llm_sidecar(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    manifest_path = tmp_path / "manifest.json"
    audit_path = tmp_path / "audit.json"
    fake_runtime = FakeLocalLlmReview()
    write_rows(source)

    manifest = run_final_csv_pipeline(
        source,
        output,
        text_col="text",
        id_col="id",
        manifest_path=manifest_path,
        audit_path=audit_path,
        disabled_providers=["presidio", "scrubadub"],
        llm_review="local_llm",
        llm_verifier="off",
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
    assert "hsd_advisory" not in verification
    assert audit["summary"]["artifact_type"] == "final_exact_csv"
    assert audit["classification_reviews"][0]["label"] == "1"
    sent_texts = [row["text"] for row in fake_runtime.calls[0]["rows"]]
    assert all("mara@example.test" not in text for text in sent_texts)
    assert "[EMAIL]" in sent_texts[0]
    serialized = json.dumps(manifest)
    assert "mara@example.test" not in serialized


def test_final_pipeline_can_run_optional_second_verifier(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    manifest_path = tmp_path / "manifest.json"
    audit_path = tmp_path / "audit.json"
    fake_review = FakeLocalLlmReview()
    fake_verifier = FakeLocalLlmVerifier()
    write_rows(source)

    manifest = run_final_csv_pipeline(
        source,
        output,
        text_col="text",
        id_col="id",
        manifest_path=manifest_path,
        audit_path=audit_path,
        disabled_providers=["presidio", "scrubadub"],
        llm_review="local_llm",
        llm_verifier="local_llm",
        local_llm_batch_size=4,
        local_llm_verifier_batch_size=2,
        model_factories={
            "local_llm": lambda _context: fake_review,
            "local_llm_verifier": lambda _context: fake_verifier,
        },
    )

    rows = read_rows(output)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert list(rows[0]) == ["id", "text", "is_hate_speech"]
    assert manifest["llm_verifier"] == "local_llm"
    verifier = manifest["classification_verifier"]
    assert verifier["status"] == "ok"
    assert verifier["row_count"] == 1
    assert verifier["decision_counts"] == {"disagree": 1}
    assert verifier["human_review_candidate_count"] == 1
    assert verifier["label_override_applied"] is False
    assert manifest["stages"]["verification"]["local_llm_hsd_verifier"][
        "status"
    ] == "ok"
    assert fake_verifier.calls[0]["batch_size"] == 2
    assert [row["id"] for row in fake_verifier.calls[0]["rows"]] == ["1"]
    assert audit["verifier_reviews"][0]["action"] == "human_review_candidate"


def test_final_pipeline_can_use_hf_classifier_sidecar(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    manifest_path = tmp_path / "manifest.json"
    audit_path = tmp_path / "audit.json"
    fake_classifier = FakeHfClassifier()
    write_rows(source)

    manifest = run_final_csv_pipeline(
        source,
        output,
        text_col="text",
        id_col="id",
        manifest_path=manifest_path,
        audit_path=audit_path,
        disabled_providers=["presidio", "scrubadub"],
        hsd_classification_backend="hf_classifier",
        hf_hsd_batch_size=8,
        hf_hsd_threshold=0.7,
        llm_review="off",
        llm_verifier="off",
        model_factories={"hf_classifier": lambda _context: fake_classifier},
    )

    rows = read_rows(output)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    classification = manifest["classification"]
    assert list(rows[0]) == ["id", "text", "is_hate_speech"]
    assert classification["backend"] == "hf_classifier"
    assert classification["status"] == "ok"
    assert classification["parse_count"] == 2
    assert classification["prediction_counts"] == {"0": 1, "1": 1}
    assert classification["threshold"] == 0.7
    assert classification["row_reviews"][0]["score"] == 0.91
    assert manifest["hsd_classification_backend"] == "hf_classifier"
    assert manifest["llm_review"] == "off"
    assert manifest["stages"]["verification"]["hsd_classification"][
        "backend"
    ] == "hf_classifier"
    assert fake_classifier.calls[0]["batch_size"] == 8
    assert "mara@example.test" not in json.dumps(audit)


def test_final_pipeline_can_skip_local_llm_sidecar(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    write_rows(source)

    manifest = run_final_csv_pipeline(
        source,
        output,
        text_col="text",
        id_col="id",
        disabled_providers=["presidio", "scrubadub"],
        llm_review="off",
        llm_verifier="off",
    )

    assert manifest["llm_review"] == "off"
    assert manifest["classification"]["status"] == "skipped"
    assert manifest["classification"]["skip_reason"] == "disabled"
    assert read_rows(output)[0]["text"].count("[EMAIL]") == 1


def test_final_pipeline_fast_path_skips_candidate_selection_and_pii_assist(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    write_rows(source)

    manifest = run_final_csv_pipeline(
        source,
        output,
        text_col="text",
        id_col="id",
        disabled_providers=["presidio", "scrubadub"],
        candidate_selection=False,
        author_group_masking=False,
        hsd_classification_backend="none",
        llm_review="off",
        llm_verifier="off",
    )

    assert manifest["candidate_selection"] is False
    assert manifest["hsd_classification_backend"] == "none"
    assert manifest["providers"]["presidio"]["status"] == "disabled"
    assert manifest["providers"]["scrubadub"]["status"] == "disabled"
    assert manifest["sanitization"]["chosen_counts"] == {"balanced": 2}
    assert manifest["sanitization"]["stages"]["privacy_detection"][
        "candidate_counts_by_name"
    ] == {"balanced": 2}
    assert manifest["sanitization"]["stages"]["meaning_protection"][
        "candidate_count"
    ] == 2
    assert read_rows(output)[0]["text"].count("[EMAIL]") == 1


def test_final_pipeline_required_llm_fails_on_parse_skip(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    write_rows(source)

    with pytest.raises(SimplifiedPipelineError, match="could not be parsed"):
        run_final_csv_pipeline(
            source,
            output,
            text_col="text",
            id_col="id",
            require_hate_classification=True,
            disabled_providers=["presidio", "scrubadub"],
            llm_review="local_llm",
            llm_verifier="off",
            model_factories={
                "local_llm": lambda _context: FakeLocalLlmReview(skip_all=True)
            },
        )
