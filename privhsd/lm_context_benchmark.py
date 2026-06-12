"""Local LM Studio context-labeler benchmark."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import socket
import statistics
import time
from typing import Any
from urllib import error, request

from .context import CONTEXT_TAGS, analyze_context
from .csv_pipeline import read_csv, write_json
from .detectors import TARGET_GROUP_TERMS
from .style import ACTION_TERMS, NEGATION_MODALITY_TERMS


DEFAULT_ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
DEFAULT_SAMPLE_SIZE = 20
DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_TOKENS = 192
DEFAULT_MODES = ("json", "tagged", "word_lists", "binary_tags")
VALID_UNCERTAINTY = {"low", "medium", "high"}


class LmContextBenchmarkError(ValueError):
    pass


class BenchmarkRequestError(RuntimeError):
    def __init__(self, kind: str, detail: str):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


def rounded(value: float) -> float:
    return round(float(value), 4)


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * pct))
    return rounded(ordered[index])


def clean_list_value(value: Any) -> list[str]:
    if isinstance(value, str):
        items = value.replace(";", ",").split(",")
    elif isinstance(value, list):
        items = value
    else:
        return []
    result = []
    for item in items:
        text = str(item or "").strip().strip("-* ")
        if text:
            result.append(text)
    return result


def normalize_tags(tags: list[str]) -> list[str]:
    allowed = set(CONTEXT_TAGS)
    normalized = []
    for tag in tags:
        value = str(tag).strip().lower().replace("-", "_").replace(" ", "_")
        if value == "negation":
            value = "negated_hate"
        if value in allowed and value not in normalized:
            normalized.append(value)
    return normalized


def parse_json_object(content: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    stripped = content.strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return value
    for start, character in enumerate(stripped):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stripped[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise LmContextBenchmarkError("content did not contain a JSON object")


def parsed_result(
    *,
    mode: str,
    tags: list[str],
    protected_phrases: list[str] | None = None,
    maskable_phrases: list[str] | None = None,
    uncertainty: str | None = None,
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    normalized_tags = normalize_tags(tags)
    if not normalized_tags and not protected_phrases and not maskable_phrases:
        raise LmContextBenchmarkError("parsed output had no usable fields")
    uncertainty_value = str(uncertainty or "").strip().lower()
    if uncertainty_value not in VALID_UNCERTAINTY:
        uncertainty_value = "unknown"
    return {
        "mode": mode,
        "context_tags": normalized_tags,
        "protected_phrase_count": len(protected_phrases or []),
        "maskable_phrase_count": len(maskable_phrases or []),
        "protected_phrases": protected_phrases or [],
        "maskable_phrases": maskable_phrases or [],
        "uncertainty": uncertainty_value,
        "reason_code_count": len(reason_codes or []),
    }


def parse_json_mode(content: str) -> dict[str, Any]:
    value = parse_json_object(content)
    return parsed_result(
        mode="json",
        tags=clean_list_value(value.get("context_tags")),
        protected_phrases=clean_list_value(value.get("protected_phrases")),
        maskable_phrases=clean_list_value(value.get("maskable_phrases")),
        uncertainty=str(value.get("uncertainty", "")),
        reason_codes=clean_list_value(value.get("reason_codes")),
    )


def line_map(content: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in content.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
        elif "=" in line:
            key, value = line.split("=", 1)
        else:
            continue
        result[key.strip().lower().replace(" ", "_")] = value.strip()
    return result


def parse_tagged_mode(content: str) -> dict[str, Any]:
    fields = line_map(content)
    return parsed_result(
        mode="tagged",
        tags=clean_list_value(fields.get("tags", "")),
        protected_phrases=clean_list_value(fields.get("protect", "")),
        maskable_phrases=clean_list_value(fields.get("maskable", "")),
        uncertainty=fields.get("uncertainty"),
        reason_codes=clean_list_value(fields.get("reasons", "")),
    )


def parse_word_lists_mode(content: str) -> dict[str, Any]:
    fields = line_map(content)
    return parsed_result(
        mode="word_lists",
        tags=clean_list_value(fields.get("context_tags", "")),
        protected_phrases=clean_list_value(fields.get("protected_words", "")),
        maskable_phrases=clean_list_value(fields.get("maskable_words", "")),
        uncertainty=fields.get("uncertainty"),
        reason_codes=clean_list_value(fields.get("reason_codes", "")),
    )


def parse_binary_tags_mode(content: str) -> dict[str, Any]:
    fields = line_map(content)
    tags: list[str] = []
    binary_map = {
        "protected_target": "protected_target",
        "hostile_action": "hostile_action",
        "negation": "negated_hate",
        "negated_hate": "negated_hate",
        "counterspeech": "counterspeech",
        "quoted_or_reported": "quoted_or_reported",
        "quote": "quoted_or_reported",
        "threat": "threat",
        "exclusion": "exclusion",
        "dehumanization": "dehumanization",
    }
    for key, tag in binary_map.items():
        if fields.get(key, "").strip().lower() in {"yes", "true", "1"}:
            tags.append(tag)
    return parsed_result(
        mode="binary_tags",
        tags=tags,
        protected_phrases=clean_list_value(fields.get("protect", "")),
        maskable_phrases=clean_list_value(fields.get("mask", "")),
        uncertainty=fields.get("uncertainty"),
    )


PARSERS = {
    "json": parse_json_mode,
    "tagged": parse_tagged_mode,
    "word_lists": parse_word_lists_mode,
    "binary_tags": parse_binary_tags_mode,
}


def cue_terms() -> set[str]:
    terms = set(ACTION_TERMS) | set(NEGATION_MODALITY_TERMS)
    for values in TARGET_GROUP_TERMS.values():
        terms.update(term.lower() for term in values)
    return terms


PROTECTED_CUE_TERMS = cue_terms()


def phrase_has_protected_cue(phrase: str) -> bool:
    lowered = phrase.lower()
    return any(term in lowered for term in PROTECTED_CUE_TERMS)


def prompt_messages(text: str, mode: str) -> list[dict[str, str]]:
    mode_instruction = {
        "json": (
            "Return only valid JSON with context_tags, protected_phrases, "
            "maskable_phrases, uncertainty, and reason_codes."
        ),
        "tagged": (
            "Return tagged lines only: TAGS:, PROTECT:, MASKABLE:, "
            "UNCERTAINTY:, REASONS:."
        ),
        "word_lists": (
            "Return compact lists only: protected_words:, maskable_words:, "
            "context_tags:, uncertainty:."
        ),
        "binary_tags": (
            "Return yes/no lines only for protected_target, hostile_action, "
            "negation, counterspeech, quoted_or_reported, threat, exclusion, "
            "plus protect= and mask=."
        ),
    }[mode]
    return [
        {
            "role": "system",
            "content": (
                "You label context for a hate-speech-detection privacy audit. "
                "Do not rewrite text. Identify target/action/negation/context "
                "phrases that must remain semantically visible, and identifier "
                "or style phrases that may be maskable. Be brief. "
                + mode_instruction
            ),
        },
        {"role": "user", "content": text},
    ]


def post_chat_completion(
    *,
    endpoint: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float,
    max_tokens: int,
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
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
            body = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") or exc.reason
        raise BenchmarkRequestError(f"http_{exc.code}", detail) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise BenchmarkRequestError("timeout", str(exc)) from exc
    except (OSError, error.URLError) as exc:
        raise BenchmarkRequestError("connection_error", str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkRequestError("invalid_response_json", str(exc)) from exc
    try:
        return str(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise BenchmarkRequestError("invalid_response_shape", str(exc)) from exc


def select_sample_rows(
    rows: list[dict[str, str]],
    *,
    sample_size: int,
    source_col: str | None,
    label_col: str | None,
) -> list[tuple[int, dict[str, str]]]:
    indexed = list(enumerate(rows, start=1))
    if sample_size <= 0 or sample_size >= len(indexed):
        return indexed
    buckets: dict[tuple[str, str], list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for item in indexed:
        _, row = item
        key = (
            str(row.get(source_col, "") or "<blank>") if source_col else "<all>",
            str(row.get(label_col, "") or "<blank>") if label_col else "<all>",
        )
        buckets[key].append(item)
    selected: list[tuple[int, dict[str, str]]] = []
    keys = sorted(buckets)
    cursor = 0
    while len(selected) < sample_size and any(buckets.values()):
        key = keys[cursor % len(keys)]
        if buckets[key]:
            selected.append(buckets[key].pop(0))
        cursor += 1
    return selected


def agreement_score(predicted: list[str], deterministic: list[str]) -> float:
    predicted_set = set(predicted)
    deterministic_set = set(deterministic)
    if not predicted_set and not deterministic_set:
        return 1.0
    union = predicted_set | deterministic_set
    return len(predicted_set & deterministic_set) / len(union) if union else 1.0


def run_lm_context_benchmark(
    input_path: Path,
    *,
    text_col: str,
    id_col: str | None = None,
    source_col: str | None = "source",
    label_col: str | None = "label",
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = "local-model",
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    output_path: Path | None = None,
    modes: list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    missing = [
        column
        for column in (text_col, id_col, source_col, label_col)
        if column and column not in fieldnames
    ]
    if missing:
        raise LmContextBenchmarkError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )
    selected_modes = modes or list(DEFAULT_MODES)
    unknown_modes = [mode for mode in selected_modes if mode not in PARSERS]
    if unknown_modes:
        raise LmContextBenchmarkError(f"unknown mode(s): {', '.join(unknown_modes)}")
    if sample_size < 0:
        raise LmContextBenchmarkError("--sample-size must be non-negative")

    sample = select_sample_rows(
        rows,
        sample_size=sample_size,
        source_col=source_col,
        label_col=label_col,
    )
    row_reports: list[dict[str, Any]] = []
    parse_mode_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    error_counts: Counter[str] = Counter()
    latencies: list[float] = []
    agreements: list[float] = []
    protected_cue_phrase_hits = 0
    maskable_cue_violations = 0
    first_error: str | None = None
    blocked = False
    start = time.perf_counter()

    for sample_index, (row_index, row) in enumerate(sample, start=1):
        text = str(row.get(text_col, "") or "")
        row_id = str(row.get(id_col, "") or row_index) if id_col else str(row_index)
        deterministic = analyze_context(
            text,
            {
                "target": row.get("target", ""),
                "target_categories": row.get("target_categories", ""),
            },
        )
        row_status = "failed"
        parsed: dict[str, Any] | None = None
        best_mode: str | None = None
        row_latency: float | None = None
        row_error: str | None = None
        for mode_index, mode in enumerate(selected_modes):
            mode_start = time.perf_counter()
            try:
                content = post_chat_completion(
                    endpoint=endpoint,
                    model=model,
                    messages=prompt_messages(text, mode),
                    timeout=timeout,
                    max_tokens=max_tokens,
                )
                latency = time.perf_counter() - mode_start
                candidate = PARSERS[mode](content)
                parsed = candidate
                best_mode = mode
                row_latency = latency
                row_status = "parsed"
                break
            except LmContextBenchmarkError as exc:
                error_counts[f"parse_{mode}"] += 1
                row_error = str(exc)
                continue
            except BenchmarkRequestError as exc:
                error_counts[exc.kind] += 1
                row_error = exc.detail
                first_error = first_error or f"{exc.kind}: {exc.detail}"
                if (
                    sample_index == 1
                    and mode_index == 0
                    and exc.kind in {"connection_error", "timeout"}
                ):
                    blocked = True
                break
        if blocked:
            status_counts["blocked_endpoint"] += 1
            row_reports.append(
                {
                    "row_index": row_index,
                    "row_id": row_id,
                    "source": row.get(source_col, "") if source_col else None,
                    "label": row.get(label_col, "") if label_col else None,
                    "status": "blocked_endpoint",
                    "best_mode": None,
                    "deterministic_tag_count": len(deterministic["context_tags"]),
                    "agreement": None,
                    "latency_seconds": None,
                    "detail": row_error,
                }
            )
            break

        status_counts[row_status] += 1
        agreement = None
        protected_count = 0
        maskable_count = 0
        if parsed is not None:
            parse_mode_counts[best_mode or "unknown"] += 1
            if row_latency is not None:
                latencies.append(row_latency)
            agreement = agreement_score(
                parsed["context_tags"],
                deterministic["context_tags"],
            )
            agreements.append(agreement)
            protected_count = int(parsed.get("protected_phrase_count", 0))
            maskable_count = int(parsed.get("maskable_phrase_count", 0))
            protected_cue_phrase_hits += sum(
                1
                for phrase in parsed.get("protected_phrases", [])
                if phrase_has_protected_cue(phrase)
            )
            maskable_cue_violations += sum(
                1
                for phrase in parsed.get("maskable_phrases", [])
                if phrase_has_protected_cue(phrase)
            )

        row_reports.append(
            {
                "row_index": row_index,
                "row_id": row_id,
                "source": row.get(source_col, "") if source_col else None,
                "label": row.get(label_col, "") if label_col else None,
                "status": row_status,
                "best_mode": best_mode,
                "deterministic_tags": deterministic["context_tags"],
                "predicted_tags": parsed["context_tags"] if parsed else [],
                "agreement": rounded(agreement) if agreement is not None else None,
                "latency_seconds": rounded(row_latency) if row_latency is not None else None,
                "protected_phrase_count": protected_count,
                "maskable_phrase_count": maskable_count,
                "detail": row_error if row_status != "parsed" else None,
            }
        )

    runtime = time.perf_counter() - start
    parsed_count = status_counts.get("parsed", 0)
    attempted_count = sum(status_counts.values())
    result = {
        "artifact_type": "lm_context_benchmark",
        "status": "blocked" if blocked else ("ok" if parsed_count else "skipped"),
        "skip_reason": "endpoint_unreachable" if blocked else (
            "no_parseable_outputs" if not parsed_count else None
        ),
        "first_error": first_error,
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "endpoint": endpoint,
        "model": model,
        "columns": {
            "text_col": text_col,
            "id_col": id_col,
            "source_col": source_col,
            "label_col": label_col,
        },
        "sample": {
            "requested_sample_size": sample_size,
            "selected_sample_size": len(sample),
            "attempted_rows": attempted_count,
            "strategy": "source_label_round_robin",
        },
        "modes": selected_modes,
        "metrics": {
            "parse_valid_rate": rounded(parsed_count / attempted_count)
            if attempted_count
            else 0.0,
            "status_counts": dict(sorted(status_counts.items())),
            "parse_mode_counts": dict(sorted(parse_mode_counts.items())),
            "error_counts": dict(sorted(error_counts.items())),
            "latency_p50_seconds": percentile(latencies, 0.5),
            "latency_p95_seconds": percentile(latencies, 0.95),
            "rows_per_second": rounded(parsed_count / runtime) if runtime else 0.0,
            "agreement_with_deterministic_mean": (
                rounded(statistics.mean(agreements)) if agreements else None
            ),
            "protected_cue_phrase_hits": protected_cue_phrase_hits,
            "maskable_cue_violations": maskable_cue_violations,
        },
        "runtime_seconds": rounded(runtime),
        "rows": row_reports,
        "notes": [
            "Raw text and model phrase strings are omitted from this report.",
            "LLM labels are advisory only and must not directly rewrite final text.",
        ],
    }
    if output_path:
        write_json(output_path, result)
    return result
