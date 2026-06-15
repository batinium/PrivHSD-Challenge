import json

from contextsafe_hsd.models.local_llm_hsd_review_runtime import (
    LOCAL_LLM_HSD_SYSTEM_PROMPT,
    LocalLlmHsdReviewRuntime,
)


def tool_response(items):
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "record_hsd_review",
                                "arguments": json.dumps({"items": items}),
                            }
                        }
                    ]
                }
            }
        ]
    }


def content_response(items):
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps({"items": items}),
                }
            }
        ]
    }


def review_item(row_id, *, hate):
    return {
        "id": row_id,
        "hate": hate,
        "hsd_reasons": ["protected_target"] if hate else ["none"],
        "pii_leftover": [],
        "review_needed": hate,
    }


def test_tool_call_response_parses_labels_and_reason_tags():
    def fake_request(_payload, _timeout):
        return tool_response([review_item("row-1", hate=True)])

    runtime = LocalLlmHsdReviewRuntime(
        endpoint="http://local.test/v1/chat/completions",
        model_id="fake-model",
        request_callable=fake_request,
    )

    result = runtime.review_texts(
        [{"id": "row-1", "text": "Muslims should leave."}],
        batch_size=10,
    )

    assert result.status == "ok"
    assert result.parsed_count == 1
    assert result.rows[0].label == "1"
    assert result.rows[0].hsd_reasons == ("protected_target",)
    assert result.summary()["reason_tag_counts"] == {"protected_target": 1}


def test_malformed_batch_retries_per_row():
    calls = []

    def fake_request(payload, _timeout):
        calls.append(payload)
        if len(calls) == 1:
            return {"choices": [{"message": {"content": "not json"}}]}
        rows = json.loads(payload["messages"][1]["content"])["items"]
        return content_response([review_item(rows[0]["id"], hate=rows[0]["id"] == "1")])

    runtime = LocalLlmHsdReviewRuntime(
        endpoint="http://local.test/v1/chat/completions",
        model_id="fake-model",
        request_callable=fake_request,
    )

    result = runtime.review_texts(
        [
            {"id": "1", "text": "Muslims should leave."},
            {"id": "2", "text": "Everyone deserves respect."},
        ],
        batch_size=2,
    )

    assert result.status == "ok"
    assert result.fallback_count == 2
    assert result.request_count == 3
    assert [row.label for row in result.rows] == ["1", "0"]


def test_unparseable_individual_rows_are_skipped():
    def fake_request(_payload, _timeout):
        return {"choices": [{"message": {"content": "not json"}}]}

    runtime = LocalLlmHsdReviewRuntime(
        endpoint="http://local.test/v1/chat/completions",
        model_id="fake-model",
        request_callable=fake_request,
    )

    result = runtime.review_texts(
        [
            {"id": "1", "text": "Muslims should leave."},
            {"id": "2", "text": "Everyone deserves respect."},
        ],
        batch_size=2,
    )

    assert result.status == "skipped"
    assert result.parsed_count == 0
    assert result.skipped_count == 2
    assert {row.parse_status for row in result.rows} == {"skipped"}


def test_runtime_sends_cleaned_text_only_to_request_callable():
    seen_payloads = []

    def fake_request(payload, _timeout):
        seen_payloads.append(payload)
        content = payload["messages"][1]["content"]
        assert "alex@example.test" not in content
        return content_response([review_item("row-1", hate=True)])

    runtime = LocalLlmHsdReviewRuntime(
        endpoint="http://local.test/v1/chat/completions",
        model_id="fake-model",
        request_callable=fake_request,
    )

    runtime.review_texts(
        [{"id": "row-1", "text": "Email [EMAIL] because Muslims should leave."}],
        batch_size=1,
    )

    assert seen_payloads


def test_system_prompt_preserves_context_and_endorsement_guardrails():
    prompt = LOCAL_LLM_HSD_SYSTEM_PROMPT.lower()

    assert "endorses" in prompt
    assert "quotations" in prompt
    assert "reports" in prompt
    assert "counterspeech" in prompt
    assert "without endorsing" in prompt


def test_runtime_uses_required_tool_choice_and_json_schema_fallback():
    seen_payloads = []

    def fake_request(payload, _timeout):
        seen_payloads.append(payload)
        if len(seen_payloads) == 1:
            return {"choices": [{"message": {"content": "not json"}}]}
        assert "tools" not in payload
        return content_response([review_item("row-1", hate=False)])

    runtime = LocalLlmHsdReviewRuntime(
        endpoint="http://local.test/v1/chat/completions",
        model_id="fake-model",
        request_callable=fake_request,
        require_structured_output=False,
    )

    result = runtime.review_texts(
        [{"id": "row-1", "text": "Everyone deserves respect."}],
        batch_size=1,
    )

    assert result.status == "ok"
    assert seen_payloads[0]["tool_choice"] == "required"
    assert seen_payloads[1]["response_format"]["type"] == "json_schema"
    assert seen_payloads[1]["response_format"]["json_schema"]["name"] == "hsd_review"
    assert (
        seen_payloads[1]["response_format"]["json_schema"]["schema"]["required"]
        == ["items"]
    )
