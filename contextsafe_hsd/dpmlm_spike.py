"""Bounded DPMLM rewrite spike harness.

This module deliberately does not integrate DPMLM into the core anonymizer. It
records whether a supported local backend is available, the protected cue
configuration that a rewrite would need to respect, and structured blockers when
the experiment cannot run.
"""

from __future__ import annotations

from collections import Counter
import importlib
import importlib.util
from pathlib import Path
import time
from typing import Any

from .csv_pipeline import read_csv, write_json
from .detectors import TARGET_GROUP_TERMS
from .metrics import UTILITY_CUES, aggregate_metrics, row_metric
from .row_ids import report_row_id
from .style import ACTION_TERMS, NEGATION_MODALITY_TERMS


DEFAULT_EPSILONS = (25.0, 50.0)
DEFAULT_SAMPLE_SIZE = 25
SUPPORTED_BACKENDS = ("dpmlm", "private_transformers", "opendp")
DPMLM_WARNING = (
    "This is a bounded experiment harness only. DPMLM is not part of core "
    "privhsd anonymize, and outputs should not be used for submission unless "
    "they improve measured privacy/HSD tradeoffs and are reproducible enough "
    "for audit."
)


class DpmlmSpikeError(ValueError):
    pass


def rounded(value: float) -> float:
    return round(float(value), 4)


def validate_columns(
    input_path: Path,
    fieldnames: list[str],
    *,
    text_col: str,
    id_col: str | None,
    privatized_col: str | None,
) -> None:
    missing = [column for column in (text_col, id_col, privatized_col) if column]
    missing = [column for column in missing if column not in fieldnames]
    if missing:
        raise DpmlmSpikeError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )


def detect_backends() -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    for backend in SUPPORTED_BACKENDS:
        installed = importlib.util.find_spec(backend) is not None
        importable = False
        error = None
        if installed:
            try:
                importlib.import_module(backend)
            except Exception as exc:  # pragma: no cover - environment dependent
                error = f"{type(exc).__name__}: {exc}"
            else:
                importable = True
        statuses[backend] = {
            "installed": installed,
            "importable": importable,
            "error": error,
        }
    return statuses


def normalize_backend_statuses(
    backends: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    for backend in SUPPORTED_BACKENDS:
        status = backends.get(backend, False)
        if isinstance(status, bool):
            statuses[backend] = {
                "installed": status,
                "importable": status,
                "error": None,
            }
        else:
            statuses[backend] = {
                "installed": bool(status.get("installed", False)),
                "importable": bool(status.get("importable", False)),
                "error": status.get("error"),
            }
    return statuses


def protected_cue_manifest() -> dict[str, Any]:
    target_terms = sorted(
        {
            term.lower()
            for terms in TARGET_GROUP_TERMS.values()
            for term in terms
        }
    )
    utility_terms = sorted({cue.lower() for cue in UTILITY_CUES})
    action_terms = sorted(ACTION_TERMS)
    negation_modality_terms = sorted(NEGATION_MODALITY_TERMS)
    token_set = sorted(
        set(action_terms)
        | set(negation_modality_terms)
        | {
            token
            for phrase in [*target_terms, *utility_terms]
            for token in phrase.split()
        }
    )
    return {
        "target_terms": target_terms,
        "utility_terms": utility_terms,
        "action_terms": action_terms,
        "negation_modality_terms": negation_modality_terms,
        "protected_token_count": len(token_set),
        "protected_tokens": token_set,
    }


def collect_sample_rows(
    rows: list[dict[str, str]],
    *,
    text_col: str,
    id_col: str | None,
    sample_size: int,
) -> list[dict[str, Any]]:
    limit = len(rows) if sample_size <= 0 else min(sample_size, len(rows))
    sampled = []
    for row_index, row in enumerate(rows[:limit], start=1):
        sampled.append(
            {
                "row_index": row_index,
                "row_id": report_row_id(row, row_index=row_index, id_col=id_col),
                "text_length": len(str(row.get(text_col, "") or "")),
            }
        )
    return sampled


def existing_privatized_baseline(
    rows: list[dict[str, str]],
    *,
    text_col: str,
    privatized_col: str | None,
    sample_size: int,
) -> dict[str, Any] | None:
    if not privatized_col:
        return None
    limit = len(rows) if sample_size <= 0 else min(sample_size, len(rows))
    metrics = [
        row_metric(
            str(row.get(text_col, "") or ""),
            str(row.get(privatized_col, "") or ""),
        )
        for row in rows[:limit]
    ]
    return {
        "description": "Existing privatized-column baseline; not DPMLM output.",
        "metrics": aggregate_metrics(metrics),
    }


def skipped_epsilon_result(
    epsilon: float,
    *,
    sample_size: int,
    blockers: list[str],
    skip_reason: str,
) -> dict[str, Any]:
    return {
        "epsilon": epsilon,
        "status": "skipped",
        "skip_reason": skip_reason,
        "runtime_seconds": 0.0,
        "sample_size": sample_size,
        "deterministic": None,
        "utility_drift": None,
        "author_risk_drop": None,
        "protected_cue_retention": None,
        "blockers": blockers,
    }


def run_dpmlm_spike(
    input_path: Path,
    *,
    text_col: str,
    id_col: str | None = None,
    privatized_col: str | None = None,
    output_path: Path | None = None,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    epsilons: list[float] | None = None,
    backend: str = "auto",
    random_seed: int = 0,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        privatized_col=privatized_col,
    )
    epsilons = epsilons or list(DEFAULT_EPSILONS)
    if not epsilons:
        raise DpmlmSpikeError("at least one --epsilon value is required")
    if any(epsilon <= 0 for epsilon in epsilons):
        raise DpmlmSpikeError("--epsilon values must be positive")
    if sample_size < 0:
        raise DpmlmSpikeError("--sample-size must be non-negative")

    start = time.perf_counter()
    backends = normalize_backend_statuses(detect_backends())
    backend_detected = {
        name: status["importable"] for name, status in backends.items()
    }
    available_backends = [
        name for name, status in backends.items() if status["importable"]
    ]
    backend_available = backend == "auto" and bool(available_backends)
    if backend != "auto":
        backend_available = backends.get(
            backend,
            {"importable": False},
        )["importable"]
    sampled_rows = collect_sample_rows(
        rows,
        text_col=text_col,
        id_col=id_col,
        sample_size=sample_size,
    )
    blockers = []
    skip_reason = "no_supported_dpmlm_backend"
    if not backend_available:
        blockers.append(
            "No supported local DPMLM backend is installed "
            f"({', '.join(SUPPORTED_BACKENDS)} checked)."
        )
        installed_blocked = [
            f"{name}: {status['error']}"
            for name, status in backends.items()
            if status["installed"] and not status["importable"] and status["error"]
        ]
        if installed_blocked:
            blockers.append(
                "Installed backend import failed: " + "; ".join(installed_blocked)
            )
        blockers.append(
            "Protected-cue rewrite policy is defined, but no backend-specific "
            "token-freezing API is available to exercise it."
        )
    if backend != "auto" and backend not in SUPPORTED_BACKENDS:
        blockers.append(f"Unsupported backend requested: {backend}")

    selected_backend = None
    if backend_available:
        selected_backend = available_backends[0] if backend == "auto" else backend
        skip_reason = "adapter_not_implemented"
        blockers.append(
            "A potential backend was detected, but this harness has no audited "
            "DPMLM adapter yet; leaving integration blocked until adapter tests "
            "prove cue protection and determinism."
        )

    effective_sample_size = len(sampled_rows)
    epsilon_results = [
        skipped_epsilon_result(
            epsilon,
            sample_size=effective_sample_size,
            blockers=blockers,
            skip_reason=skip_reason,
        )
        for epsilon in epsilons
    ]
    status = "skipped"
    result = {
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "spike_type": "dpmlm_protected_cue_rewrite",
        "status": status,
        "warning": DPMLM_WARNING,
        "columns": {
            "text_col": text_col,
            "id_col": id_col,
            "privatized_col": privatized_col,
        },
        "sample": {
            "requested_sample_size": sample_size,
            "sample_size": effective_sample_size,
            "source_row_count": len(rows),
            "strategy": "first_n_rows",
            "rows": sampled_rows,
        },
        "privacy_parameters": {
            "epsilons": epsilons,
            "random_seed": random_seed,
        },
        "backend": {
            "requested": backend,
            "selected": selected_backend,
            "detected": backend_detected,
            "details": backends,
        },
        "protected_cues": protected_cue_manifest(),
        "existing_privatized_baseline": existing_privatized_baseline(
            rows,
            text_col=text_col,
            privatized_col=privatized_col,
            sample_size=sample_size,
        ),
        "epsilon_results": epsilon_results,
        "runtime_seconds": rounded(time.perf_counter() - start),
        "blockers": blockers,
        "blocker_counts": dict(sorted(Counter(blockers).items())),
    }
    if output_path:
        write_json(output_path, result)
    return result
