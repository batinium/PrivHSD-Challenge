"""Load versioned policy resources used by the local pipeline."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
import ast
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10.
    tomllib = None  # type: ignore[assignment]


def _parse_simple_toml(text: str) -> dict[str, Any]:
    """Parse the small TOML subset used by package resources on Python 3.10."""
    data: dict[str, Any] = {}
    section: dict[str, Any] | None = None
    pending_key: str | None = None
    pending_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if pending_key is not None:
            pending_lines.append(line)
            if line.endswith("]"):
                if section is None:
                    raise ValueError("resource TOML array outside a section")
                section[pending_key] = ast.literal_eval(" ".join(pending_lines))
                pending_key = None
                pending_lines = []
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            section = data.setdefault(name, {})
            continue
        if "=" not in line or section is None:
            raise ValueError(f"unsupported resource TOML line: {raw_line!r}")
        key, value = [part.strip() for part in line.split("=", 1)]
        if value.startswith("[") and not value.endswith("]"):
            pending_key = key
            pending_lines = [value]
            continue
        section[key] = ast.literal_eval(value)
    if pending_key is not None:
        raise ValueError("unterminated resource TOML array")
    return data


@lru_cache(maxsize=None)
def load_toml_resource(filename: str) -> dict[str, Any]:
    text = resources.files("contextsafe_hsd.resources").joinpath(filename).read_text(
        encoding="utf-8"
    )
    if tomllib is not None:
        return tomllib.loads(text)
    return _parse_simple_toml(text)


@lru_cache(maxsize=1)
def load_target_group_terms() -> dict[str, tuple[str, ...]]:
    data = load_toml_resource("target_cues.toml")
    return {
        category: tuple(str(term) for term in terms)
        for category, terms in data["target_group_terms"].items()
    }


@lru_cache(maxsize=None)
def load_utility_cue_terms(section: str) -> tuple[str, ...]:
    data = load_toml_resource("utility_cues.toml")
    return tuple(str(term) for term in data[section]["terms"])

