import csv
import io

import pytest

pytest.importorskip("fastapi.testclient")

from fastapi.testclient import TestClient

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
