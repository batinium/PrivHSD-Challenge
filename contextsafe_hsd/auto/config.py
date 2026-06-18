"""Configuration for automatic provider/model orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field

from contextsafe_hsd.metrics import METRIC_DEPTHS
from contextsafe_hsd.models.hf_hsd_classifier_runtime import (
    DEFAULT_HF_HSD_BATCH_SIZE,
    DEFAULT_HF_HSD_MAX_LENGTH,
    DEFAULT_HF_HSD_MODEL_PATH,
    DEFAULT_HF_HSD_THRESHOLD,
)
from contextsafe_hsd.models.dpmlm_rewrite_runtime import (
    DEFAULT_DPMLM_EPSILON,
    DEFAULT_DPMLM_MAX_LENGTH,
    DEFAULT_DPMLM_MAX_REWRITE_TOKENS,
    DEFAULT_DPMLM_MIN_ELIGIBLE_SCORE,
    DEFAULT_DPMLM_MODEL_PATH,
    DEFAULT_DPMLM_TOP_K,
)


AUTO_MODES = frozenset({"auto"})
AUTO_CAPABLE_MODES = frozenset({"auto", "utility", "balanced", "privacy"})
DEVICE_POLICIES = frozenset({"auto", "cpu", "cuda"})
AUDIT_LEVELS = frozenset({"summary", "row", "debug"})
HSD_CLASSIFICATION_BACKENDS = frozenset({"none", "local_llm", "hf_classifier"})


@dataclass(frozen=True)
class AutoPipelineConfig:
    """Run-level auto pipeline settings.

    The automatic official path keeps balanced deterministic masking as the
    always-present baseline and treats optional systems as advisory evidence.
    """

    baseline_mode: str = "balanced"
    metric_depth: str = "fast"
    allow_model_download: bool = False
    device: str = "cpu"
    max_model_batch_size: int = 16
    max_provider_rows: int | None = None
    disabled_providers: frozenset[str] = field(default_factory=frozenset)
    disabled_models: frozenset[str] = field(default_factory=frozenset)
    audit_level: str = "summary"
    provider_language: str = "en"
    hsd_classification_backend: str = "none"
    hf_hsd_model_path: str = DEFAULT_HF_HSD_MODEL_PATH
    hf_hsd_threshold: float = DEFAULT_HF_HSD_THRESHOLD
    hf_hsd_device: str = "auto"
    hf_hsd_batch_size: int = DEFAULT_HF_HSD_BATCH_SIZE
    hf_hsd_max_length: int = DEFAULT_HF_HSD_MAX_LENGTH
    generalize_targets: bool | None = False
    candidate_selection: bool = True
    style_scrub: bool = True
    style_simplify_language: bool = False
    dpmlm_rewrite: bool = False
    dpmlm_model_path: str = DEFAULT_DPMLM_MODEL_PATH
    dpmlm_device: str = "auto"
    dpmlm_epsilon: float = DEFAULT_DPMLM_EPSILON
    dpmlm_max_rewrite_tokens: int = DEFAULT_DPMLM_MAX_REWRITE_TOKENS
    dpmlm_min_eligible_score: int = DEFAULT_DPMLM_MIN_ELIGIBLE_SCORE
    dpmlm_top_k: int = DEFAULT_DPMLM_TOP_K
    dpmlm_max_length: int = DEFAULT_DPMLM_MAX_LENGTH
    dpmlm_random_seed: int = 0
    dpmlm_min_row_style_risk: int = 1
    dpmlm_min_character_retention: float = 0.65
    dpmlm_max_length_drift: float = 0.45
    hsd_token_importance_path: str | None = None
    hsd_token_protect_threshold: float = 0.03
    official_mode: bool = True
    local_llm_enabled: bool = False
    local_llm_endpoint: str = "http://localhost:1234/v1/chat/completions"
    local_llm_model: str = "openai/gpt-oss-20b"
    local_llm_timeout_seconds: float = 120.0
    local_llm_batch_size: int = 10
    local_llm_enable_pii_suggestions: bool = True
    local_llm_require_structured_output: bool = True
    author_group_masking: bool = True
    author_group_col: str | None = None
    author_group_min_repetitions: int = 2
    author_group_min_author_rows: int = 2

    def __post_init__(self) -> None:
        backend = self.hsd_classification_backend.strip().lower().replace("-", "_")
        object.__setattr__(self, "hsd_classification_backend", backend)
        disabled_models = frozenset(
            model.strip()
            for model in self.disabled_models
            if model and model.strip()
        )
        object.__setattr__(self, "disabled_models", disabled_models)
        object.__setattr__(
            self,
            "local_llm_endpoint",
            self.local_llm_endpoint.strip()
            or "http://localhost:1234/v1/chat/completions",
        )
        object.__setattr__(
            self,
            "local_llm_model",
            self.local_llm_model.strip() or "openai/gpt-oss-20b",
        )
        object.__setattr__(
            self,
            "local_llm_enabled",
            bool(self.local_llm_enabled or backend == "local_llm"),
        )
        object.__setattr__(
            self,
            "hf_hsd_model_path",
            self.hf_hsd_model_path.strip() or DEFAULT_HF_HSD_MODEL_PATH,
        )
        object.__setattr__(
            self,
            "hf_hsd_device",
            self.hf_hsd_device.strip().lower() or "auto",
        )
        object.__setattr__(
            self,
            "dpmlm_model_path",
            self.dpmlm_model_path.strip() or DEFAULT_DPMLM_MODEL_PATH,
        )
        object.__setattr__(
            self,
            "dpmlm_device",
            self.dpmlm_device.strip().lower() or "auto",
        )
        if self.author_group_col is not None:
            object.__setattr__(
                self,
                "author_group_col",
                self.author_group_col.strip() or None,
            )
        if self.hsd_token_importance_path is not None:
            object.__setattr__(
                self,
                "hsd_token_importance_path",
                self.hsd_token_importance_path.strip() or None,
            )
        if self.baseline_mode not in {"utility", "balanced", "privacy"}:
            raise ValueError("baseline_mode must be utility, balanced, or privacy")
        if self.metric_depth not in METRIC_DEPTHS:
            raise ValueError(f"metric_depth must be one of {sorted(METRIC_DEPTHS)}")
        if self.device not in DEVICE_POLICIES:
            raise ValueError(f"device must be one of {sorted(DEVICE_POLICIES)}")
        if self.audit_level not in AUDIT_LEVELS:
            raise ValueError(f"audit_level must be one of {sorted(AUDIT_LEVELS)}")
        if self.hsd_classification_backend not in HSD_CLASSIFICATION_BACKENDS:
            raise ValueError(
                "hsd_classification_backend must be one of "
                f"{sorted(HSD_CLASSIFICATION_BACKENDS)}"
            )
        if self.hf_hsd_device not in DEVICE_POLICIES:
            raise ValueError(f"hf_hsd_device must be one of {sorted(DEVICE_POLICIES)}")
        if self.dpmlm_device not in DEVICE_POLICIES:
            raise ValueError(f"dpmlm_device must be one of {sorted(DEVICE_POLICIES)}")
        if not 0.0 <= self.hf_hsd_threshold <= 1.0:
            raise ValueError("hf_hsd_threshold must be between 0 and 1")
        if self.hf_hsd_batch_size < 1:
            raise ValueError("hf_hsd_batch_size must be positive")
        if self.hf_hsd_max_length < 1:
            raise ValueError("hf_hsd_max_length must be positive")
        if self.dpmlm_epsilon <= 0:
            raise ValueError("dpmlm_epsilon must be positive")
        if self.dpmlm_max_rewrite_tokens < 0:
            raise ValueError("dpmlm_max_rewrite_tokens must be non-negative")
        if self.dpmlm_min_eligible_score < 0:
            raise ValueError("dpmlm_min_eligible_score must be non-negative")
        if self.dpmlm_top_k < 1:
            raise ValueError("dpmlm_top_k must be positive")
        if self.dpmlm_max_length < 1:
            raise ValueError("dpmlm_max_length must be positive")
        if self.dpmlm_min_row_style_risk < 0:
            raise ValueError("dpmlm_min_row_style_risk must be non-negative")
        if not 0 <= self.dpmlm_min_character_retention <= 1:
            raise ValueError("dpmlm_min_character_retention must be between 0 and 1")
        if self.dpmlm_max_length_drift < 0:
            raise ValueError("dpmlm_max_length_drift must be non-negative")
        if self.hsd_token_protect_threshold < 0:
            raise ValueError("hsd_token_protect_threshold must be non-negative")
        if self.max_model_batch_size < 1:
            raise ValueError("max_model_batch_size must be positive")
        if self.max_provider_rows is not None and self.max_provider_rows < 0:
            raise ValueError("max_provider_rows must be non-negative")
        if self.local_llm_timeout_seconds <= 0.0:
            raise ValueError("local_llm_timeout_seconds must be positive")
        if self.local_llm_batch_size < 1:
            raise ValueError("local_llm_batch_size must be positive")
        if self.author_group_min_repetitions < 2:
            raise ValueError("author_group_min_repetitions must be at least 2")
        if self.author_group_min_author_rows < 2:
            raise ValueError("author_group_min_author_rows must be at least 2")
