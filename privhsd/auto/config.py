"""Configuration for automatic provider/model orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from privhsd.metrics import METRIC_DEPTHS


AUTO_MODES = frozenset({"auto"})
AUTO_CAPABLE_MODES = frozenset({"auto", "utility", "balanced", "privacy"})
DEVICE_POLICIES = frozenset({"auto", "cpu", "cuda"})
AUDIT_LEVELS = frozenset({"summary", "row", "debug"})
DEFAULT_TOKEN_POLICY_MODEL_DIRS = (
    Path("data/outputs/token_policy_roberta_base.action_balanced_train30000.cuda"),
    Path("data/outputs/token_policy_hatebert.action_balanced_train30000.cuda"),
)
DEFAULT_HSD_ADVISORY_MODEL = "facebook/roberta-hate-speech-dynabench-r4-target"


@dataclass(frozen=True)
class AutoPipelineConfig:
    """Run-level auto pipeline settings.

    The automatic official path keeps balanced deterministic masking as the
    always-present baseline and treats optional systems as advisory evidence.
    """

    baseline_mode: str = "balanced"
    metric_depth: str = "fast"
    allow_model_download: bool = False
    device: str = "auto"
    max_model_batch_size: int = 16
    max_provider_rows: int | None = None
    disabled_providers: frozenset[str] = field(default_factory=frozenset)
    disabled_models: frozenset[str] = field(default_factory=frozenset)
    audit_level: str = "summary"
    provider_language: str = "en"
    gliner_model: str | None = None
    token_policy_model_dirs: tuple[Path, ...] = DEFAULT_TOKEN_POLICY_MODEL_DIRS
    token_policy_mode: str = "mean_prob"
    hsd_advisory_model: str = DEFAULT_HSD_ADVISORY_MODEL
    hsd_advisory_decision_threshold: float = 0.5
    hsd_advisory_large_drop_threshold: float = 0.25
    hsd_advisory_max_abs_drift: float = 0.35
    generalize_targets: bool | None = False
    style_scrub: bool = False
    official_mode: bool = True
    local_llm_enabled: bool = False

    def __post_init__(self) -> None:
        if self.baseline_mode not in {"utility", "balanced", "privacy"}:
            raise ValueError("baseline_mode must be utility, balanced, or privacy")
        if self.metric_depth not in METRIC_DEPTHS:
            raise ValueError(f"metric_depth must be one of {sorted(METRIC_DEPTHS)}")
        if self.device not in DEVICE_POLICIES:
            raise ValueError(f"device must be one of {sorted(DEVICE_POLICIES)}")
        if self.audit_level not in AUDIT_LEVELS:
            raise ValueError(f"audit_level must be one of {sorted(AUDIT_LEVELS)}")
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
