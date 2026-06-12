import csv
import io
import json
from urllib import error

from privhsd.cli import build_parser
from privhsd.local_llm import (
    LocalLlmError,
    post_chat_completion,
    response_text,
    run_local_llm_candidates,
)


def write_rows(path):
    rows = [
        ("1", "REFUGEES dooo NOOOT belong here!!!! #MyTag", "hate"),
        ("2", "Everyone deserves respect.", "nothate"),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "label"])
        writer.writerows(rows)


def write_mixed_rows(path):
    rows = [
        ("1", "First hate row from @one about Muslims.", "hate", "a"),
        ("2", "Second hate row from @two about refugees.", "hate", "a"),
        ("3", "First not-hate row from @three.", "not_hate", "a"),
        ("4", "First toxic row from @four.", "toxic", "b"),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "label", "source"])
        writer.writerows(rows)


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_generate_llm_candidates_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "generate-llm-candidates",
            "--input",
            "input.csv",
            "--output",
            "output.csv",
            "--text-col",
            "text",
        ]
    )

    assert args.command == "generate-llm-candidates"
    assert args.candidate_col == "llm_candidate"


def test_local_llm_candidate_generation_accepts_schema_checked_candidate(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.csv"
    output = tmp_path / "candidates.csv"
    report = tmp_path / "report.json"
    write_rows(source)

    def fake_post(**_kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "privatized_text": "refugees do not belong here!",
                                "preserved_cues": ["refugees", "do not belong"],
                                "notes": "style normalized",
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("privhsd.local_llm.post_chat_completion", fake_post)

    result = run_local_llm_candidates(
        source,
        output,
        text_col="text",
        id_col="id",
        report_path=report,
        sample_size=1,
    )

    rows = read_rows(output)
    written = json.loads(report.read_text(encoding="utf-8"))
    assert result == written
    assert result["status"] == "ok"
    assert result["detail"] is None
    assert result["accepted_count"] == 1
    assert result["status_counts"] == {"accepted": 1}
    assert rows[0]["llm_candidate"] == "refugees do not belong here!"
    assert rows[1]["llm_candidate"] == ""
    assert result["rows"][0]["status"] == "accepted"
    assert "text" not in result["rows"][0]


def test_local_llm_candidate_generation_can_sample_source_label_round_robin(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.csv"
    output = tmp_path / "candidates.csv"
    write_mixed_rows(source)
    requested_texts = []

    def fake_post(**kwargs):
        payload = json.loads(kwargs["messages"][1]["content"])
        requested_texts.append(payload["text"])
        assert payload["metadata"]["source"]
        assert payload["metadata"]["label"]
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "privatized_text": payload["text"].replace("@", ""),
                                "preserved_cues": [],
                                "notes": "handle normalized",
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("privhsd.local_llm.post_chat_completion", fake_post)

    result = run_local_llm_candidates(
        source,
        output,
        text_col="text",
        id_col="id",
        source_col="source",
        label_col="label",
        sample_size=3,
    )

    rows = read_rows(output)
    assert result["sample"]["strategy"] == "source_label_round_robin"
    assert result["accepted_count"] == 3
    assert len(requested_texts) == 3
    assert rows[0]["llm_candidate"]
    assert rows[2]["llm_candidate"]
    assert rows[3]["llm_candidate"]
    assert rows[1]["llm_candidate"] == ""


def test_local_llm_candidate_generation_skips_when_endpoint_fails(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.csv"
    output = tmp_path / "candidates.csv"
    write_rows(source)

    def fake_post(**_kwargs):
        raise LocalLlmError("endpoint unavailable")

    monkeypatch.setattr("privhsd.local_llm.post_chat_completion", fake_post)

    result = run_local_llm_candidates(
        source,
        output,
        text_col="text",
        id_col="id",
        sample_size=1,
    )

    rows = read_rows(output)
    assert result["status"] == "skipped"
    assert result["skip_reason"] == "no_accepted_candidates"
    assert result["detail"] == "endpoint unavailable"
    assert result["first_error"] == "endpoint unavailable"
    assert result["status_counts"] == {"failed": 1}
    assert result["rows"][0]["status"] == "failed"
    assert rows[0]["llm_candidate"] == ""


def test_local_llm_candidate_generation_rejects_cue_loss(monkeypatch, tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "candidates.csv"
    write_rows(source)

    def fake_post(**_kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "privatized_text": "everyone should leave",
                                "preserved_cues": [],
                                "notes": "bad rewrite",
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("privhsd.local_llm.post_chat_completion", fake_post)

    result = run_local_llm_candidates(
        source,
        output,
        text_col="text",
        id_col="id",
        sample_size=1,
    )

    rows = read_rows(output)
    assert result["status"] == "skipped"
    assert result["rows"][0]["status"] == "rejected_by_checks"
    assert "target_cue_loss" in result["rows"][0]["checks"]["reasons"]
    assert result["status_counts"] == {"rejected_by_checks": 1}
    assert rows[0]["llm_candidate"] == ""


def test_local_llm_candidate_generation_rejects_negation_loss(monkeypatch, tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "candidates.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "label"])
        writer.writerow(["1", "Do not attack Muslims.", "not_hate"])

    def fake_post(**_kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "privatized_text": "attack Muslims.",
                                "preserved_cues": ["Muslims"],
                                "notes": "bad negation loss",
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("privhsd.local_llm.post_chat_completion", fake_post)

    result = run_local_llm_candidates(
        source,
        output,
        text_col="text",
        id_col="id",
        sample_size=1,
    )

    assert result["rows"][0]["status"] == "rejected_by_checks"
    assert "negation_modality_loss" in result["rows"][0]["checks"]["reasons"]


def test_response_text_extracts_json_from_lm_studio_markers():
    response = {
        "choices": [
            {
                "message": {
                    "content": (
                        '<|channel|>final <|constrain|>JSON<|message|>'
                        '{"privatized_text":"refugees do not belong here!",'
                        '"preserved_cues":["refugees"],"notes":"ok"}'
                    )
                }
            }
        ]
    }

    assert response_text(response) == "refugees do not belong here!"


def test_post_chat_completion_falls_back_when_response_format_rejected(monkeypatch):
    class FakeResponse(io.BytesIO):
        def __init__(self, payload):
            super().__init__(json.dumps(payload).encode("utf-8"))

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            return False

    calls = []

    def fake_urlopen(req, timeout):
        calls.append(json.loads(req.data.decode("utf-8")))
        if len(calls) == 1:
            raise error.HTTPError(
                req.full_url,
                400,
                "Bad Request",
                {},
                FakeResponse({"error": "unsupported response_format"}),
            )
        return FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr("privhsd.local_llm.request.urlopen", fake_urlopen)

    result = post_chat_completion(
        endpoint="http://localhost/v1/chat/completions",
        model="local",
        messages=[{"role": "user", "content": "test"}],
        timeout=1,
    )

    assert result["choices"][0]["message"]["content"] == "{}"
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[1]["response_format"]["type"] == "json_object"
