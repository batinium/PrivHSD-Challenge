import csv
import json

from contextsafe_hsd.api_server import (
    ApiConfig,
    admin_bundle_summary,
    admin_cases,
    build_job,
    list_jobs,
    list_uploads,
    persist_upload,
    read_job,
    review_seed,
)


def test_review_seed_uses_backend_restatement_column(tmp_path):
    source = tmp_path / "review.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ID",
                "text",
                "hs",
                "backend_restatement_final",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ID": "row-1",
                "text": "Protected source text with [USER].",
                "hs": "1",
                "backend_restatement_final": "The comment attacks a protected group.",
            }
        )

    items = review_seed(ApiConfig(protected_csv=source))

    assert items[0]["protectedText"] == "Protected source text with [USER]."
    assert items[0]["restatement"] == "The comment attacks a protected group."
    assert items[0]["classifierLabel"] == "hate"


def test_review_seed_prefers_latest_completed_admin_job(tmp_path):
    config = ApiConfig(admin_runs_dir=tmp_path)
    upload = persist_upload(
        config,
        filename="incoming.csv",
        content="ID,text,hs\nsource-row,Raw text,0\n",
    )
    job = build_job(
        config,
        {
            "uploadId": upload["id"],
            "textCol": "text",
            "idCol": "ID",
            "labelCol": "hs",
        },
    )
    output_dir = tmp_path / upload["id"] / "runs" / job["id"]
    annotated = output_dir / "source.restated.annotated.csv"
    with annotated.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ID",
                "scrubbed_text",
                "hs",
                "backend_restatement_final",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ID": "source-row",
                "scrubbed_text": "Live scrubbed text.",
                "hs": "1",
                "backend_restatement_final": "The live comment attacks a group.",
            }
        )
    manifest = {
        "artifact_type": "backend_admin_csv_bundle",
        "outputs": {"restatement_annotated_csv": str(annotated)},
    }
    (output_dir / "source.backend_bundle.manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    updated_job = {**job, "status": "complete", "updatedAt": "2099-01-01T00:00:00+00:00"}
    (output_dir / "job.json").write_text(json.dumps(updated_job), encoding="utf-8")

    items = review_seed(config, limit=5)

    assert items[0]["protectedText"] == "Live scrubbed text."
    assert items[0]["restatement"] == "The live comment attacks a group."
    assert items[0]["classifierLabel"] == "hate"


def test_admin_cases_join_source_restatement_deviation_and_tokens(tmp_path):
    annotated = tmp_path / "annotated.csv"
    with annotated.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ID",
                "text",
                "source_text",
                "scrubbed_text",
                "hs",
                "backend_restatement_final",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ID": "REDDIT_1",
                "text": "Scrubbed text with [PERSON].",
                "source_text": "Original text with a public target.",
                "scrubbed_text": "Scrubbed text with [PERSON].",
                "hs": "1",
                "backend_restatement_final": "The comment attacks a public target.",
            }
        )

    audit = tmp_path / "audit.csv"
    with audit.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ID", "deviation_risk", "deviation_score", "deviation_reasons"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ID": "REDDIT_1",
                "deviation_risk": "medium",
                "deviation_score": "3",
                "deviation_reasons": "context_term_loss|target_term_loss",
            }
        )

    importance = tmp_path / "importance.csv"
    with importance.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "row_id",
                "token",
                "abs_delta_hate_score",
                "protect_hsd_token",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "row_id": "REDDIT_1",
                "token": "target",
                "abs_delta_hate_score": "0.5",
                "protect_hsd_token": "1",
            }
        )

    items = admin_cases(
        ApiConfig(
            protected_csv=annotated,
            deviation_audit_csv=audit,
            token_importance_csv=importance,
        )
    )

    assert items[0]["source"] == "REDDIT_1"
    assert items[0]["originalText"] == "Original text with a public target."
    assert items[0]["protectedText"] == "Scrubbed text with [PERSON]."
    assert items[0]["restatement"] == "The comment attacks a public target."
    assert items[0]["deviationRisk"] == "medium"
    assert items[0]["deviationReasons"] == [
        "context_term_loss",
        "target_term_loss",
    ]
    assert items[0]["tokenHighlights"] == ["target"]


def test_admin_cases_use_predicted_label_when_hs_is_missing(tmp_path):
    annotated = tmp_path / "annotated.csv"
    with annotated.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ID",
                "text",
                "source_text",
                "scrubbed_text",
                "hs_predicted",
                "hf_hsd_score",
                "backend_restatement_final",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ID": "row-1",
                "text": "Scrubbed text.",
                "source_text": "Original text.",
                "scrubbed_text": "Scrubbed text.",
                "hs_predicted": "1",
                "hf_hsd_score": "0.91",
                "backend_restatement_final": "The comment attacks a group.",
            }
        )

    items = admin_cases(ApiConfig(protected_csv=annotated))

    assert items[0]["classifierLabel"] == "hate"
    assert items[0]["classifierScore"] == 0.91


def test_admin_bundle_summary_loads_manifest_deviation_summary(tmp_path):
    protected = tmp_path / "protected.csv"
    protected.write_text("ID,text,hs\n1,hello,0\n", encoding="utf-8")
    deviation_summary = tmp_path / "summary.json"
    deviation_summary.write_text(
        json.dumps({"risk_counts": {"medium": 1}}),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "artifact_type": "backend_admin_csv_bundle",
                "outputs": {
                    "deviation_audit_summary": str(deviation_summary),
                },
            }
        ),
        encoding="utf-8",
    )

    summary = admin_bundle_summary(
        ApiConfig(
            protected_csv=protected,
            validation_json=manifest,
        )
    )

    assert summary["bundle"]["artifact_type"] == "backend_admin_csv_bundle"
    assert summary["deviationSummary"]["risk_counts"] == {"medium": 1}


def test_persist_upload_deduplicates_by_content_and_lists(tmp_path):
    config = ApiConfig(admin_runs_dir=tmp_path)

    first = persist_upload(
        config,
        filename="incoming.csv",
        content="ID,text,hs\nr1,hello,0\n",
    )
    second = persist_upload(
        config,
        filename="renamed.csv",
        content="ID,text,hs\nr1,hello,0\n",
    )

    assert first["id"] == second["id"]
    assert second["filename"] == "renamed.csv"
    assert second["rowCount"] == 1
    assert second["columns"] == ["ID", "text", "hs"]
    assert list_uploads(config)[0]["id"] == first["id"]


def test_build_job_persists_reusable_job_record(tmp_path):
    config = ApiConfig(admin_runs_dir=tmp_path)
    upload = persist_upload(
        config,
        filename="incoming.csv",
        content="ID,text,hs\nr1,hello,0\n",
    )

    job = build_job(
        config,
        {
            "uploadId": upload["id"],
            "textCol": "text",
            "idCol": "ID",
            "labelCol": "hs",
            "restatementModel": "qwen3.5-4b",
        },
    )
    reloaded = read_job(config, job["id"])

    assert reloaded is not None
    assert reloaded["id"] == job["id"]
    assert reloaded["uploadId"] == upload["id"]
    assert reloaded["options"]["textCol"] == "text"
    assert list_jobs(config)[0]["id"] == job["id"]
