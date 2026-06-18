"""Lightweight local API for the Expo review app."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import threading
from typing import Any
from urllib.parse import urlparse

from .backend_bundle import (
    DEFAULT_RESTATEMENT_ENDPOINT,
    DEFAULT_RESTATEMENT_MODEL,
    DEFAULT_TOKEN_PROTECT_THRESHOLD,
    run_backend_bundle,
)
from .models.hf_hsd_classifier_runtime import (
    DEFAULT_HF_HSD_BATCH_SIZE,
    DEFAULT_HF_HSD_MAX_LENGTH,
    DEFAULT_HF_HSD_MODEL_PATH,
    DEFAULT_HF_HSD_THRESHOLD,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTECTED_CSV = (
    ROOT
    / "data"
    / "locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed"
    / "train_split.no_simplify_hf.recovered.protected.csv"
)
DEFAULT_VALIDATION_JSON = (
    ROOT
    / "data"
    / "locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed"
    / "manifest.json"
)
DEFAULT_RESTATEMENT_COLUMNS = (
    "backend_restatement_final",
    "backend_restatement",
    "qwen35_descriptive_restatement",
    "restatement",
)
DEFAULT_SOURCE_TEXT_COLUMNS = ("source_text", "original_text")
DEFAULT_SCRUBBED_TEXT_COLUMNS = ("scrubbed_text", "protected_text", "text")
DEFAULT_CLASSIFIER_SCORE_COLUMNS = (
    "hf_hsd_score",
    "classifier_score",
    "hate_score",
    "baseline_hate_score",
)
DEFAULT_ADMIN_RUNS_DIR = ROOT / "data" / "admin_uploads"
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ApiConfig:
    protected_csv: Path = DEFAULT_PROTECTED_CSV
    validation_json: Path = DEFAULT_VALIDATION_JSON
    restatement_col: str | None = None
    bundle_manifest: Path | None = None
    deviation_audit_csv: Path | None = None
    token_importance_csv: Path | None = None
    admin_runs_dir: Path = DEFAULT_ADMIN_RUNS_DIR
    hf_hsd_model_path: str = DEFAULT_HF_HSD_MODEL_PATH
    hf_hsd_threshold: float = DEFAULT_HF_HSD_THRESHOLD
    hf_hsd_device: str = "auto"
    hf_hsd_batch_size: int = DEFAULT_HF_HSD_BATCH_SIZE
    hf_hsd_max_length: int = DEFAULT_HF_HSD_MAX_LENGTH
    restatement_endpoint: str = DEFAULT_RESTATEMENT_ENDPOINT
    restatement_model: str = DEFAULT_RESTATEMENT_MODEL
    restatement_batch_size: int = 5
    restatement_timeout_seconds: float = 180.0


def file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_path(value: str | Path | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def display_path(path: Path) -> str:
    return str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def safe_filename(filename: str) -> str:
    name = Path(filename or "upload.csv").name
    cleaned = SAFE_FILENAME_PATTERN.sub("_", name).strip("._")
    if not cleaned:
        return "upload.csv"
    return cleaned[:160]


def parse_csv_metadata(content: str) -> tuple[int, list[str]]:
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None:
        raise ValueError("CSV header is required")
    rows = list(reader)
    return len(rows), list(reader.fieldnames)


def read_validation(
    path: Path,
    *,
    submission_path: Path | None = None,
) -> dict[str, Any] | None:
    payload = read_json(path)
    if payload is None:
        return None
    validation = payload.get("validation")
    if isinstance(validation, dict):
        validation = dict(validation)
        if submission_path is not None:
            validation["submission"] = display_path(submission_path)
        return validation
    return payload


def protected_csv_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "path": display_path(path),
        }
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    return {
        "exists": True,
        "path": display_path(path),
        "sha256": file_sha256(path),
        "row_count": len(rows),
        "columns": reader.fieldnames or [],
    }


def upload_dir(config: ApiConfig, upload_id: str) -> Path:
    return config.admin_runs_dir / upload_id


def upload_meta_path(config: ApiConfig, upload_id: str) -> Path:
    return upload_dir(config, upload_id) / "upload.json"


def upload_source_path(config: ApiConfig, upload_id: str) -> Path:
    return upload_dir(config, upload_id) / "source.csv"


def read_upload(config: ApiConfig, upload_id: str) -> dict[str, Any] | None:
    return read_json(upload_meta_path(config, upload_id))


def persist_upload(config: ApiConfig, *, filename: str, content: str) -> dict[str, Any]:
    if not content.strip():
        raise ValueError("uploaded CSV is empty")
    row_count, columns = parse_csv_metadata(content)
    encoded = content.encode("utf-8")
    digest = sha256(encoded).hexdigest()
    upload_id = digest[:16]
    directory = upload_dir(config, upload_id)
    directory.mkdir(parents=True, exist_ok=True)
    source_path = upload_source_path(config, upload_id)
    if not source_path.exists() or file_sha256(source_path) != digest:
        source_path.write_bytes(encoded)
    existing = read_upload(config, upload_id) or {}
    now = utc_now()
    meta = {
        "id": upload_id,
        "filename": safe_filename(filename),
        "originalFilename": filename or "upload.csv",
        "sourcePath": str(source_path),
        "displaySourcePath": display_path(source_path),
        "sha256": digest,
        "bytes": len(encoded),
        "rowCount": row_count,
        "columns": columns,
        "createdAt": existing.get("createdAt") or now,
        "updatedAt": now,
    }
    write_json(upload_meta_path(config, upload_id), meta)
    return meta


def list_uploads(config: ApiConfig) -> list[dict[str, Any]]:
    if not config.admin_runs_dir.exists():
        return []
    uploads: list[dict[str, Any]] = []
    for path in config.admin_runs_dir.glob("*/upload.json"):
        payload = read_json(path)
        if payload:
            uploads.append(payload)
    return sorted(uploads, key=lambda item: str(item.get("updatedAt", "")), reverse=True)


def normalize_job_options(payload: dict[str, Any]) -> dict[str, Any]:
    id_col = str(payload.get("idCol") or payload.get("id_col") or "ID")
    if id_col.lower() in {"none", "null", "auto", "-"}:
        id_col = ""
    return {
        "textCol": str(payload.get("textCol") or payload.get("text_col") or "text"),
        "idCol": id_col,
        "labelCol": str(payload.get("labelCol") or payload.get("label_col") or "hs"),
        "restatementModel": str(payload.get("restatementModel") or ""),
        "finalScrub": bool(payload.get("finalScrub", True)),
        "allowRestatementFallback": bool(payload.get("allowRestatementFallback", False)),
    }


def job_id_for(upload_id: str, options: dict[str, Any]) -> str:
    digest = sha256(json.dumps(options, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"{upload_id}-{digest}"


def job_dir(config: ApiConfig, upload_id: str, job_id: str) -> Path:
    return upload_dir(config, upload_id) / "runs" / job_id


def job_meta_path(config: ApiConfig, upload_id: str, job_id: str) -> Path:
    return job_dir(config, upload_id, job_id) / "job.json"


def read_job_path(path: Path) -> dict[str, Any] | None:
    return read_json(path)


def read_job(config: ApiConfig, job_id: str) -> dict[str, Any] | None:
    if not config.admin_runs_dir.exists():
        return None
    matches = list(config.admin_runs_dir.glob(f"*/runs/{job_id}/job.json"))
    if not matches:
        return None
    return read_json(matches[0])


def write_job(job: dict[str, Any]) -> None:
    write_json(Path(str(job["jobPath"])), job)


def list_jobs(config: ApiConfig) -> list[dict[str, Any]]:
    if not config.admin_runs_dir.exists():
        return []
    jobs: list[dict[str, Any]] = []
    for path in config.admin_runs_dir.glob("*/runs/*/job.json"):
        payload = read_job_path(path)
        if payload:
            jobs.append(payload)
    return sorted(jobs, key=lambda item: str(item.get("updatedAt", "")), reverse=True)


def build_job(config: ApiConfig, payload: dict[str, Any]) -> dict[str, Any]:
    upload_id = str(payload.get("uploadId") or payload.get("upload_id") or "")
    if not upload_id:
        raise ValueError("uploadId is required")
    upload = read_upload(config, upload_id)
    if upload is None:
        raise ValueError(f"unknown uploadId: {upload_id}")
    options = normalize_job_options(payload)
    job_id = job_id_for(upload_id, options)
    output_dir = job_dir(config, upload_id, job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = job_meta_path(config, upload_id, job_id)
    existing = read_json(path) or {}
    now = utc_now()
    manifest_path = output_dir / "source.backend_bundle.manifest.json"
    status = existing.get("status") or "created"
    if manifest_path.exists() and status not in {"queued", "running"}:
        status = "complete"
    job = {
        "id": job_id,
        "uploadId": upload_id,
        "filename": upload.get("filename"),
        "sourcePath": upload.get("sourcePath"),
        "outputDir": str(output_dir),
        "jobPath": str(path),
        "manifestPath": str(manifest_path),
        "status": status,
        "stage": existing.get("stage") or "created",
        "progress": existing.get("progress") or {"processed": 0, "total": 0},
        "error": existing.get("error") or "",
        "options": options,
        "createdAt": existing.get("createdAt") or now,
        "updatedAt": now,
        "completedAt": existing.get("completedAt"),
    }
    write_job(job)
    return job


def job_artifact_config(config: ApiConfig, job: dict[str, Any]) -> ApiConfig:
    manifest_path = Path(str(job["manifestPath"]))
    manifest = read_json(manifest_path) or {}
    outputs = manifest.get("outputs") if isinstance(manifest, dict) else {}
    outputs = outputs if isinstance(outputs, dict) else {}
    annotated_csv = resolve_path(outputs.get("restatement_annotated_csv")) or config.protected_csv
    deviation_csv = resolve_path(outputs.get("deviation_audit_csv"))
    importance_csv = resolve_path(outputs.get("importance_csv"))
    return ApiConfig(
        protected_csv=annotated_csv,
        validation_json=manifest_path,
        restatement_col=config.restatement_col,
        bundle_manifest=manifest_path,
        deviation_audit_csv=deviation_csv,
        token_importance_csv=importance_csv,
        admin_runs_dir=config.admin_runs_dir,
    )


def admin_cases_for_job(config: ApiConfig, job_id: str) -> list[dict[str, Any]]:
    job = read_job(config, job_id)
    if not job:
        raise ValueError(f"unknown job: {job_id}")
    return admin_cases(job_artifact_config(config, job))


def admin_bundle_for_job(config: ApiConfig, job_id: str) -> dict[str, Any]:
    job = read_job(config, job_id)
    if not job:
        raise ValueError(f"unknown job: {job_id}")
    summary = admin_bundle_summary(job_artifact_config(config, job))
    summary["job"] = job
    return summary


def update_job_status(job: dict[str, Any], **updates: Any) -> dict[str, Any]:
    updated = dict(job)
    updated.update(updates)
    updated["updatedAt"] = utc_now()
    write_job(updated)
    return updated


def execute_backend_job(config: ApiConfig, job: dict[str, Any]) -> dict[str, Any]:
    options = dict(job["options"])
    job = update_job_status(
        job,
        status="running",
        stage="starting",
        error="",
        progress={"processed": 0, "total": 0},
    )

    def progress(event: dict[str, object]) -> None:
        nonlocal job
        job = update_job_status(
            job,
            status="running",
            stage=str(event.get("stage") or "running"),
            progress={
                "processed": int(event.get("processed") or 0),
                "total": int(event.get("total") or 0),
                "detail": str(event.get("detail") or ""),
            },
        )

    manifest = run_backend_bundle(
        Path(str(job["sourcePath"])),
        Path(str(job["outputDir"])),
        text_col=str(options["textCol"]),
        id_col=str(options["idCol"]) or None,
        label_col=str(options["labelCol"]),
        manifest_path=Path(str(job["manifestPath"])),
        hf_hsd_model_path=config.hf_hsd_model_path,
        hf_hsd_threshold=config.hf_hsd_threshold,
        hf_hsd_device=config.hf_hsd_device,
        hf_hsd_batch_size=config.hf_hsd_batch_size,
        hf_hsd_max_length=config.hf_hsd_max_length,
        token_protect_threshold=DEFAULT_TOKEN_PROTECT_THRESHOLD,
        restatement_endpoint=config.restatement_endpoint,
        restatement_model=str(options["restatementModel"]) or config.restatement_model,
        restatement_batch_size=config.restatement_batch_size,
        restatement_timeout_seconds=config.restatement_timeout_seconds,
        final_scrub=bool(options["finalScrub"]),
        allow_restatement_fallback=bool(options["allowRestatementFallback"]),
        progress_callback=progress,
        command=["api_server", "backend-bundle", str(job["sourcePath"])],
    )
    outputs = manifest.get("outputs", {})
    return update_job_status(
        job,
        status="complete",
        stage="complete",
        progress={"processed": 1, "total": 1, "detail": "Bundle complete."},
        outputs=outputs,
        completedAt=utc_now(),
    )


def bundle_manifest(config: ApiConfig) -> dict[str, Any] | None:
    if config.bundle_manifest:
        return read_json(config.bundle_manifest)
    payload = read_json(config.validation_json)
    if payload and payload.get("artifact_type") == "backend_admin_csv_bundle":
        return payload
    return None


def manifest_output_path(config: ApiConfig, key: str) -> Path | None:
    manifest = bundle_manifest(config)
    if not manifest:
        return None
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        return None
    value = outputs.get(key)
    return resolve_path(str(value)) if value else None


def configured_deviation_audit_path(config: ApiConfig) -> Path | None:
    return config.deviation_audit_csv or manifest_output_path(config, "deviation_audit_csv")


def configured_token_importance_path(config: ApiConfig) -> Path | None:
    return config.token_importance_csv or manifest_output_path(config, "importance_csv")


def configured_deviation_summary_path(config: ApiConfig) -> Path | None:
    return manifest_output_path(config, "deviation_audit_summary")


def first_nonempty(row: dict[str, str], columns: tuple[str, ...]) -> str:
    for column in columns:
        value = str(row.get(column, "") or "").strip()
        if value:
            return value
    return ""


def parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def split_pipe(value: str | None) -> list[str]:
    if not value:
        return []
    return [item for item in str(value).split("|") if item]


def row_source_id(row: dict[str, str], index: int) -> str:
    return str(row.get("ID") or row.get("id") or row.get("row_id") or f"row-{index}")


def load_deviation_rows(config: ApiConfig) -> dict[str, dict[str, str]]:
    path = configured_deviation_audit_path(config)
    if not path or not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row_source_id(row, index): row
            for index, row in enumerate(csv.DictReader(handle), start=1)
        }


def load_token_highlights(config: ApiConfig, *, limit_per_row: int = 5) -> dict[str, list[str]]:
    path = configured_token_importance_path(config)
    if not path or not path.exists():
        return {}
    highlights: dict[str, list[tuple[float, str]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            row_id = str(row.get("row_id") or row.get("ID") or row.get("row_index") or "")
            token = str(row.get("token") or "").strip()
            if not row_id or not token:
                continue
            protected = str(row.get("protect_hsd_token") or "") == "1"
            delta = parse_float(row.get("abs_delta_hate_score")) or 0.0
            if not protected and delta <= 0:
                continue
            highlights.setdefault(row_id, []).append((delta, token))
    return {
        row_id: [
            token
            for _delta, token in sorted(tokens, reverse=True)[:limit_per_row]
        ]
        for row_id, tokens in highlights.items()
    }


def admin_bundle_summary(config: ApiConfig) -> dict[str, Any]:
    manifest = bundle_manifest(config)
    deviation_summary_path = configured_deviation_summary_path(config)
    return {
        "protectedCsv": protected_csv_summary(config.protected_csv),
        "validation": read_validation(
            config.validation_json,
            submission_path=config.protected_csv,
        ),
        "bundle": manifest,
        "deviationSummary": read_json(deviation_summary_path)
        if deviation_summary_path
        else None,
    }


def admin_cases(config: ApiConfig, limit: int = 100) -> list[dict[str, Any]]:
    if not config.protected_csv.exists():
        return []
    deviation_rows = load_deviation_rows(config)
    token_highlights = load_token_highlights(config)
    rows: list[dict[str, Any]] = []
    with config.protected_csv.open(newline="", encoding="utf-8") as handle:
        for index, row in enumerate(csv.DictReader(handle), start=1):
            if len(rows) >= limit:
                break
            source_id = row_source_id(row, index)
            protected_text = first_nonempty(row, DEFAULT_SCRUBBED_TEXT_COLUMNS)
            deviation = deviation_rows.get(source_id, {})
            rows.append(
                {
                    "id": f"case-{index:03d}",
                    "source": source_id,
                    "originalText": first_nonempty(row, DEFAULT_SOURCE_TEXT_COLUMNS),
                    "protectedText": protected_text,
                    "restatement": row_restatement(
                        row,
                        protected_text,
                        config.restatement_col,
                    ),
                    "classifierLabel": "hate"
                    if str(row.get("hs", "")).strip() == "1"
                    else "not_hate",
                    "classifierScore": parse_float(
                        first_nonempty(row, DEFAULT_CLASSIFIER_SCORE_COLUMNS)
                    ),
                    "riskLevel": deviation.get("deviation_risk") or "medium",
                    "deviationRisk": deviation.get("deviation_risk") or "unknown",
                    "deviationScore": parse_float(deviation.get("deviation_score")),
                    "deviationReasons": split_pipe(deviation.get("deviation_reasons")),
                    "missingTargetTerms": split_pipe(
                        deviation.get("missing_target_terms")
                    ),
                    "missingContextTerms": split_pipe(
                        deviation.get("missing_context_terms")
                    ),
                    "tokenHighlights": token_highlights.get(source_id)
                    or token_highlights.get(str(index))
                    or [],
                    "decision": "pending",
                    "adminDisposition": "review",
                }
            )
    return rows


def review_seed(config: ApiConfig, limit: int = 20) -> list[dict[str, Any]]:
    if not config.protected_csv.exists():
        return []
    rows: list[dict[str, Any]] = []
    with config.protected_csv.open(newline="", encoding="utf-8") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            if index >= limit:
                break
            text = row.get("text", "")
            restatement = row_restatement(row, text, config.restatement_col)
            rows.append(
                {
                    "id": f"case-{index + 1:03d}",
                    "source": row.get("ID") or f"row-{index + 1}",
                    "protectedText": text,
                    "restatement": restatement,
                    "classifierLabel": "hate" if row.get("hs") == "1" else "not_hate",
                    "classifierScore": None,
                    "riskLevel": "medium",
                    "decision": "pending",
                }
            )
    return rows


def row_restatement(
    row: dict[str, str],
    text: str,
    configured_col: str | None,
) -> str:
    candidate_columns = (
        (configured_col,)
        if configured_col
        else DEFAULT_RESTATEMENT_COLUMNS
    )
    for column in candidate_columns:
        if not column:
            continue
        value = str(row.get(column, "") or "").strip()
        if value:
            return value
    return restate_for_demo(text)


def restate_for_demo(text: str) -> str:
    words = text.split()
    if len(words) <= 32:
        excerpt = text
    else:
        excerpt = " ".join(words[:32]) + "..."
    return (
        "A protected comment for citizen review says: "
        f"{excerpt}"
    )


class ContextSafeApiHandler(BaseHTTPRequestHandler):
    server: "ContextSafeApiServer"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.write_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        parts = [part for part in path.strip("/").split("/") if part]
        if path == "/health":
            self.write_json({"status": "ok", "service": "contextsafe-review-api"})
            return
        if path == "/api/baseline":
            self.write_json(
                {
                    "protectedCsv": protected_csv_summary(self.server.config.protected_csv),
                    "validation": read_validation(
                        self.server.config.validation_json,
                        submission_path=self.server.config.protected_csv,
                    ),
                }
            )
            return
        if path == "/api/admin-bundle":
            self.write_json(admin_bundle_summary(self.server.config))
            return
        if path == "/api/admin-cases":
            self.write_json({"items": admin_cases(self.server.config)})
            return
        if path == "/api/admin/uploads":
            self.write_json({"uploads": list_uploads(self.server.config)})
            return
        if path == "/api/admin/jobs":
            self.write_json({"jobs": list_jobs(self.server.config)})
            return
        if len(parts) == 4 and parts[:3] == ["api", "admin", "jobs"]:
            job = read_job(self.server.config, parts[3])
            if not job:
                self.write_json(
                    {"error": "not_found", "path": path},
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            self.write_json({"job": job})
            return
        if len(parts) == 5 and parts[:3] == ["api", "admin", "jobs"]:
            try:
                if parts[4] == "cases":
                    self.write_json(
                        {"items": admin_cases_for_job(self.server.config, parts[3])}
                    )
                    return
                if parts[4] == "bundle":
                    self.write_json(admin_bundle_for_job(self.server.config, parts[3]))
                    return
            except ValueError as exc:
                self.write_json(
                    {"error": "not_found", "message": str(exc)},
                    status=HTTPStatus.NOT_FOUND,
                )
                return
        if path == "/api/review-seed":
            self.write_json({"items": review_seed(self.server.config)})
            return
        self.write_json({"error": "not_found", "path": path}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self.read_json_body()
            if path == "/api/admin/uploads":
                upload = persist_upload(
                    self.server.config,
                    filename=str(payload.get("filename") or "upload.csv"),
                    content=str(payload.get("content") or ""),
                )
                self.write_json({"upload": upload}, status=HTTPStatus.CREATED)
                return
            if path == "/api/admin/jobs":
                job = self.server.start_job(payload)
                status = HTTPStatus.OK if job["status"] == "complete" else HTTPStatus.ACCEPTED
                self.write_json({"job": job}, status=status)
                return
            self.write_json({"error": "not_found", "path": path}, status=HTTPStatus.NOT_FOUND)
        except json.JSONDecodeError as exc:
            self.write_json(
                {"error": "bad_json", "message": str(exc)},
                status=HTTPStatus.BAD_REQUEST,
            )
        except ValueError as exc:
            self.write_json(
                {"error": "bad_request", "message": str(exc)},
                status=HTTPStatus.BAD_REQUEST,
            )
        except OSError as exc:
            self.write_json(
                {"error": "io_error", "message": str(exc)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[api] {self.address_string()} - {format % args}")

    def write_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8") if raw else "{}")
        if not isinstance(payload, dict):
            raise ValueError("JSON object body is required")
        return payload

    def write_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.write_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ContextSafeApiServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], config: ApiConfig) -> None:
        super().__init__(server_address, ContextSafeApiHandler)
        self.config = config
        self.active_jobs: dict[str, threading.Thread] = {}
        self.jobs_lock = threading.Lock()

    def start_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = build_job(self.config, payload)
        if job["status"] == "complete":
            return job
        with self.jobs_lock:
            thread = self.active_jobs.get(str(job["id"]))
            if thread and thread.is_alive():
                return job
            job = update_job_status(
                job,
                status="queued",
                stage="queued",
                progress={"processed": 0, "total": 0, "detail": "Queued."},
                error="",
            )
            thread = threading.Thread(
                target=self._run_job_thread,
                args=(dict(job),),
                name=f"contextsafe-job-{job['id']}",
                daemon=True,
            )
            self.active_jobs[str(job["id"])] = thread
            thread.start()
            return job

    def _run_job_thread(self, job: dict[str, Any]) -> None:
        try:
            execute_backend_job(self.config, job)
        except Exception as exc:  # pragma: no cover - exercised by integration use.
            update_job_status(
                job,
                status="failed",
                stage="failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            with self.jobs_lock:
                self.active_jobs.pop(str(job["id"]), None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local ContextSafe review API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--protected-csv", type=Path, default=DEFAULT_PROTECTED_CSV)
    parser.add_argument("--validation-json", type=Path, default=DEFAULT_VALIDATION_JSON)
    parser.add_argument(
        "--admin-runs-dir",
        type=Path,
        default=DEFAULT_ADMIN_RUNS_DIR,
        help="Persistent directory for uploaded CSVs and backend bundle jobs.",
    )
    parser.add_argument(
        "--bundle-manifest",
        type=Path,
        help="Backend bundle manifest JSON for admin endpoints.",
    )
    parser.add_argument(
        "--deviation-audit-csv",
        type=Path,
        help="Deviation audit CSV for /api/admin-cases.",
    )
    parser.add_argument(
        "--token-importance-csv",
        type=Path,
        help="DeHateBERT token importance CSV for /api/admin-cases.",
    )
    parser.add_argument(
        "--restatement-col",
        help=(
            "CSV column to serve as review restatement. Defaults to auto-detecting "
            "backend_restatement_final/backend_restatement/restatement columns."
        ),
    )
    parser.add_argument(
        "--hf-hsd-model-path",
        default=DEFAULT_HF_HSD_MODEL_PATH,
        help="Local DeHateBERT checkpoint path for processing uploaded CSVs.",
    )
    parser.add_argument("--hf-hsd-threshold", type=float, default=DEFAULT_HF_HSD_THRESHOLD)
    parser.add_argument("--hf-hsd-device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--hf-hsd-batch-size", type=int, default=DEFAULT_HF_HSD_BATCH_SIZE)
    parser.add_argument("--hf-hsd-max-length", type=int, default=DEFAULT_HF_HSD_MAX_LENGTH)
    parser.add_argument(
        "--restatement-endpoint",
        default=DEFAULT_RESTATEMENT_ENDPOINT,
        help="LM Studio/OpenAI-compatible base URL for uploaded CSV jobs.",
    )
    parser.add_argument("--restatement-model", default=DEFAULT_RESTATEMENT_MODEL)
    parser.add_argument("--restatement-batch-size", type=int, default=5)
    parser.add_argument("--restatement-timeout-seconds", type=float, default=180.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = ApiConfig(
        protected_csv=args.protected_csv,
        validation_json=args.validation_json,
        restatement_col=args.restatement_col,
        bundle_manifest=args.bundle_manifest,
        deviation_audit_csv=args.deviation_audit_csv,
        token_importance_csv=args.token_importance_csv,
        admin_runs_dir=args.admin_runs_dir,
        hf_hsd_model_path=args.hf_hsd_model_path,
        hf_hsd_threshold=args.hf_hsd_threshold,
        hf_hsd_device=args.hf_hsd_device,
        hf_hsd_batch_size=args.hf_hsd_batch_size,
        hf_hsd_max_length=args.hf_hsd_max_length,
        restatement_endpoint=args.restatement_endpoint,
        restatement_model=args.restatement_model,
        restatement_batch_size=args.restatement_batch_size,
        restatement_timeout_seconds=args.restatement_timeout_seconds,
    )
    server = ContextSafeApiServer((args.host, args.port), config)
    print(f"[api] listening on http://{args.host}:{args.port}")
    print(f"[api] protected CSV: {config.protected_csv}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[api] stopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
