"""Run-level resource ownership for automatic mode."""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
from typing import Any, Callable, Mapping

from contextsafe_hsd.models.dpmlm_rewrite_runtime import normalize_token
from contextsafe_hsd.span_providers.base import SpanProvider
from contextsafe_hsd.span_providers.presidio import PresidioAugmentError, PresidioSpanProvider, load_presidio_analyzer
from contextsafe_hsd.span_providers.scrubadub_provider import (
    ScrubadubProviderError,
    load_scrubadub_provider,
)

from .config import AutoPipelineConfig
from .model_registry import (
    discover_dpmlm_rewriter,
    discover_hf_classifier,
    discover_local_llm,
)


ProviderFactory = Callable[["AutoPipelineContext"], SpanProvider]
ModelFactory = Callable[["AutoPipelineContext"], Any]


def has_module(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def error_status(exc: Exception, *, kind: str) -> dict[str, Any]:
    return {
        "status": "error",
        "kind": kind,
        "error_class": type(exc).__name__,
        "detail": str(exc),
    }


@dataclass
class AutoPipelineContext:
    """Own providers, models, load counters, and raw-text-free status."""

    config: AutoPipelineConfig
    provider_factories: Mapping[str, ProviderFactory] = field(default_factory=dict)
    model_factories: Mapping[str, ModelFactory] = field(default_factory=dict)
    providers: dict[str, SpanProvider] = field(default_factory=dict)
    models: dict[str, Any] = field(default_factory=dict)
    provider_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    model_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    provider_load_counts: Counter[str] = field(default_factory=Counter)
    model_load_counts: Counter[str] = field(default_factory=Counter)
    audit_counters: Counter[str] = field(default_factory=Counter)
    _hsd_protected_tokens_by_row: dict[str, frozenset[str]] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _hsd_token_guard_status: dict[str, Any] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    @classmethod
    def create(
        cls,
        config: AutoPipelineConfig | None = None,
        *,
        provider_factories: Mapping[str, ProviderFactory] | None = None,
        model_factories: Mapping[str, ModelFactory] | None = None,
    ) -> "AutoPipelineContext":
        context = cls(
            config=config or AutoPipelineConfig(),
            provider_factories=provider_factories or {},
            model_factories=model_factories or {},
        )
        context.discover()
        context.load_startup_providers()
        return context

    def discover(self) -> None:
        self.provider_status["deterministic"] = {"status": "ready", "kind": "provider"}
        self._discover_provider("presidio", "presidio_analyzer")
        self._discover_provider("scrubadub", "scrubadub")
        self.model_status["local_llm"] = discover_local_llm(self.config)
        self.model_status["hf_classifier"] = discover_hf_classifier(self.config)
        self.model_status["dpmlm_rewriter"] = discover_dpmlm_rewriter(self.config)
        for name in self.provider_factories:
            self.provider_status[name] = {
                "status": "available",
                "kind": "provider",
                "source": "injected_factory",
            }
        for name in self.model_factories:
            self.model_status[name] = {
                "status": "available",
                "kind": "model",
                "load": "lazy",
                "source": "injected_factory",
            }

    def _discover_provider(self, name: str, module_name: str) -> None:
        if name in self.config.disabled_providers:
            self.provider_status[name] = {"status": "disabled", "kind": "provider"}
        elif has_module(module_name):
            self.provider_status[name] = {"status": "available", "kind": "provider"}
        else:
            self.provider_status[name] = {
                "status": "missing_dependency",
                "kind": "provider",
                "missing": [module_name],
            }

    def load_startup_providers(self) -> None:
        # Discovery is cheap and eager; provider initialization is lazy so
        # routing can avoid heavy optional model loads on rows that do not need
        # provider evidence.
        return

    def ensure_provider(self, name: str) -> SpanProvider | None:
        if name in self.providers:
            return self.providers[name]
        status = self.provider_status.get(name, {})
        if status.get("status") not in {"available", "download_allowed"}:
            return None
        try:
            provider = self._load_provider(name)
        except Exception as exc:
            self.provider_status[name] = error_status(exc, kind="provider")
            self.audit_counters[f"provider_error:{name}:{type(exc).__name__}"] += 1
            return None
        self.providers[name] = provider
        self.provider_load_counts[name] += 1
        self.provider_status[name] = {
            **status,
            "status": "ready",
            "load_count": self.provider_load_counts[name],
        }
        return provider

    def _load_provider(self, name: str) -> SpanProvider:
        if name in self.provider_factories:
            return self.provider_factories[name](self)
        if name == "presidio":
            return PresidioSpanProvider(
                analyzer=load_presidio_analyzer(),
                language=self.config.provider_language,
            )
        if name == "scrubadub":
            return load_scrubadub_provider()
        raise ValueError(f"unknown auto provider {name!r}")

    def optional_span_providers(self) -> list[SpanProvider]:
        providers = []
        for name in ("presidio", "scrubadub", *self.provider_factories):
            provider = self.ensure_provider(name)
            if provider is not None:
                providers.append(provider)
        return providers

    def ensure_model(self, name: str) -> Any | None:
        if name in self.models:
            return self.models[name]
        status = self.model_status.get(name, {})
        if status.get("status") not in {"available", "download_allowed"}:
            return None
        try:
            model = self._load_model(name)
        except Exception as exc:
            self.model_status[name] = error_status(exc, kind="model")
            self.audit_counters[f"model_error:{name}:{type(exc).__name__}"] += 1
            return None
        self.models[name] = model
        self.model_load_counts[name] += 1
        self.model_status[name] = {
            **status,
            "status": "ready",
            "load_count": self.model_load_counts[name],
            **getattr(model, "status_metadata", lambda: {})(),
        }
        return model

    def _load_model(self, name: str) -> Any:
        if name in self.model_factories:
            return self.model_factories[name](self)
        if name == "local_llm":
            from contextsafe_hsd.models.local_llm_hsd_review_runtime import (
                LocalLlmHsdReviewRuntime,
            )

            return LocalLlmHsdReviewRuntime(
                endpoint=self.config.local_llm_endpoint,
                model_id=self.config.local_llm_model,
                timeout_seconds=self.config.local_llm_timeout_seconds,
                enable_pii_suggestions=self.config.local_llm_enable_pii_suggestions,
                require_structured_output=self.config.local_llm_require_structured_output,
            )
        if name == "hf_classifier":
            from contextsafe_hsd.models.hf_hsd_classifier_runtime import (
                HfHsdClassifierRuntime,
            )

            return HfHsdClassifierRuntime(
                model_path=self.config.hf_hsd_model_path,
                threshold=self.config.hf_hsd_threshold,
                device=self.config.hf_hsd_device,
                max_length=self.config.hf_hsd_max_length,
            )
        if name == "dpmlm_rewriter":
            from contextsafe_hsd.models.dpmlm_rewrite_runtime import (
                DpmlmRewriteRuntime,
            )

            return DpmlmRewriteRuntime(
                model_path=self.config.dpmlm_model_path,
                device=self.config.dpmlm_device,
                epsilon=self.config.dpmlm_epsilon,
                top_k=self.config.dpmlm_top_k,
                max_length=self.config.dpmlm_max_length,
            )
        raise ValueError(f"unknown auto model {name!r}")

    def ensure_local_llm_review(self) -> Any | None:
        return self.ensure_model("local_llm")

    def ensure_hf_classifier(self) -> Any | None:
        return self.ensure_model("hf_classifier")

    def ensure_dpmlm_rewriter(self) -> Any | None:
        return self.ensure_model("dpmlm_rewriter")

    def hsd_protected_tokens_for(
        self,
        *,
        row_id: str,
        row_index: int,
    ) -> frozenset[str]:
        if not self.config.hsd_token_importance_path:
            return frozenset()
        mapping = self._load_hsd_protected_tokens()
        keys = (str(row_id), f"index:{row_index}")
        protected: set[str] = set()
        for key in keys:
            protected.update(mapping.get(key, frozenset()))
        return frozenset(protected)

    def _load_hsd_protected_tokens(self) -> dict[str, frozenset[str]]:
        if self._hsd_protected_tokens_by_row is not None:
            return self._hsd_protected_tokens_by_row
        path = Path(str(self.config.hsd_token_importance_path))
        row_tokens: dict[str, set[str]] = {}
        token_count = 0
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    try:
                        importance = float(row.get("abs_delta_hate_score") or 0.0)
                    except ValueError:
                        importance = 0.0
                    if importance < self.config.hsd_token_protect_threshold:
                        continue
                    token = normalize_token(str(row.get("token") or ""))
                    if not token:
                        continue
                    row_id = str(row.get("row_id") or "").strip()
                    row_index = str(row.get("row_index") or "").strip()
                    if row_id:
                        row_tokens.setdefault(row_id, set()).add(token)
                    if row_index:
                        row_tokens.setdefault(f"index:{row_index}", set()).add(token)
                    token_count += 1
        except OSError as exc:
            self._hsd_token_guard_status = error_status(exc, kind="hsd_token_guard")
            self.audit_counters[
                f"hsd_token_guard_error:{type(exc).__name__}"
            ] += 1
            self._hsd_protected_tokens_by_row = {}
            return self._hsd_protected_tokens_by_row

        self._hsd_protected_tokens_by_row = {
            key: frozenset(tokens) for key, tokens in row_tokens.items()
        }
        self._hsd_token_guard_status = {
            "status": "ready",
            "kind": "hsd_token_guard",
            "path": str(path),
            "threshold": self.config.hsd_token_protect_threshold,
            "row_key_count": len(self._hsd_protected_tokens_by_row),
            "token_count": token_count,
        }
        return self._hsd_protected_tokens_by_row

    def audit_status(self) -> dict[str, Any]:
        if self.config.hsd_token_importance_path and not self._hsd_token_guard_status:
            self._load_hsd_protected_tokens()
        return {
            "providers": self.provider_status,
            "models": self.model_status,
            "hsd_token_guard": self._hsd_token_guard_status
            or {
                "status": "disabled",
                "kind": "hsd_token_guard",
            },
            "provider_load_counts": dict(sorted(self.provider_load_counts.items())),
            "model_load_counts": dict(sorted(self.model_load_counts.items())),
            "audit_counters": dict(sorted(self.audit_counters.items())),
        }


__all__ = [
    "AutoPipelineContext",
    "PresidioAugmentError",
    "ScrubadubProviderError",
]
