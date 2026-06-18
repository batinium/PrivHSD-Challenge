"""Public API for the Glimo HSD package."""

from __future__ import annotations

from importlib import metadata

from .config import AuditConfig, ModelConfig, PipelineConfig, RestatementConfig
from .pipeline import process_csv
from .results import PipelineResult, StepResult
from .steps import (
    audit_restatements,
    classify_csv,
    final_scrub_csv,
    generate_token_importances,
    restate_csv,
    scrub_csv,
)

try:
    __version__ = metadata.version("glimo-hsd")
except metadata.PackageNotFoundError:  # pragma: no cover - source tree import.
    __version__ = "0.1.1"

__all__ = [
    "AuditConfig",
    "ModelConfig",
    "PipelineConfig",
    "PipelineResult",
    "RestatementConfig",
    "StepResult",
    "__version__",
    "audit_restatements",
    "classify_csv",
    "final_scrub_csv",
    "generate_token_importances",
    "process_csv",
    "restate_csv",
    "scrub_csv",
]
