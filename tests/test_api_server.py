import csv
import json
import threading
import time

from contextsafe_hsd import api_server as api_server_module
from contextsafe_hsd.api_server import (
    ApiConfig,
    ContextSafeApiServer,
    JobStopped,
    admin_bundle_summary,
    admin_cases,
    build_job,
    execute_backend_job,
    list_jobs,
    list_uploads,
    persist_upload,
    read_job,
    review_seed,
    update_job_status,
    write_json,
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


def test_read_job_treats_empty_record_as_unavailable(tmp_path):
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
        },
    )

    job_path = tmp_path / upload["id"] / "runs" / job["id"] / "job.json"
    job_path.write_text("", encoding="utf-8")

    assert read_job(config, job["id"]) is None
    assert list_jobs(config) == []


def test_write_json_replaces_file_and_cleans_temp_file(tmp_path):
    path = tmp_path / "job.json"
    path.write_text('{"old": true}\n', encoding="utf-8")

    write_json(path, {"new": "value"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"new": "value"}
    assert list(tmp_path.glob(".job.json.*.tmp")) == []


def test_stale_running_job_is_marked_interrupted_and_resumable(tmp_path):
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
        },
    )
    update_job_status(
        job,
        status="running",
        stage="llm_restatement",
        progress={
            "processed": 5889,
            "total": 6792,
            "detail": "Selected row-level masked output.",
        },
    )
    server = ContextSafeApiServer(("127.0.0.1", 0), config)
    try:
        response = server.read_job_for_response(job["id"])
    finally:
        server.server_close()

    assert response is not None
    assert response["status"] == "interrupted"
    assert response["stage"] == "interrupted"
    assert response["canResume"] is True
    assert response["isActive"] is False
    assert response["progress"]["processed"] == 5889
    assert response["progress"]["total"] == 6792
    assert "Selected row-level masked output." in response["progress"]["detail"]

    persisted = read_job(config, job["id"])
    assert persisted is not None
    assert persisted["status"] == "interrupted"
    assert "canResume" not in persisted
    assert "isActive" not in persisted


def test_resume_job_queues_interrupted_job_from_cached_artifacts(tmp_path, monkeypatch):
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
        },
    )
    update_job_status(
        job,
        status="interrupted",
        stage="interrupted",
        progress={
            "processed": 5889,
            "total": 6792,
            "detail": "Interrupted before completion.",
        },
    )
    calls: list[str] = []

    def fake_execute_backend_job(
        _config: ApiConfig,
        queued_job: dict[str, object],
        *,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, object]:
        assert cancel_event is not None
        calls.append(str(queued_job["id"]))
        return update_job_status(
            queued_job,
            status="complete",
            stage="complete",
            progress={"processed": 1, "total": 1, "detail": "Bundle complete."},
            outputs={},
            completedAt="done",
        )

    monkeypatch.setattr(
        api_server_module,
        "execute_backend_job",
        fake_execute_backend_job,
    )
    server = ContextSafeApiServer(("127.0.0.1", 0), config)
    try:
        resumed = server.resume_job(job["id"])
        for _ in range(50):
            persisted = read_job(config, job["id"])
            if persisted and persisted["status"] == "complete":
                break
            time.sleep(0.01)
    finally:
        server.server_close()

    assert resumed["status"] == "queued"
    assert resumed["canResume"] is False
    assert resumed["progress"]["processed"] == 5889
    assert resumed["progress"]["total"] == 6792
    assert resumed["progress"]["detail"] == "Queued resume from cached artifacts."
    assert calls == [job["id"]]
    assert read_job(config, job["id"])["status"] == "complete"


def test_execute_backend_job_honors_pre_start_stop(tmp_path):
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
        },
    )
    cancel_event = threading.Event()
    cancel_event.set()

    try:
        execute_backend_job(config, job, cancel_event=cancel_event)
    except JobStopped as exc:
        stopped_job = exc.job
    else:  # pragma: no cover - defensive branch.
        raise AssertionError("expected JobStopped")

    assert stopped_job["status"] == "stopped"
    assert stopped_job["stage"] == "stopped"
    assert "Stopped by user" in stopped_job["progress"]["detail"]
    assert read_job(config, job["id"])["status"] == "stopped"


def test_stop_job_marks_active_job_as_stopping(tmp_path):
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
        },
    )
    running_job = update_job_status(
        job,
        status="running",
        stage="baseline",
        progress={
            "processed": 10,
            "total": 20,
            "detail": "Built deterministic privacy baseline.",
        },
    )
    release_thread = threading.Event()
    thread = threading.Thread(target=release_thread.wait)
    thread.start()
    cancel_event = threading.Event()
    server = ContextSafeApiServer(("127.0.0.1", 0), config)
    try:
        server.active_jobs[running_job["id"]] = thread
        server.job_cancel_events[running_job["id"]] = cancel_event

        response = server.stop_job(running_job["id"])
    finally:
        release_thread.set()
        thread.join(timeout=1)
        server.server_close()

    assert response["status"] == "stopping"
    assert response["isActive"] is True
    assert response["canResume"] is False
    assert cancel_event.is_set()
    assert read_job(config, running_job["id"])["status"] == "stopping"
