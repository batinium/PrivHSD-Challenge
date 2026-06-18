"""Configuration objects for the Glimo HSD pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_MODEL_ID = "batinium/glimo-dehatebert-hsd"
DEFAULT_THRESHOLD = 0.850469
DEFAULT_RESTATEMENT_ENDPOINT = "http://localhost:1234/v1/chat/completions"
DEFAULT_RESTATEMENT_MODEL = "qwen3.5-4b"

ClassifierBackend = Literal["hf", "keyword", "none"]
RestatementBackendName = Literal["none", "qwen", "local-http"]


@dataclass(frozen=True)
class ModelConfig:
    model_id: str = DEFAULT_MODEL_ID
    model_revision: str | None = None
    backend: ClassifierBackend = "hf"
    threshold: float = DEFAULT_THRESHOLD
    device: str = "auto"
    batch_size: int = 64
    max_length: int = 512

    def __post_init__(self) -> None:
        if self.backend not in {"hf", "keyword", "none"}:
            raise ValueError("classifier backend must be hf, keyword, or none")
        if not 0 <= self.threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.max_length < 1:
            raise ValueError("max_length must be positive")


@dataclass(frozen=True)
class RestatementConfig:
    backend: RestatementBackendName = "none"
    endpoint: str = DEFAULT_RESTATEMENT_ENDPOINT
    model: str = DEFAULT_RESTATEMENT_MODEL
    batch_size: int = 5
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 2200
    timeout_seconds: float = 180.0
    max_retries: int = 2
    allow_fallback: bool = False
    prompt_version: str = "descriptive_v2"

    def __post_init__(self) -> None:
        if self.backend not in {"none", "qwen", "local-http"}:
            raise ValueError("restatement backend must be none, qwen, or local-http")
        if self.batch_size < 1:
            raise ValueError("restatement batch_size must be positive")
        if self.max_retries < 0:
            raise ValueError("restatement max_retries cannot be negative")


@dataclass(frozen=True)
class AuditConfig:
    enabled: bool = True
    risk_threshold: int = 3


@dataclass(frozen=True)
class PipelineConfig:
    text_col: str = "text"
    label_col: str | None = "hs"
    id_col: str | None = None
    output_dir: str | Path | None = None
    model_id: str = DEFAULT_MODEL_ID
    model_revision: str | None = None
    classifier_backend: ClassifierBackend = "hf"
    threshold: float = DEFAULT_THRESHOLD
    device: str = "auto"
    batch_size: int = 64
    max_length: int = 512
    token_importance: bool = True
    token_protect_threshold: float = 0.03
    restatement_backend: RestatementBackendName = "none"
    restatement_endpoint: str = DEFAULT_RESTATEMENT_ENDPOINT
    restatement_model: str = DEFAULT_RESTATEMENT_MODEL
    restatement_batch_size: int = 5
    restatement_temperature: float = 0.2
    restatement_top_p: float = 0.9
    restatement_max_tokens: int = 2200
    restatement_timeout_seconds: float = 180.0
    restatement_max_retries: int = 2
    allow_restatement_fallback: bool = False
    prompt_version: str = "descriptive_v2"
    final_scrub: bool = True
    force: bool = False

    def model_config(self) -> ModelConfig:
        return ModelConfig(
            model_id=self.model_id,
            model_revision=self.model_revision,
            backend=self.classifier_backend,
            threshold=self.threshold,
            device=self.device,
            batch_size=self.batch_size,
            max_length=self.max_length,
        )

    def restatement_config(self) -> RestatementConfig:
        return RestatementConfig(
            backend=self.restatement_backend,
            endpoint=self.restatement_endpoint,
            model=self.restatement_model,
            batch_size=self.restatement_batch_size,
            temperature=self.restatement_temperature,
            top_p=self.restatement_top_p,
            max_tokens=self.restatement_max_tokens,
            timeout_seconds=self.restatement_timeout_seconds,
            max_retries=self.restatement_max_retries,
            allow_fallback=self.allow_restatement_fallback,
            prompt_version=self.prompt_version,
        )

    def audit_config(self) -> AuditConfig:
        return AuditConfig()
