import csv
import json

from privhsd.cli import build_parser
from privhsd.local_llm import LocalLlmError, run_local_llm_candidates


def write_rows(path):
    rows = [
        ("1", "REFUGEES dooo NOOOT belong here!!!! #MyTag", "hate"),
        ("2", "Everyone deserves respect.", "nothate"),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "label"])
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

    def fake_post(**kwargs):
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
    assert result["accepted_count"] == 1
    assert rows[0]["llm_candidate"] == "refugees do not belong here!"
    assert rows[1]["llm_candidate"] == ""
    assert result["rows"][0]["status"] == "accepted"
    assert "text" not in result["rows"][0]


def test_local_llm_candidate_generation_skips_when_endpoint_fails(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.csv"
    output = tmp_path / "candidates.csv"
    write_rows(source)

    def fake_post(**kwargs):
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
    assert result["rows"][0]["status"] == "failed"
    assert rows[0]["llm_candidate"] == ""


def test_local_llm_candidate_generation_rejects_cue_loss(monkeypatch, tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "candidates.csv"
    write_rows(source)

    def fake_post(**kwargs):
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
    assert rows[0]["llm_candidate"] == ""
