import csv
import io

import pytest

pytest.importorskip("fastapi.testclient")

from fastapi.testclient import TestClient

from contextsafe_hsd.span_providers.base import (
    PRIVACY_CLASS_DIRECT,
    UTILITY_CLASS_NONE,
    SpanCandidate,
    SpanProviderOutput,
)
from workbench.backend.app import app


def test_workbench_csv_endpoint_returns_masked_csv_without_helper_when_replacing():
    client = TestClient(app)
    response = client.post(
        "/api/csv/privatize",
        json={
            "csv_text": (
                "id,text,label\n"
                "1,Email alex@example.test because Muslims should leave.,hate\n"
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
    assert list(rows[0]) == ["id", "text", "label"]
    assert rows[0]["text"] == "Email [EMAIL] because Muslims should leave."
    assert body["audit"]["summary"]["validation"]["valid"] is True
    assert body["manifest"]["mode"] == "auto"
    assert body["manifest"]["columns"]["output_col"] == "text"


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
