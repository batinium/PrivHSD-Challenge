"""Local optional provider/model discovery for auto mode."""

from __future__ import annotations

import importlib.util
from typing import Any

from .config import AutoPipelineConfig


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def disabled_status(kind: str) -> dict[str, Any]:
    return {"status": "disabled", "kind": kind}


def dependency_status(
    module_names: tuple[str, ...],
    *,
    kind: str,
) -> dict[str, Any] | None:
    missing = [name for name in module_names if not module_available(name)]
    if missing:
        return {
            "status": "missing_dependency",
            "kind": kind,
            "missing": missing,
        }
    return None


def discover_local_llm(config: AutoPipelineConfig) -> dict[str, Any]:
    if "local_llm" in config.disabled_models or "local-llm" in config.disabled_models:
        return disabled_status("model")
    if config.hsd_classification_backend != "local_llm" and not config.local_llm_enabled:
        return {
            "status": "disabled",
            "kind": "model",
            "detail": "Local LLM structured review is disabled unless selected.",
        }
    if config.official_mode:
        return {
            "status": "disabled",
            "kind": "model",
            "detail": "Local LLM review is not enabled for official mode.",
        }
    return {
        "status": "available",
        "kind": "model",
        "load": "lazy",
        "model_id": config.local_llm_model,
        "endpoint": config.local_llm_endpoint,
        "batch_size": config.local_llm_batch_size,
        "timeout_seconds": config.local_llm_timeout_seconds,
        "pii_suggestions_enabled": config.local_llm_enable_pii_suggestions,
        "require_structured_output": config.local_llm_require_structured_output,
        "detail": "Local OpenAI-compatible structured review; no live call made during discovery.",
    }
