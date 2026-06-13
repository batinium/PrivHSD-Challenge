"""Local optional provider/model discovery for auto mode."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from .config import AutoPipelineConfig


TOKEN_POLICY_WEIGHT_FILES = (
    "model.safetensors",
    "pytorch_model.bin",
)


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


def token_policy_artifact_status(model_dir: Path) -> dict[str, Any]:
    metadata = model_dir / "token_policy_metadata.json"
    weight_files = [model_dir / name for name in TOKEN_POLICY_WEIGHT_FILES]
    existing_weights = [path for path in weight_files if path.exists()]
    return {
        "path": str(model_dir),
        "exists": model_dir.exists(),
        "metadata_exists": metadata.exists(),
        "weight_exists": bool(existing_weights),
        "weight_files": [str(path) for path in existing_weights],
        "ready": model_dir.exists() and metadata.exists() and bool(existing_weights),
    }


def discover_token_policy(config: AutoPipelineConfig) -> dict[str, Any]:
    if "token_policy_ensemble" in config.disabled_models or "token-policy" in config.disabled_models:
        return disabled_status("model")
    dependency = dependency_status(("torch", "transformers"), kind="model")
    if dependency:
        return dependency
    artifacts = [
        token_policy_artifact_status(path)
        for path in config.token_policy_model_dirs
    ]
    ready = [item for item in artifacts if item["ready"]]
    if not ready:
        return {
            "status": "missing_artifact",
            "kind": "model",
            "artifacts": artifacts,
        }
    return {
        "status": "available",
        "kind": "model",
        "load": "lazy",
        "artifacts": artifacts,
        "ready_model_dirs": [item["path"] for item in ready],
    }


def discover_gliner(config: AutoPipelineConfig) -> dict[str, Any]:
    if "gliner" in config.disabled_providers:
        return disabled_status("provider")
    dependency = dependency_status(("gliner",), kind="provider")
    if dependency:
        return dependency
    if config.gliner_model:
        model_path = Path(config.gliner_model)
        if model_path.exists():
            return {
                "status": "available",
                "kind": "provider",
                "model": str(model_path),
                "local_only": True,
            }
        if config.allow_model_download:
            return {
                "status": "download_allowed",
                "kind": "provider",
                "model": config.gliner_model,
                "local_only": False,
            }
        return {
            "status": "missing_artifact",
            "kind": "provider",
            "model": config.gliner_model,
        }
    if config.allow_model_download:
        return {
            "status": "download_allowed",
            "kind": "provider",
            "model": None,
            "local_only": False,
        }
    return {
        "status": "missing_artifact",
        "kind": "provider",
        "detail": "GLiNER default model is remote; pass --allow-model-download or a local model path.",
    }


def discover_semantic_models(config: AutoPipelineConfig) -> dict[str, Any]:
    if "semantic" in config.disabled_models:
        return disabled_status("model")
    dependency = dependency_status(("sentence_transformers",), kind="model")
    if dependency:
        return dependency
    return {
        "status": "missing_artifact",
        "kind": "model",
        "load": "skipped",
        "detail": "No local semantic scorer artifact is configured for auto mode.",
    }


def discover_hsd_advisory(config: AutoPipelineConfig) -> dict[str, Any]:
    if "hsd_advisory" in config.disabled_models or "hsd-advisory" in config.disabled_models:
        return disabled_status("model")
    dependency = dependency_status(("torch", "transformers"), kind="model")
    if dependency:
        return dependency
    model_path = Path(config.hsd_advisory_model)
    if model_path.exists():
        return {
            "status": "available",
            "kind": "model",
            "load": "lazy",
            "model": str(model_path),
            "local_only": True,
        }
    if config.allow_model_download:
        return {
            "status": "available",
            "kind": "model",
            "load": "lazy",
            "model": config.hsd_advisory_model,
            "local_only": False,
        }
    return {
        "status": "available",
        "kind": "model",
        "load": "lazy",
        "model": config.hsd_advisory_model,
        "local_only": True,
        "detail": "Loads from the local Hugging Face cache only unless --allow-model-download is passed.",
    }


def discover_local_llm(config: AutoPipelineConfig) -> dict[str, Any]:
    if not config.local_llm_enabled:
        return {
            "status": "disabled",
            "kind": "model",
            "detail": "Local LLM structured review is disabled for official auto mode.",
        }
    if config.official_mode:
        return {
            "status": "disabled",
            "kind": "model",
            "detail": "Local LLM review is not enabled for official mode.",
        }
    return {
        "status": "not_configured",
        "kind": "model",
        "detail": "No local-only structured LLM reviewer is configured.",
    }
