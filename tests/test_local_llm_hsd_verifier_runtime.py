import json

from contextsafe_hsd.models.local_llm_hsd_verifier_runtime import (
    LocalLlmHsdVerifierRuntime,
)


def tool_response(items):
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "record_hsd_verifier",
                                "arguments": json.dumps({"items": items}),
                            }
                        }
                    ]
                }
            }
        ]
    }


def verifier_item(row_id, *, decision="agree", suggested_label=True, reason="other"):
    return {
        "id": row_id,
        "decision": decision,
        "suggested_label": suggested_label,
        "reason": reason,
    }


def test_verifier_uses_required_tool_calling_and_validates_batch_items():
    requests = []

    def fake_request(payload, _timeout):
        requests.append(payload)
        rows = json.loads(payload["messages"][1]["content"])["items"]
        return tool_response([verifier_item(row["id"]) for row in rows])

    runtime = LocalLlmHsdVerifierRuntime(
        endpoint="http://local.test/v1/chat/completions",
        model_id="fake-verifier",
        request_callable=fake_request,
    )

    result = runtime.verify_texts(
        [
            {"id": "1", "text": "Muslims should leave."},
            {"id": "2", "text": "Jews should leave."},
        ],
        batch_size=2,
    )

    assert result.parsed_count == 2
    assert result.fallback_count == 0
    assert requests[0]["tool_choice"] == "required"
    assert requests[0]["tools"][0]["function"]["name"] == "record_hsd_verifier"


def test_verifier_retries_malformed_batch_per_row():
    requests = []

    def fake_request(payload, _timeout):
        requests.append(payload)
        rows = json.loads(payload["messages"][1]["content"])["items"]
        if len(requests) == 1:
            return tool_response([verifier_item(rows[0]["id"])])
        return tool_response([verifier_item(rows[0]["id"])])

    runtime = LocalLlmHsdVerifierRuntime(
        endpoint="http://local.test/v1/chat/completions",
        model_id="fake-verifier",
        request_callable=fake_request,
    )

    result = runtime.verify_texts(
        [
            {"id": "1", "text": "Muslims should leave."},
            {"id": "2", "text": "Jews should leave."},
        ],
        batch_size=2,
    )

    assert result.parsed_count == 2
    assert result.fallback_count == 2
    assert result.request_count == 3
    assert [row.row_id for row in result.rows] == ["1", "2"]
