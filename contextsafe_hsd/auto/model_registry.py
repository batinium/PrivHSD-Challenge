"""Local optional provider/model discovery for auto mode."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from contextsafe_hsd.hf_utility import approved_model_ids

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
    if not config.enable_token_policy:
        return {
            "status": "disabled",
            "kind": "model",
            "detail": (
                "Token-policy candidate generation is disabled by default; "
                "use --enable-token-policy only for research/audit ablations."
            ),
        }
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
    if not config.gliner_model:
        return {
            "status": "disabled",
            "kind": "provider",
            "profile": config.gliner_profile,
            "detail": (
                "GLiNER is not part of the default auto pipeline; pass an "
                "explicit local --gliner-model for research/debug ablations."
            ),
        }
    dependency = dependency_status(("gliner",), kind="provider")
    if dependency:
        return {
            **dependency,
            "model": config.gliner_model,
            "profile": config.gliner_profile,
        }
    model_path = Path(config.gliner_model)
    if model_path.exists():
        return {
            "status": "available",
            "kind": "provider",
            "model": str(model_path),
            "profile": config.gliner_profile,
            "local_only": True,
        }
    if config.allow_model_download:
        return {
            "status": "download_allowed",
            "kind": "provider",
            "model": config.gliner_model,
            "profile": config.gliner_profile,
            "local_only": False,
        }
    return {
        "status": "missing_artifact",
        "kind": "provider",
        "model": config.gliner_model,
        "profile": config.gliner_profile,
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
    model_ids = list(config.hsd_advisory_models)
    unsupported = [
        model_id
        for model_id in model_ids
        if model_id not in approved_model_ids(defaults_only=False)
    ]
    if unsupported:
        return {
            "status": "unsupported_model",
            "kind": "model",
            "model_ids": model_ids,
            "unsupported_model_ids": unsupported,
            "detail": "HSD advisory models must be listed in the approved HF utility registry.",
        }
    dependency = dependency_status(("torch", "transformers"), kind="model")
    if dependency:
        return {**dependency, "model_ids": model_ids}
    members = []
    local_only = not config.allow_model_download
    for model_id in model_ids:
        model_path = Path(model_id)
        if model_path.exists():
            members.append(
                {
                    "model_id": str(model_path),
                    "local_path": True,
                    "local_only": True,
                }
            )
        else:
            members.append(
                {
                    "model_id": model_id,
                    "local_path": False,
                    "local_only": local_only,
                }
            )
    return {
        "status": "available",
        "kind": "model",
        "load": "lazy",
        "model": model_ids[0] if len(model_ids) == 1 else None,
        "model_ids": model_ids,
        "member_count": len(model_ids),
        "members": members,
        "local_only": local_only,
        "detail": "Loads from the local Hugging Face cache only unless --allow-model-download is passed.",
    }


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
