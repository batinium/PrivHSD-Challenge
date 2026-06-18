"""Small filesystem and CSV helpers."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class GlimoHsdError(ValueError):
    """Base package error for invalid inputs or pipeline failures."""


class CsvError(GlimoHsdError):
    """CSV input or output error."""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv(path: str | Path) -> tuple[list[dict[str, str]], list[str]]:
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise CsvError(f"{csv_path}: CSV header is required")
        return [dict(row) for row in reader], list(reader.fieldnames)


def write_csv(
    path: str | Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    assert_utf8(csv_path)


def assert_utf8(path: Path) -> None:
    try:
        path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CsvError(f"{path}: not valid UTF-8 at byte {exc.start}") from exc


def copy_file(source: str | Path, destination: str | Path) -> None:
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    assert_utf8(dest)


def write_json(path: str | Path, value: dict[str, Any]) -> None:
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
