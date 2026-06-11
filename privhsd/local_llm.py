"""Optional local LLM candidate generation through OpenAI-compatible servers."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any
from urllib import error, request

from .csv_pipeline import read_csv, write_csv, write_json
from .metrics import UTILITY_CUES, row_metric, target_cue_counts


DEFAULT_ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
DEFAULT_MODEL = "local-model"
DEFAULT_SAMPLE_SIZE = 25
LOCAL_LLM_WARNING = (
    "Local LLM outputs are candidate rewrites only. They must be reranked and "
    "validated before any submission; generic anonymization prompting is not "
    "used as the product."
)


class LocalLlmError(ValueError):
    pass


def rounded(value: float) -> float:
    return round(float(value), 4)


def protected_cues_for_text(text: str) -> dict[str, Any]:
    lowered = text.lower()
    utility_cues = [
        cue for cue in UTILITY_CUES if cue in lowered
    ]
    target_terms, target_cues = target_cue_counts(text)
    return {
        "utility_cues": sorted(set(utility_cues)),
        "target_categories": sorted(target_cues),
        "target_term_count": sum(target_terms.values()),
        "negation_modality_instruction": (
            "Preserve negation, threat/action terms, modality such as should/must, "
            "and target-group wording unless the candidate is later rejected."
        ),
    }


def prompt_messages(text: str) -> list[dict[str, str]]:
    protected = protected_cues_for_text(text)
    return [
        {
            "role": "system",
            "content": (
                "You generate one privacy-preserving candidate rewrite for a "
                "hate-speech-detection dataset. Rewrite only author/style-bearing "
                "surface cues. Preserve target groups, hateful action cues, "
                "negation, threats, modality, and core meaning. Return only JSON "
                "matching this schema: {\"privatized_text\": string, "
                "\"preserved_cues\": [string], \"notes\": string}."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "text": text,
                    "protected_cues": protected,
                },
                ensure_ascii=False,
            ),
        },
    ]


def post_chat_completion(
    *,
    endpoint: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LocalLlmError(f"local LLM request failed: {exc}") from exc


def response_text(response: dict[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LocalLlmError("local LLM response did not contain message content") from exc
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LocalLlmError("local LLM response content was not valid JSON") from exc
    candidate = value.get("privatized_text")
    if not isinstance(candidate, str) or not candidate.strip():
        raise LocalLlmError("local LLM JSON missing non-empty privatized_text")
    return candidate.strip()


def validate_candidate(
    original: str,
    candidate: str,
    *,
    min_target_retention: float,
    min_utility_retention: float,
    max_length_drift: float,
) -> tuple[bool, dict[str, Any]]:
    metrics = row_metric(original, candidate)
    length_drift = abs(len(candidate) - len(original)) / max(len(original), 1)
    checks = {
        "target_cue_retention": metrics["target_cue_retention"],
        "utility_cue_retention": metrics["utility_cue_retention"],
        "character_utility_retention": metrics["character_utility_retention"],
        "length_drift": rounded(length_drift),
        "min_target_retention": min_target_retention,
        "min_utility_retention": min_utility_retention,
        "max_length_drift": max_length_drift,
    }
    accepted = (
        metrics["target_cue_retention"] >= min_target_retention
        and metrics["utility_cue_retention"] >= min_utility_retention
        and length_drift <= max_length_drift
    )
    return accepted, checks


def run_local_llm_candidates(
    input_path: Path,
    output_path: Path,
    *,
    text_col: str,
    id_col: str | None = None,
    candidate_col: str = "llm_candidate",
    report_path: Path | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = DEFAULT_MODEL,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    timeout: float = 10.0,
    min_target_retention: float = 1.0,
    min_utility_retention: float = 1.0,
    max_length_drift: float = 0.6,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    if text_col not in fieldnames:
        raise LocalLlmError(f"{input_path}: missing text column {text_col!r}")
    if id_col and id_col not in fieldnames:
        raise LocalLlmError(f"{input_path}: missing id column {id_col!r}")
    if sample_size < 0:
        raise LocalLlmError("--sample-size must be non-negative")
    output_fieldnames = list(fieldnames)
    if candidate_col not in output_fieldnames:
        output_fieldnames.append(candidate_col)

    limit = len(rows) if sample_size <= 0 else min(sample_size, len(rows))
    output_rows = []
    audit_rows: list[dict[str, Any]] = []
    accepted_count = 0
    start = time.perf_counter()
    first_error: str | None = None
    for row_index, row in enumerate(rows, start=1):
        output_row = dict(row)
        candidate = ""
        row_status = "not_requested"
        checks: dict[str, Any] | None = None
        detail = None
        if row_index <= limit:
            original = str(row.get(text_col, "") or "")
            try:
                response = post_chat_completion(
                    endpoint=endpoint,
                    model=model,
                    messages=prompt_messages(original),
                    timeout=timeout,
                )
                proposed = response_text(response)
                accepted, checks = validate_candidate(
                    original,
                    proposed,
                    min_target_retention=min_target_retention,
                    min_utility_retention=min_utility_retention,
                    max_length_drift=max_length_drift,
                )
                if accepted:
                    candidate = proposed
                    accepted_count += 1
                    row_status = "accepted"
                else:
                    row_status = "rejected_by_checks"
            except LocalLlmError as exc:
                row_status = "failed"
                detail = str(exc)
                first_error = first_error or detail
        output_row[candidate_col] = candidate
        output_rows.append(output_row)
        if row_index <= limit:
            audit_rows.append(
                {
                    "row_index": row_index,
                    "row_id": str(row.get(id_col, "") or row_index) if id_col else str(row_index),
                    "status": row_status,
                    "checks": checks,
                    "detail": detail,
                }
            )
    write_csv(output_path, output_rows, output_fieldnames)
    status = "ok" if accepted_count else "skipped"
    report = {
        "input": str(input_path),
        "output": str(output_path),
        "report": str(report_path) if report_path else None,
        "generator_type": "local_openai_compatible_llm",
        "status": status,
        "skip_reason": "no_accepted_candidates" if status == "skipped" else None,
        "detail": first_error,
        "warning": LOCAL_LLM_WARNING,
        "endpoint": endpoint,
        "model": model,
        "columns": {
            "text_col": text_col,
            "id_col": id_col,
            "candidate_col": candidate_col,
        },
        "sample": {
            "requested_sample_size": sample_size,
            "sample_size": limit,
            "source_row_count": len(rows),
            "strategy": "first_n_rows",
        },
        "accepted_count": accepted_count,
        "runtime_seconds": rounded(time.perf_counter() - start),
        "rows": audit_rows,
        "next_step": (
            "Run rerank-candidates with --candidate-col "
            f"{candidate_col}; do not submit raw LLM candidates directly."
        ),
    }
    if report_path:
        write_json(report_path, report)
    return report
