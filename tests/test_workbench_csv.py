import csv
import io
import json
import re
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


def test_platform_insight_without_label_columns_is_unclassified():
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
    )

    assert report["classification"]["source"] == "not_classified"
    assert report["classification"]["classified_rows"] == 0
    assert report["classification"]["hatred_rows"] == 0
    assert report["classification"]["mean_hatred_score"] is None
    assert report["target_groups"]["categories"]["religion"]["hatred_rows"] == 0
    assert report["citizen_jury"]["routing_rule"] == "not_classified"
    assert report["citizen_jury"]["queue_rows"] == 0


def test_platform_insight_does_not_classify_from_audit_candidate_scores():
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
                        "metrics": {"privacy_gain": 1.0},
                    }
                ],
            }
        ],
    )

    assert report["classification"]["source"] == "not_classified"
    assert report["classification"]["hatred_rows"] == 0
    assert report["classification"]["mean_hatred_score"] is None
    assert report["classification"]["total_positive_model_votes"] == 0
    assert report["classification"]["total_model_votes"] == 0
    assert report["classification"]["model_vote_rule"] is None


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
        citizen_restatements={
            "case-1": {
                "text": 'A user wrote "Muslims should leave" and I reported it.',
                "parse_status": "ok",
                "semantic_similarity": {
                    "backend": "off",
                    "status": "skipped",
                    "score": None,
                },
            }
        },
    )

    assert report["classification"]["source"] == "csv_post_classification_columns"
    assert report["classification"]["label_column"] == "hsd_answer"
    assert report["classification"]["hatred_rows"] == 1
    item = report["citizen_jury"]["queue_preview"][0]
    assert item["row_id"] == "case-1"
    assert item["citizen_restatement"] == (
        'A user wrote "Muslims should leave" and I reported it.'
    )
    assert item["citizen_validation"]["raw_text_retained"] is False
    assert item["privacy_leakage"]["status"] == "clear"
    assert item["context_preservation"]["components"]["target_group_reference"] == "preserved"
    assert item["safeguard"]["human_review"]["required"] is True
    assert item["safeguard"]["proportionate_response"]["auto_moderation"] is False
    assert report["safeguards"]["human_review_required_rows"] == 1
    assert report["citizen_jury"]["citizen_validation"]["enabled"] is True


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

    assert report["citizen_jury"]["queue_rows"] == workbench_app.MAX_PREVIEW_ROWS + 5
    assert len(report["citizen_jury"]["queue_items"]) == workbench_app.MAX_PREVIEW_ROWS + 5
    assert len(report["citizen_jury"]["queue_preview"]) == workbench_app.MAX_PREVIEW_ROWS
    assert report["citizen_jury"]["queue_items"][-1]["row_id"] == (
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
            "disabled_providers": ["presidio", "scrubadub"],
            "disabled_models": ["local_llm"],
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
    assert insights["citizen_jury"]["auto_moderation"] is False


def test_workbench_csv_endpoint_does_not_require_case_key(tmp_path, monkeypatch):
    monkeypatch.setattr(workbench_app, "CSV_RESULT_CACHE_DIR", tmp_path / "csv_results")
    client = TestClient(workbench_app.app)
    response = client.post(
        "/api/csv/privatize",
        json={
            "csv_text": (
                "text,predicted_is_hate_speech\n"
                "Email alex@example.test because Muslims should leave.,1\n"
            ),
            "text_col": "text",
            "mode": "auto",
            "replace_text": True,
            "disabled_providers": ["presidio", "scrubadub"],
            "disabled_models": ["local_llm"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    rows = list(csv.DictReader(io.StringIO(body["output_csv"])))
    assert list(rows[0]) == ["text", "predicted_is_hate_speech"]
    assert body["manifest"]["columns"]["id_col"] is None
    assert body["manifest"]["columns"]["review_id_col"] is None
    assert body["manifest"]["columns"]["review_id_synthetic"] is True
    assert re.fullmatch(r"case-[0-9a-f]{24}", body["preview_rows"][0]["row_id"])


def test_workbench_csv_uses_safe_fingerprint_as_review_case_key(tmp_path, monkeypatch):
    monkeypatch.setattr(workbench_app, "CSV_RESULT_CACHE_DIR", tmp_path / "csv_results")
    client = TestClient(workbench_app.app)
    fingerprint = "fp_" + ("a" * 32)
    response = client.post(
        "/api/csv/privatize",
        json={
            "csv_text": (
                "case_fingerprint,text,predicted_is_hate_speech\n"
                f"{fingerprint},Email alex@example.test because Muslims should leave.,1\n"
            ),
            "text_col": "text",
            "id_col": "case_fingerprint",
            "mode": "auto",
            "replace_text": True,
            "disabled_providers": ["presidio", "scrubadub"],
            "disabled_models": ["local_llm"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["manifest"]["columns"]["id_col"] == "case_fingerprint"
    assert body["manifest"]["columns"]["review_id_col"] == "case_fingerprint"
    assert body["manifest"]["columns"]["review_id_synthetic"] is False
    assert (
        body["manifest"]["columns"]["review_id_strategy"]
        == "input_privacy_safe_case_key"
    )
    assert body["preview_rows"][0]["row_id"] == fingerprint
    assert body["audit"]["rows"][0]["row_id"] == fingerprint
    review_item = body["platform_insights"]["citizen_jury"]["queue_items"][0]
    assert review_item["row_id"] == fingerprint
    review_rows = list(csv.DictReader(io.StringIO(body["review_csv"])))
    assert review_rows[0]["case_id"] == fingerprint
    assert "citizen_evidence" in review_rows[0]
    assert "protected_text" not in review_rows[0]


def test_workbench_rejects_duplicate_fingerprints_for_review_case_keys():
    fingerprint = "fp_" + ("b" * 32)
    rows = [
        {"case_fingerprint": fingerprint, "text": "First comment"},
        {"case_fingerprint": fingerprint, "text": "Second comment"},
    ]

    processed_rows, processing_id_col, synthetic, strategy = (
        workbench_app.review_id_processing_rows(
            rows,
            id_col="case_fingerprint",
            text_col="text",
        )
    )

    assert processing_id_col == workbench_app.REVIEW_CASE_ID_COLUMN
    assert synthetic is True
    assert strategy == "hmac_sha256_row_text"
    assert processed_rows[0][processing_id_col] != processed_rows[1][processing_id_col]


def test_workbench_csv_uses_synthetic_review_ids_for_author_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(workbench_app, "CSV_RESULT_CACHE_DIR", tmp_path / "csv_results")
    client = TestClient(workbench_app.app)
    response = client.post(
        "/api/csv/privatize",
        json={
            "csv_text": (
                "author_id,text,predicted_is_hate_speech\n"
                "author-secret-1,Email alex@example.test because Muslims should leave.,1\n"
            ),
            "text_col": "text",
            "id_col": "author_id",
            "mode": "auto",
            "replace_text": True,
            "disabled_providers": ["presidio", "scrubadub"],
            "disabled_models": ["local_llm"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    rows = list(csv.DictReader(io.StringIO(body["output_csv"])))
    assert rows[0]["author_id"] == "author-secret-1"
    assert body["manifest"]["columns"]["id_col"] == "author_id"
    assert body["manifest"]["columns"]["review_id_col"] is None
    assert body["manifest"]["columns"]["review_id_synthetic"] is True
    assert (
        body["manifest"]["columns"]["review_id_strategy"]
        == "hmac_sha256_row_text"
    )
    assert re.fullmatch(r"case-[0-9a-f]{24}", body["preview_rows"][0]["row_id"])
    review_item = body["platform_insights"]["citizen_jury"]["queue_items"][0]
    assert review_item["row_id"] == body["preview_rows"][0]["row_id"]
    review_rows = list(csv.DictReader(io.StringIO(body["review_csv"])))
    assert list(review_rows[0]) == [
        "case_id",
        "citizen_evidence",
        "evidence_source",
        "restatement_status",
        "semantic_similarity_score",
        "semantic_similarity_status",
    ]
    assert review_rows[0]["case_id"] == body["preview_rows"][0]["row_id"]
    assert review_rows[0]["citizen_evidence"] == ""
    assert "author-secret-1" not in json.dumps(body["platform_insights"])
    assert "author-secret-1" not in json.dumps(body["audit"])
    assert "author-secret-1" not in body["review_csv"]


def test_workbench_csv_endpoint_persists_and_reuses_cached_result(tmp_path, monkeypatch):
    monkeypatch.setattr(workbench_app, "CSV_RESULT_CACHE_DIR", tmp_path / "csv_results")
    client = TestClient(workbench_app.app)
    payload = {
        "csv_text": "id,text\n1,Email alex@example.test because Muslims should leave.\n",
        "text_col": "text",
        "id_col": "id",
        "mode": "auto",
        "replace_text": True,
        "disabled_providers": ["presidio", "scrubadub"],
        "disabled_models": ["local_llm"],
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

    recent = client.get("/api/csv/cache/recent")
    assert recent.status_code == 200
    recent_body = recent.json()
    assert recent_body["version"] == workbench_app.CSV_CACHE_VERSION
    assert recent_body["items"]
    summary = recent_body["items"][0]
    assert summary["cache_key"] == first_body["cache"]["key"]
    assert summary["row_count"] == 1
    assert summary["text_col"] == "text"
    assert summary["id_col"] == "id"
    assert summary["review_queue_rows"] == 0
    assert "csv_text" not in json.dumps(summary)
    assert "alex@example.test" not in json.dumps(summary)

    loaded = client.get(f"/api/csv/cache/{first_body['cache']['key']}")
    assert loaded.status_code == 200
    loaded_body = loaded.json()
    assert loaded_body["cache"]["hit"] is True
    assert loaded_body["output_csv"] == first_body["output_csv"]

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
        "disabled_providers": ["presidio", "scrubadub"],
        "disabled_models": ["local_llm"],
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
        "disabled_providers": ["presidio", "scrubadub"],
        "disabled_models": ["local_llm"],
    }
    processed = client.post("/api/csv/privatize", json=payload)
    assert processed.status_code == 200
    processed_body = processed.json()
    cache_key = processed_body["cache"]["key"]
    review_row_id = processed_body["platform_insights"]["citizen_jury"]["queue_items"][0][
        "row_id"
    ]
    assert re.fullmatch(r"case-[0-9a-f]{24}", review_row_id)

    update = client.put(
        f"/api/reviews/{cache_key}/cases/{review_row_id}",
        json={
            "status": "escalated",
            "reviewer_id": "citizen-demo",
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
    case = body["cases"][review_row_id]
    assert case["status"] == "escalated"
    assert case["labels"]["pii_feedback"] == ["missed_location"]
    assert case["labels"]["target_categories"] == ["religion"]
    assert body["summary"]["status_counts"]["escalated"] == 1

    lookup = client.get(f"/api/reviews/{cache_key}")
    assert lookup.status_code == 200
    assert lookup.json()["cases"][review_row_id]["labels"]["harm_risk"] == "high"
    saved = json.loads((tmp_path / "reviews" / f"{cache_key}.json").read_text())
    saved_text = json.dumps(saved)
    assert "alex@example.test" not in saved_text
    assert "Muslims should leave" not in saved_text
    assert saved["cases"][review_row_id]["privacy"]["raw_text_retained"] is False


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
    assert body["privatized_text"] == "[PERSON] said muslims should leave."
    assert body["span_providers"]["presidio"]["status"] == "ready"
    assert body["span_providers"]["presidio"]["accepted_span_count"] == 1
    assert body["hsd_classifier"]["status"] == "removed"


def test_workbench_csv_cache_key_includes_hsd_backend_options():
    base = workbench_app.CsvPrivatizeRequest(
        csv_text="id,text\n1,hello\n",
        text_col="text",
        id_col="id",
        disabled_models=["local_llm"],
    )
    local = workbench_app.CsvPrivatizeRequest(
        csv_text="id,text\n1,hello\n",
        text_col="text",
        id_col="id",
        disabled_models=["local_llm"],
        hsd_classification_backend="local_llm",
        local_llm_model="fake-local-llm",
    )

    base_key, base_options = workbench_app.csv_result_cache_key(base)
    local_key, local_options = workbench_app.csv_result_cache_key(local)

    assert base_key != local_key
    assert base_options["hsd_classification_backend"] == "none"
    assert local_options["hsd_classification_backend"] == "local_llm"
    assert local_options["hsd_verifier_backend"] == "local_llm"
    assert "local_llm" not in local_options["disabled_models"]


def test_workbench_csv_endpoint_can_select_local_llm_review(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(workbench_app, "CSV_RESULT_CACHE_DIR", tmp_path / "csv_results")

    seen_payloads = []

    def fake_post_chat_completion(*, endpoint, payload, timeout):
        seen_payloads.append(
            {
                "endpoint": endpoint,
                "payload": payload,
                "timeout": timeout,
            }
        )
        schema_name = payload.get("response_format", {}).get("json_schema", {}).get(
            "name"
        )
        if schema_name == "citizen_review_restatement":
            content = payload["messages"][1]["content"]
            assert "alex@example.test" not in content
            rows = json.loads(content)["items"]
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "items": [
                                        {
                                            "id": rows[0]["id"],
                                            "restatement": (
                                                "A person used a contact address while "
                                                "saying Muslims should leave."
                                            ),
                                            "safety_notes": "No raw identifier included.",
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ]
            }
        tool_name = (
            payload.get("tools", [{}])[0]
            .get("function", {})
            .get("name")
        )
        if tool_name == "record_hsd_verifier":
            content = payload["messages"][1]["content"]
            assert "alex@example.test" not in content
            rows = json.loads(content)["items"]
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "record_hsd_verifier",
                                        "arguments": json.dumps(
                                            {
                                                "items": [
                                                    {
                                                        "id": rows[0]["id"],
                                                        "decision": "agree",
                                                        "suggested_label": True,
                                                        "reason": "protected_identity_attack",
                                                    }
                                                ]
                                            }
                                        ),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        content = payload["messages"][1]["content"]
        assert "alex@example.test" not in content
        rows = json.loads(content)["items"]
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "record_hsd_review",
                                    "arguments": json.dumps(
                                        {
                                            "items": [
                                                {
                                                    "id": rows[0]["id"],
                                                    "hate": True,
                                                    "hsd_reasons": [
                                                        "protected_target",
                                                        "exclusion",
                                                    ],
                                                    "pii_leftover": [
                                                        "[EMAIL]",
                                                        "Muslims",
                                                    ],
                                                    "review_needed": True,
                                                }
                                            ]
                                        }
                                    ),
                                }
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(
        "contextsafe_hsd.models.local_llm_hsd_review_runtime.post_chat_completion",
        fake_post_chat_completion,
    )
    monkeypatch.setattr(
        "contextsafe_hsd.models.local_llm_hsd_verifier_runtime.post_chat_completion",
        fake_post_chat_completion,
    )
    monkeypatch.setattr(
        "workbench.backend.app.post_chat_completion",
        fake_post_chat_completion,
    )
    client = TestClient(workbench_app.app)
    response = client.post(
        "/api/csv/privatize",
        json={
            "csv_text": (
                "id,text\n"
                "1,Email alex@example.test because Muslims should leave.\n"
            ),
            "text_col": "text",
            "id_col": "id",
            "mode": "auto",
            "replace_text": True,
            "disabled_providers": ["presidio", "scrubadub"],
            "disabled_models": ["local_llm"],
            "hsd_classification_backend": "local_llm",
            "local_llm_endpoint": "http://local.test/v1/chat/completions",
            "local_llm_model": "fake-local-llm",
            "local_llm_batch_size": 2,
            "citizen_restatement_backend": "local_llm",
            "citizen_restatement_model": "fake-restater",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert seen_payloads
    output_rows = list(csv.DictReader(io.StringIO(body["output_csv"])))
    assert "__contextsafe_hsd_label" not in output_rows[0]
    assert "alex@example.test" not in output_rows[0]["text"]
    classification = body["manifest"]["classification"]
    assert classification["backend"] == "local_llm"
    assert classification["model_id"] == "fake-local-llm"
    assert classification["parse_count"] == 1
    assert classification["pii_suggestion_status_counts"] == {
        "rejected_placeholder": 1,
        "rejected_protected_or_hsd_cue": 1,
    }
    insights = body["platform_insights"]
    assert insights["classification"]["source"] == "local_llm_hsd_review"
    assert insights["classification"]["reason_tag_counts"] == {
        "exclusion": 1,
        "protected_target": 1,
    }
    queue_item = insights["citizen_jury"]["queue_items"][0]
    assert queue_item["hsd_backend"] == "local_llm"
    assert queue_item["hsd_reasons"] == ["protected_target", "exclusion"]
    assert queue_item["verifier_decision"] == "agree"
    assert queue_item["pii_suggestion_count"] == 2
    assert "contact address" in queue_item["citizen_evidence"]
    assert "alex@example.test" not in queue_item["citizen_evidence"]
    assert body["manifest"]["citizen_validation"]["enabled"] is True
    assert body["manifest"]["citizen_validation"]["restatement_model"] == "fake-restater"
    assert body["manifest"]["classification_verifier"]["status"] == "ok"
    serialized_review = json.dumps(
        body["platform_insights"]["citizen_jury"]["queue_items"]
    )
    assert "alex@example.test" not in serialized_review
    serialized_classification = json.dumps(classification)
    assert "[EMAIL]" not in serialized_classification
