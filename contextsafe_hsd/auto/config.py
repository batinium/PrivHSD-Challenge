"""Configuration for automatic provider/model orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from contextsafe_hsd.metrics import METRIC_DEPTHS


AUTO_MODES = frozenset({"auto"})
AUTO_CAPABLE_MODES = frozenset({"auto", "utility", "balanced", "privacy"})
DEVICE_POLICIES = frozenset({"auto", "cpu", "cuda"})
AUDIT_LEVELS = frozenset({"summary", "row", "debug"})
GLINER_PROFILES = frozenset({"general", "pii"})
HSD_CLASSIFICATION_BACKENDS = frozenset({"ml", "local_llm"})
DEFAULT_TOKEN_POLICY_MODEL_DIRS = (
    Path("data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda"),
    Path("data/outputs/token_policy_hatebert.action_balanced_train30000.cuda"),
)
DEFAULT_HSD_ADVISORY_MODEL = "facebook/roberta-hate-speech-dynabench-r4-target"
DEFAULT_HSD_ADVISORY_MODELS = (
    DEFAULT_HSD_ADVISORY_MODEL,
    "cardiffnlp/twitter-roberta-base-hate-latest",
)


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
    gliner_model: str | None = None
    gliner_profile: str = "general"
    token_policy_model_dirs: tuple[Path, ...] = DEFAULT_TOKEN_POLICY_MODEL_DIRS
    token_policy_mode: str = "mean_prob"
    enable_token_policy: bool = False
    hsd_advisory_model: str = DEFAULT_HSD_ADVISORY_MODEL
    hsd_advisory_models: tuple[str, ...] = DEFAULT_HSD_ADVISORY_MODELS
    hsd_advisory_decision_threshold: float = 0.5
    hsd_advisory_large_drop_threshold: float = 0.25
    hsd_advisory_max_abs_drift: float = 0.35
    hsd_classification_backend: str = "ml"
    generalize_targets: bool | None = False
    style_scrub: bool = False
    official_mode: bool = True
    local_llm_enabled: bool = False
    local_llm_endpoint: str = "http://localhost:1234/v1/chat/completions"
    local_llm_model: str = "openai/gpt-oss-20b"
    local_llm_timeout_seconds: float = 120.0
    local_llm_batch_size: int = 10
    local_llm_enable_pii_suggestions: bool = True
    local_llm_require_structured_output: bool = True
    author_group_masking: bool = False
    author_group_col: str | None = None
    author_group_min_repetitions: int = 2
    author_group_min_author_rows: int = 2

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "gliner_profile",
            self.gliner_profile.strip().lower(),
        )
        backend = self.hsd_classification_backend.strip().lower().replace("-", "_")
        object.__setattr__(self, "hsd_classification_backend", backend)
        disabled_models = frozenset(
            model.strip()
            for model in self.disabled_models
            if model and model.strip()
        )
        if backend == "local_llm":
            disabled_models = disabled_models | {"hsd_advisory"}
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
        if self.author_group_col is not None:
            object.__setattr__(
                self,
                "author_group_col",
                self.author_group_col.strip() or None,
            )
        normalized_hsd_models = tuple(
            dict.fromkeys(
                model.strip()
                for model in self.hsd_advisory_models
                if model and model.strip()
            )
        )
        if not normalized_hsd_models and self.hsd_advisory_model:
            normalized_hsd_models = (self.hsd_advisory_model.strip(),)
        object.__setattr__(self, "hsd_advisory_models", normalized_hsd_models)
        if self.baseline_mode not in {"utility", "balanced", "privacy"}:
            raise ValueError("baseline_mode must be utility, balanced, or privacy")
        if self.metric_depth not in METRIC_DEPTHS:
            raise ValueError(f"metric_depth must be one of {sorted(METRIC_DEPTHS)}")
        if self.device not in DEVICE_POLICIES:
            raise ValueError(f"device must be one of {sorted(DEVICE_POLICIES)}")
        if self.audit_level not in AUDIT_LEVELS:
            raise ValueError(f"audit_level must be one of {sorted(AUDIT_LEVELS)}")
        if self.gliner_profile not in GLINER_PROFILES:
            raise ValueError(f"gliner_profile must be one of {sorted(GLINER_PROFILES)}")
        if self.hsd_classification_backend not in HSD_CLASSIFICATION_BACKENDS:
            raise ValueError(
                "hsd_classification_backend must be one of "
                f"{sorted(HSD_CLASSIFICATION_BACKENDS)}"
            )
        if self.max_model_batch_size < 1:
            raise ValueError("max_model_batch_size must be positive")
        if self.max_provider_rows is not None and self.max_provider_rows < 0:
            raise ValueError("max_provider_rows must be non-negative")
        if not 0.0 < self.hsd_advisory_decision_threshold < 1.0:
            raise ValueError("hsd_advisory_decision_threshold must be between 0 and 1")
        if self.hsd_advisory_large_drop_threshold < 0.0:
            raise ValueError("hsd_advisory_large_drop_threshold must be non-negative")
        if self.hsd_advisory_max_abs_drift < 0.0:
            raise ValueError("hsd_advisory_max_abs_drift must be non-negative")
        if self.local_llm_timeout_seconds <= 0.0:
            raise ValueError("local_llm_timeout_seconds must be positive")
        if self.local_llm_batch_size < 1:
            raise ValueError("local_llm_batch_size must be positive")
        if self.author_group_min_repetitions < 2:
            raise ValueError("author_group_min_repetitions must be at least 2")
        if self.author_group_min_author_rows < 2:
            raise ValueError("author_group_min_author_rows must be at least 2")
