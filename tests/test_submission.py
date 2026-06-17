import csv
import json
import subprocess
import sys

from contextsafe_hsd.cli import build_parser, main
from contextsafe_hsd.submission import validate_submission


def write_source(path):
    rows = [
        {
            "id": "1",
            "text": "@mara emailed mara@example.test that immigrants should leave.",
            "label": "hate",
            "meta": "keep-a",
        },
        {
            "id": "2",
            "text": "Everyone deserves respect.",
            "label": "nothate",
            "meta": "keep-b",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "text", "label", "meta"])
        writer.writeheader()
        writer.writerows(rows)
    return rows


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_public_commands_are_registered():
    parser = build_parser()

    protect_args = parser.parse_args(
        [
            "protect",
            "--input",
            "input.csv",
            "--output",
            "output.csv",
            "--text-col",
            "text",
        ]
    )
    validate_args = parser.parse_args(
        [
            "validate-submission",
            "--source",
            "input.csv",
            "--submission",
            "submission.csv",
            "--text-col",
            "text",
        ]
    )

    assert protect_args.command == "protect"
    assert protect_args.llm_review == "local-llm"
    assert protect_args.llm_verifier == "local-llm"
    assert validate_args.command == "validate-submission"


def test_protect_help_is_short_public_surface():
    result = subprocess.run(
        [sys.executable, "-m", "contextsafe_hsd.cli", "protect", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--preset" in result.stdout
    assert "--llm-review" in result.stdout
    assert "--llm-verifier" in result.stdout
    assert "exact" in result.stdout
    assert "Run the final exact CSV pipeline" in result.stdout
    assert "--disable-provider" not in result.stdout
    assert "--disable-model" not in result.stdout
    assert "--metric-depth" not in result.stdout
    assert "create-submission" not in result.stdout
    assert "rerank-candidates" not in result.stdout


def test_protect_exact_preserves_schema_and_manifest_stages(tmp_path, capsys):
    source = tmp_path / "source.csv"
    output = tmp_path / "protected.csv"
    manifest_path = tmp_path / "manifest.json"
    write_source(source)

    exit_code = main(
        [
            "protect",
            "--input",
            str(source),
            "--output",
            str(output),
            "--text-col",
            "text",
            "--id-col",
            "id",
            "--manifest",
            str(manifest_path),
            "--preset",
            "exact",
            "--llm-review",
            "off",
            "--llm-verifier",
            "off",
        ]
    )
    captured = capsys.readouterr()

    rows = read_rows(output)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert '"preset": "exact"' in captured.out
    assert list(rows[0]) == ["id", "text", "label", "meta"]
    assert not any(column.startswith("hate_speech") for column in rows[0])
    assert not any(column.startswith("predicted_") for column in rows[0])
    assert "[USER]" in rows[0]["text"]
    assert "[EMAIL]" in rows[0]["text"]
    assert manifest["pipeline"] == "final_exact"
    assert manifest["exact_format_submission"] is True
    assert manifest["llm_review"] == "off"
    assert manifest["llm_verifier"] == "off"
    assert set(manifest["stages"]) == {
        "privacy_detection",
        "meaning_protection",
        "verification",
    }
    assert "hsd_advisory" not in manifest["stages"]["verification"]
    assert manifest["stages"]["verification"]["local_llm_hsd_review"][
        "status"
    ] == "skipped"
    assert manifest["stages"]["verification"]["local_llm_hsd_verifier"][
        "status"
    ] == "skipped"
    assert manifest["validation"]["valid"] is True


def test_protect_exact_local_llm_review_stays_in_sidecar(monkeypatch, tmp_path):
    def fake_post_chat_completion(*, endpoint, payload, timeout):
        rows = json.loads(payload["messages"][1]["content"])["items"]
        assert "mara@example.test" not in payload["messages"][1]["content"]
        items = [
            {
                "id": row["id"],
                "hate": True,
                "hsd_reasons": [
                    "protected_target",
                    "exclusion",
                ],
                "pii_leftover": ["[EMAIL]"],
                "review_needed": True,
            }
            for row in rows
        ]
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "record_hsd_review",
                                    "arguments": json.dumps(
                                        {"items": items}
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
    source = tmp_path / "source.csv"
    output = tmp_path / "protected.csv"
    manifest_path = tmp_path / "manifest.json"
    audit_path = tmp_path / "audit.json"
    write_source(source)

    exit_code = main(
        [
            "protect",
            "--input",
            str(source),
            "--output",
            str(output),
            "--text-col",
            "text",
            "--id-col",
            "id",
            "--manifest",
            str(manifest_path),
            "--audit",
            str(audit_path),
            "--preset",
            "exact",
            "--llm-review",
            "local-llm",
            "--llm-verifier",
            "off",
            "--local-llm-endpoint",
            "http://local.test/v1/chat/completions",
            "--local-llm-model",
            "fake-local-llm",
        ]
    )

    rows = read_rows(output)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert list(rows[0]) == ["id", "text", "label", "meta"]
    assert "[EMAIL]" in rows[0]["text"]
    assert "is_hate_speech" not in rows[0]
    classification = manifest["classification"]
    assert classification["backend"] == "local_llm"
    assert classification["status"] == "ok"
    assert classification["parse_count"] == 2
    assert classification["fallback_count"] == 0
    assert classification["reason_tag_counts"] == {
        "exclusion": 2,
        "protected_target": 2,
    }
    assert classification["validated_pii_suggestion_counts"] == {
        "total": 2,
        "accepted_for_review": 0,
        "rejected": 2,
    }
    assert audit["classification_reviews"][0]["label"] == "1"
    assert "[EMAIL]" not in json.dumps(classification)


def test_validate_submission_reports_helper_columns(tmp_path):
    source = tmp_path / "source.csv"
    submission = tmp_path / "submission.csv"
    write_source(source)
    with submission.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "text", "label", "meta", "privatized_text"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "text": "changed",
                "label": "hate",
                "meta": "keep-a",
                "privatized_text": "helper",
            }
        )
        writer.writerow(
            {
                "id": "2",
                "text": "changed",
                "label": "nothate",
                "meta": "keep-b",
                "privatized_text": "helper",
            }
        )

    report = validate_submission(
        source,
        submission,
        text_cols=["text"],
        id_col="id",
        strict=False,
    )

    assert report["valid"] is False
    assert {issue["code"] for issue in report["issues"]} >= {
        "helper_columns_present",
        "column_order_mismatch",
    }


def test_validate_submission_reports_reordered_ids(tmp_path):
    source = tmp_path / "source.csv"
    submission = tmp_path / "submission.csv"
    write_source(source)
    rows = read_rows(source)
    with submission.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "text", "label", "meta"])
        writer.writeheader()
        writer.writerows(reversed(rows))

    report = validate_submission(
        source,
        submission,
        text_cols=["text"],
        id_col="id",
        strict=False,
    )

    assert report["valid"] is False
    assert "id_order_mismatch" in {issue["code"] for issue in report["issues"]}
