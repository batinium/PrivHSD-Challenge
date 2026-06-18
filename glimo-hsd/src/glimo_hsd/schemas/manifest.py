"""Manifest helpers."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Any

from ..io import now_utc
from ..results import StepResult


def _version() -> str:
    try:
        return metadata.version("glimo-hsd")
    except metadata.PackageNotFoundError:  # pragma: no cover - source tree import.
        return "0.1.1"


def build_manifest(
    *,
    output_dir: Path,
    input_hash: str,
    config_hash: str,
    source_path: Path,
    text_col: str,
    label_col: str | None,
    model_id: str,
    model_revision: str | None,
    steps: dict[str, StepResult],
    outputs: dict[str, Path | None],
) -> dict[str, Any]:
    return {
        "pipeline": "glimo_hsd",
        "pipeline_version": _version(),
        "created_at": now_utc(),
        "input_hash": input_hash,
        "config_hash": config_hash,
        "source_path": str(source_path),
        "text_col": text_col,
        "label_col": label_col,
        "model_id": model_id,
        "model_revision": model_revision,
        "steps": {
            name: step.to_manifest(root=output_dir) for name, step in steps.items()
        },
        "outputs": {
            name: str(path.relative_to(output_dir)) if path is not None else None
            for name, path in outputs.items()
        },
    }
