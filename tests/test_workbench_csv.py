import csv
import io
import json
import time

import pytest

pytest.importorskip("fastapi.testclient")

from fastapi.testclient import TestClient

from contextsafe_hsd.span_providers.base import (
    PRIVACY_CLASS_DIRECT,
    UTILITY_CLASS_NONE,
    SpanCandidate,
    SpanProviderOutput,
)
import workbench.backend.app as workbench_app
from workbench.backend.app import app, platform_insight_report


def test_platform_insight_uses_pipeline_hsd_advisory_without_label_columns():
    report = platform_insight_report(
        original_rows=[
            {
                "id": "1",
                "text": "Alex said Muslims should leave Boston.",
            }
        ],
        output_rows=[
            {
                "id": "1",
                "text": "[PERSON] said Muslims should leave [LOCATION].",
            }
        ],
        text_col="text",
        output_col="text",
        aggregate={"residual_identifier_count": 0},
        audit_rows=[
            {
                "chosen_candidate": "balanced",
                "scores": [
                    {
                        "name": "balanced",
                        "metrics": {
                            "hsd_advisory": {
                                "original_score": 0.92,
                                "candidate_score": 0.89,
                                "candidate_decision": "positive",
                                "decision_threshold": 0.5,
                            }
                        },
                    }
                ],
            }
        ],
    )

    assert report["classification"]["source"] == "pipeline_hsd_advisory"
    assert report["classification"]["classified_rows"] == 1
    assert report["classification"]["hatred_rows"] == 1
    assert report["classification"]["mean_hatred_score"] == 0.89
    assert report["target_groups"]["categories"]["religion"]["hatred_rows"] == 1
    assert report["ngo_review"]["routing_rule"] == "pipeline_hsd_advisory_positive"


def test_platform_insight_counts_positive_hsd_member_vote():
    report = platform_insight_report(
        original_rows=[
            {
                "id": "1",
                "text": "Refugees should be banned from town.",
            }
        ],
        output_rows=[
            {
                "id": "1",
                "text": "Refugees should be banned from town.",
            }
        ],
        text_col="text",
        output_col="text",
        aggregate={"residual_identifier_count": 0},
        audit_rows=[
            {
                "chosen_candidate": "balanced",
                "scores": [
                    {
                        "name": "balanced",
                        "metrics": {
                            "hsd_advisory": {
                                "original_score": 0.44,
                                "candidate_score": 0.48,
                                "candidate_max_score": 0.96,
                                "candidate_positive_model_count": 1,
                                "model_count": 2,
                                "candidate_decision": "negative",
                                "decision_threshold": 0.5,
                            }
                        },
                    }
                ],
            }
        ],
    )

    assert report["classification"]["hatred_rows"] == 1
    assert report["classification"]["mean_hatred_score"] == 0.96
    assert report["classification"]["total_positive_model_votes"] == 1
    assert report["classification"]["total_model_votes"] == 2
    assert (
        report["classification"]["model_vote_rule"]
        == "one_or_more_registered_hsd_models_positive"
    )


def test_platform_insight_builds_safeguard_cards_from_hsd_answer_labels():
    report = platform_insight_report(
        original_rows=[
            {
                "case_id": "case-1",
                "text": 'A user wrote "Muslims should leave" and I reported it.',
                "hsd_answer": "1",
            }
        ],
        output_rows=[
            {
                "case_id": "case-1",
                "text": 'A user wrote "Muslims should leave" and I reported it.',
                "hsd_answer": "1",
            }
        ],
        text_col="text",
        output_col="text",
        aggregate={"residual_identifier_count": 0},
        id_col="case_id",
    )

    assert report["classification"]["source"] == "csv_post_classification_columns"
    assert report["classification"]["label_column"] == "hsd_answer"
    assert report["classification"]["hatred_rows"] == 1
    item = report["ngo_review"]["queue_preview"][0]
    assert item["row_id"] == "case-1"
    assert item["privacy_leakage"]["status"] == "clear"
    assert item["context_preservation"]["components"]["target_group_reference"] == "preserved"
    assert item["safeguard"]["human_review"]["required"] is True
    assert item["safeguard"]["proportionate_response"]["auto_moderation"] is False
    assert report["safeguards"]["human_review_required_rows"] == 1


def test_platform_insight_keeps_full_review_queue_and_capped_preview():
    rows = [
        {
            "id": f"case-{index}",
            "text": "A report says Muslims should leave town.",
            "hsd_answer": "1",
        }
        for index in range(workbench_app.MAX_PREVIEW_ROWS + 5)
    ]

    report = platform_insight_report(
        original_rows=rows,
        output_rows=rows,
        text_col="text",
        output_col="text",
        aggregate={"residual_identifier_count": 0},
        id_col="id",
    )

    assert report["ngo_review"]["queue_rows"] == workbench_app.MAX_PREVIEW_ROWS + 5
    assert len(report["ngo_review"]["queue_items"]) == workbench_app.MAX_PREVIEW_ROWS + 5
    assert len(report["ngo_review"]["queue_preview"]) == workbench_app.MAX_PREVIEW_ROWS
    assert report["ngo_review"]["queue_items"][-1]["row_id"] == (
        f"case-{workbench_app.MAX_PREVIEW_ROWS + 4}"
    )


def test_workbench_csv_endpoint_returns_masked_csv_without_helper_when_replacing():
    client = TestClient(app)
    response = client.post(
        "/api/csv/privatize",
        json={
            "csv_text": (
                "id,text,predicted_is_hate_speech,hate_speech_score\n"
                "1,Email alex@example.test because Muslims should leave.,1,0.91\n"
            ),
            "text_col": "text",
            "id_col": "id",
            "mode": "auto",
            "replace_text": True,
            "disabled_providers": ["presidio", "scrubadub", "gliner"],
            "disabled_models": ["token_policy_ensemble", "semantic", "hsd_advisory"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    rows = list(csv.DictReader(io.StringIO(body["output_csv"])))
    assert list(rows[0]) == ["id", "text", "predicted_is_hate_speech", "hate_speech_score"]
    assert rows[0]["text"] == "Email [EMAIL] because Muslims should leave."
    assert body["audit"]["summary"]["validation"]["valid"] is True
    assert body["manifest"]["mode"] == "auto"
    assert body["manifest"]["columns"]["output_col"] == "text"
    insights = body["platform_insights"]
    assert insights["classification"]["label"] == "post_classification_hatred"
    assert insights["classification"]["hatred_rows"] == 1
    assert insights["classification"]["hatred_rate"] == 1.0
    assert insights["target_groups"]["categories"]["religion"]["hatred_rows"] == 1
    assert insights["ngo_review"]["auto_moderation"] is False


def test_workbench_csv_endpoint_persists_and_reuses_cached_result(tmp_path, monkeypatch):
    monkeypatch.setattr(workbench_app, "CSV_RESULT_CACHE_DIR", tmp_path / "csv_results")
    client = TestClient(workbench_app.app)
    payload = {
        "csv_text": "id,text\n1,Email alex@example.test because Muslims should leave.\n",
        "text_col": "text",
        "id_col": "id",
        "mode": "auto",
        "replace_text": True,
        "disabled_providers": ["presidio", "scrubadub", "gliner"],
        "disabled_models": ["token_policy_ensemble", "semantic", "hsd_advisory"],
    }

    first = client.post("/api/csv/privatize", json=payload)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["cache"]["hit"] is False

    lookup = client.post("/api/csv/cache", json=payload)
    assert lookup.status_code == 200
    lookup_body = lookup.json()
    assert lookup_body["cache_hit"] is True
    assert lookup_body["result"]["cache"]["hit"] is True
    assert lookup_body["result"]["output_csv"] == first_body["output_csv"]

    second = client.post("/api/csv/privatize", json=payload)
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["cache"]["hit"] is True
    assert second_body["output_csv"] == first_body["output_csv"]


def test_workbench_csv_job_reports_progress_and_result(tmp_path, monkeypatch):
    monkeypatch.setattr(workbench_app, "CSV_RESULT_CACHE_DIR", tmp_path / "csv_results")
    client = TestClient(workbench_app.app)
    payload = {
        "csv_text": (
            "id,text,predicted_is_hate_speech\n"
            "1,Email alex@example.test because Muslims should leave.,1\n"
            "2,Case note from Dana in Boston.,0\n"
        ),
        "text_col": "text",
        "id_col": "id",
        "mode": "auto",
        "replace_text": True,
        "disabled_providers": ["presidio", "scrubadub", "gliner"],
        "disabled_models": ["token_policy_ensemble", "semantic", "hsd_advisory"],
    }

    start = client.post("/api/csv/jobs", json=payload)
    assert start.status_code == 200
    start_body = start.json()
    assert start_body["job_id"]
    assert start_body["progress"]["value"] >= 0

    job = start_body
    for _attempt in range(50):
        if job["status"] == "complete":
            break
        time.sleep(0.05)
        poll = client.get(f"/api/csv/jobs/{start_body['job_id']}")
        assert poll.status_code == 200
        job = poll.json()
        assert "progress" in job
        assert 0 <= job["progress"]["value"] <= 100
    else:
        pytest.fail("CSV job did not complete")

    assert job["status"] == "complete"
    assert job["progress"]["value"] == 100
    assert job["progress"]["processed_rows"] == 2
    assert job["result"]["cache"]["hit"] is False
    assert job["result"]["manifest"]["row_count"] == 2


def test_workbench_review_annotations_persist_structured_feedback(tmp_path, monkeypatch):
    monkeypatch.setattr(workbench_app, "CSV_RESULT_CACHE_DIR", tmp_path / "csv_results")
    monkeypatch.setattr(workbench_app, "REVIEW_CACHE_DIR", tmp_path / "reviews")
    client = TestClient(workbench_app.app)
    payload = {
        "csv_text": (
            "id,text,predicted_is_hate_speech\n"
            "case-1,Email alex@example.test because Muslims should leave.,1\n"
        ),
        "text_col": "text",
        "id_col": "id",
        "mode": "auto",
        "replace_text": True,
        "disabled_providers": ["presidio", "scrubadub", "gliner"],
        "disabled_models": ["token_policy_ensemble", "semantic", "hsd_advisory"],
    }
    processed = client.post("/api/csv/privatize", json=payload)
    assert processed.status_code == 200
    cache_key = processed.json()["cache"]["key"]

    update = client.put(
        f"/api/reviews/{cache_key}/cases/case-1",
        json={
            "status": "escalated",
            "reviewer_id": "ngo-demo",
            "labels": {
                "final_hsd_label": "confirmed_hatred",
                "harm_risk": "high",
                "masking_quality": "acceptable",
                "pii_feedback": ["missed_location", "not_allowed"],
                "context_feedback": ["target_reference_preserved"],
                "target_categories": ["religion"],
            },
        },
    )
    assert update.status_code == 200
    body = update.json()
    case = body["cases"]["case-1"]
    assert case["status"] == "escalated"
    assert case["labels"]["pii_feedback"] == ["missed_location"]
    assert case["labels"]["target_categories"] == ["religion"]
    assert body["summary"]["status_counts"]["escalated"] == 1

    lookup = client.get(f"/api/reviews/{cache_key}")
    assert lookup.status_code == 200
    assert lookup.json()["cases"]["case-1"]["labels"]["harm_risk"] == "high"
    saved = json.loads((tmp_path / "reviews" / f"{cache_key}.json").read_text())
    saved_text = json.dumps(saved)
    assert "alex@example.test" not in saved_text
    assert "Muslims should leave" not in saved_text
    assert saved["cases"]["case-1"]["privacy"]["raw_text_retained"] is False


def test_workbench_text_endpoint_uses_selected_span_provider(monkeypatch):
    class FakeProvider:
        name = "presidio"

        def propose(self, text):
            return SpanProviderOutput(
                provider="presidio",
                spans=(
                    SpanCandidate(
                        start=0,
                        end=5,
                        text=text[:5],
                        entity_type="PERSON",
                        privacy_class=PRIVACY_CLASS_DIRECT,
                        utility_class=UTILITY_CLASS_NONE,
                        provider="presidio",
                        score=0.99,
                        explanation_code="PERSON",
                        metadata={"source": "presidio:PERSON"},
                    ),
                ),
                audit={"enabled": True, "accepted_span_count": 1},
            )

    monkeypatch.setattr(
        "workbench.backend.app.load_span_provider",
        lambda name: FakeProvider(),
    )
    client = TestClient(app)
    response = client.post(
        "/api/privatize",
        json={
            "text": "Alice said Muslims should leave.",
            "mode": "balanced",
            "providers": ["presidio"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["privatized_text"] == "[PERSON] said Muslims should leave."
    assert body["span_providers"]["presidio"]["status"] == "ready"
    assert body["span_providers"]["presidio"]["accepted_span_count"] == 1
    assert body["hsd_classifier"]["status"] == "not_requested"


def test_workbench_text_endpoint_can_return_hsd_classifier(monkeypatch):
    monkeypatch.setattr(
        "workbench.backend.app.run_hsd_classifier",
        lambda original, privatized: {
            "active": True,
            "available": True,
            "status": "ok",
            "model_id": "fake-hsd",
            "original_score": 0.9,
            "candidate_score": 0.88,
            "score_delta": -0.02,
            "original_decision": "positive",
            "candidate_decision": "positive",
        },
    )
    client = TestClient(app)
    response = client.post(
        "/api/privatize",
        json={
            "text": "Muslims should leave Boston.",
            "mode": "balanced",
            "run_hsd_classifier": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["hsd_classifier"]["status"] == "ok"
    assert body["hsd_classifier"]["model_id"] == "fake-hsd"
