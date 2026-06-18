"""Lightweight local API for the Expo review app."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from hashlib import sha256
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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


@dataclass(frozen=True)
class ApiConfig:
    protected_csv: Path = DEFAULT_PROTECTED_CSV
    validation_json: Path = DEFAULT_VALIDATION_JSON


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


def display_path(path: Path) -> str:
    return str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


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


def review_seed(config: ApiConfig, limit: int = 20) -> list[dict[str, Any]]:
    if not config.protected_csv.exists():
        return []
    rows: list[dict[str, Any]] = []
    with config.protected_csv.open(newline="", encoding="utf-8") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            if index >= limit:
                break
            text = row.get("text", "")
            rows.append(
                {
                    "id": f"case-{index + 1:03d}",
                    "source": row.get("ID") or f"row-{index + 1}",
                    "protectedText": text,
                    "restatement": restate_for_demo(text),
                    "classifierLabel": "hate" if row.get("hs") == "1" else "not_hate",
                    "classifierScore": None,
                    "riskLevel": "medium",
                    "decision": "pending",
                }
            )
    return rows


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
        if path == "/api/review-seed":
            self.write_json({"items": review_seed(self.server.config)})
            return
        self.write_json({"error": "not_found", "path": path}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[api] {self.address_string()} - {format % args}")

    def write_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local ContextSafe review API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--protected-csv", type=Path, default=DEFAULT_PROTECTED_CSV)
    parser.add_argument("--validation-json", type=Path, default=DEFAULT_VALIDATION_JSON)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = ApiConfig(
        protected_csv=args.protected_csv,
        validation_json=args.validation_json,
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
