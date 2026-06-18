#!/usr/bin/env python3
"""Benchmark LM Studio models for privacy-safe comment restatement.

The benchmark is intentionally narrow: it compares small OpenAI-compatible chat
models on restating HSD comments while preserving label-relevant meaning and
removing high-confidence direct identifiers.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
from pathlib import Path
import random
import re
import statistics
import sys
import time
from typing import Any
from urllib import error, request

from contextsafe_hsd.metrics import (
    high_confidence_residual_spans,
    placeholder_counts,
    row_metric_fast,
)


DEFAULT_ENDPOINT = "http://100.120.207.64:1234"
DEFAULT_INPUT = Path("data/train/train_split.csv")
DEFAULT_OUTPUT_DIR = Path("data/outputs/lmstudio_restatement_benchmark_20260618")
EXCLUDED_MODEL_MARKERS = (
    "embedding",
    "safeguard",
    "shield",
    "uncensored",
)
MANUAL_SMALL_MODEL_MARKERS = (
    "mini",
    "nano",
    "e2b",
    "e4b",
)
JSON_OBJECT_PATTERN = re.compile(r"\{", re.S)
WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")


SYSTEM_PROMPT = """Return compact JSON only. Do not explain. /no_think

You restate comments for a privacy-preserving hate-speech review mobile app.
The output will be shown to people who swipe hate / non-hate, so it must keep
the label-relevant meaning while removing private identifiers.

Rules:
1. Restate the comment; do not summarize it into a neutral description.
2. Preserve stance, negation, quotation/reporting status, target direction,
   intensity, profanity/offense level, and protected-group references needed for
   hate-speech classification.
3. If hs=1, the restatement must still read as hateful/offensive toward the
   same kind of target. If hs=0, it must not become hate speech.
4. Do not leak direct identifiers: replace usernames, handles, URLs, emails,
   phone numbers, addresses, account IDs, and personal names with typed generic
   placeholders such as [USER], [URL], [EMAIL], [PHONE], [PERSON], [ID].
   If the input already contains placeholder tokens, do not turn them into
   concrete names, handles, locations, links, emails, phone numbers, or IDs.
5. Preserve public/protected category terms that are needed for classification,
   such as religion, nationality, ethnicity, gender, sexuality, or political
   category references.
6. Keep roughly comparable length unless the original contains long links or
   identifier lists.

Return exactly this JSON object:
{"restatement":"...","meaning_preserved":true,"hs_label_preserved":true,"target_direction_preserved":true,"pii_removed":true}"""


@dataclass(frozen=True)
class SourceRow:
    row_index: int
    row_id: str
    label: str
    text: str
    high_confidence_direct: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark LM Studio small models for comment restatement."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--text-col", default="text")
    parser.add_argument("--id-col", default="ID")
    parser.add_argument("--label-col", default="hs")
    parser.add_argument(
        "--models",
        nargs="*",
        help=(
            "Model ids to benchmark. If omitted, small non-embedding/non-safety "
            "models are selected from /v1/models."
        ),
    )
    parser.add_argument("--sample-size", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260618)
    parser.add_argument("--temperature", type=float, default=0.15)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument(
        "--include-risky-models",
        action="store_true",
        help="Include safeguard, shield, uncensored, and embedding-marked models.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run requests even when a per-model output CSV already exists.",
    )
    return parser.parse_args()


def normalize_base_endpoint(endpoint: str) -> str:
    stripped = endpoint.rstrip("/")
    if stripped.endswith("/v1/chat/completions"):
        return stripped[: -len("/v1/chat/completions")]
    if stripped.endswith("/chat/completions"):
        return stripped[: -len("/chat/completions")]
    if stripped.endswith("/v1"):
        return stripped[: -len("/v1")]
    return stripped


def chat_endpoint(endpoint: str) -> str:
    return normalize_base_endpoint(endpoint) + "/v1/chat/completions"


def models_endpoint(endpoint: str) -> str:
    return normalize_base_endpoint(endpoint) + "/v1/models"


def post_json(url: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except (OSError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(str(exc)) from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("response was not a JSON object")
    return parsed


def fetch_model_ids(endpoint: str, timeout: float) -> list[str]:
    payload = post_json(models_endpoint(endpoint), None, timeout)
    data = payload.get("data")
    if not isinstance(data, list):
        raise RuntimeError("/v1/models response missing data list")
    model_ids = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            model_ids.append(item["id"])
    return model_ids


def model_size_hint(model_id: str) -> float | None:
    matches = re.findall(r"(?<!\d)(\d+(?:\.\d+)?)\s*b(?![a-z])", model_id.lower())
    if not matches:
        return None
    return max(float(value) for value in matches)


def default_small_models(model_ids: list[str], *, include_risky: bool) -> list[str]:
    selected = []
    for model_id in model_ids:
        lowered = model_id.lower()
        if not include_risky and any(marker in lowered for marker in EXCLUDED_MODEL_MARKERS):
            continue
        size = model_size_hint(model_id)
        manual = any(marker in lowered for marker in MANUAL_SMALL_MODEL_MARKERS)
        if size is not None and size <= 4.5:
            selected.append(model_id)
        elif size is None and manual:
            selected.append(model_id)
    return selected


def split_model_args(values: list[str] | None) -> list[str]:
    if not values:
        return []
    models: list[str] = []
    for value in values:
        models.extend(part.strip() for part in value.split(",") if part.strip())
    return models


def read_rows(args: argparse.Namespace) -> list[SourceRow]:
    rows: list[SourceRow] = []
    with args.input.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [
            column
            for column in (args.text_col, args.id_col, args.label_col)
            if column not in (reader.fieldnames or [])
        ]
        if missing:
            raise SystemExit(f"{args.input}: missing columns: {', '.join(missing)}")
        for row_index, row in enumerate(reader, start=1):
            text = str(row.get(args.text_col, "") or "")
            spans = high_confidence_residual_spans(text)
            rows.append(
                SourceRow(
                    row_index=row_index,
                    row_id=str(row.get(args.id_col, "") or row_index),
                    label=str(row.get(args.label_col, "") or ""),
                    text=text,
                    high_confidence_direct=tuple(span.text for span in spans),
                )
            )
    return rows


def allocate_counts(bucket_sizes: dict[tuple[bool, str], int], sample_size: int) -> dict[tuple[bool, str], int]:
    keys = sorted(bucket_sizes)
    if not keys or sample_size <= 0:
        return {}
    base = max(1, sample_size // len(keys))
    allocations = {key: min(bucket_sizes[key], base) for key in keys}
    remaining = sample_size - sum(allocations.values())
    while remaining > 0:
        progressed = False
        for key in keys:
            if allocations[key] >= bucket_sizes[key]:
                continue
            allocations[key] += 1
            remaining -= 1
            progressed = True
            if remaining == 0:
                break
        if not progressed:
            break
    return allocations


def sample_rows(rows: list[SourceRow], *, sample_size: int, seed: int) -> list[SourceRow]:
    rng = random.Random(seed)
    buckets: dict[tuple[bool, bool, str], list[SourceRow]] = defaultdict(list)
    for row in rows:
        placeholders, _placeholder_chars = placeholder_counts(row.text)
        buckets[(bool(row.high_confidence_direct), bool(placeholders), row.label)].append(row)
    for bucket_rows in buckets.values():
        rng.shuffle(bucket_rows)
    allocations = allocate_counts(
        {key: len(value) for key, value in buckets.items()},
        sample_size,
    )
    selected: list[SourceRow] = []
    for key, count in allocations.items():
        selected.extend(buckets[key][:count])
    if len(selected) < sample_size:
        selected_ids = {row.row_index for row in selected}
        remainder = [row for row in rows if row.row_index not in selected_ids]
        rng.shuffle(remainder)
        selected.extend(remainder[: sample_size - len(selected)])
    return sorted(selected[:sample_size], key=lambda row: row.row_index)


def make_payload(args: argparse.Namespace, model_id: str, row: SourceRow) -> dict[str, Any]:
    user_payload = {
        "id": row.row_id,
        "hs": row.label,
        "text": row.text,
    }
    return {
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "/no_think\n" + json.dumps(user_payload, ensure_ascii=False),
            },
        ],
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
    }


def extract_message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("response missing choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("response missing message")
    content = message.get("content")
    if isinstance(content, str):
        return content
    return ""


def parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for match in JSON_OBJECT_PATTERN.finditer(stripped):
            try:
                parsed, _offset = decoder.raw_decode(stripped[match.start() :])
                break
            except json.JSONDecodeError:
                continue
        else:
            raise RuntimeError("content did not contain a JSON object")
    if not isinstance(parsed, dict):
        raise RuntimeError("parsed JSON was not an object")
    return parsed


def request_restatement(
    args: argparse.Namespace,
    *,
    model_id: str,
    row: SourceRow,
) -> tuple[dict[str, Any] | None, str, str, float]:
    payload = make_payload(args, model_id, row)
    last_error: Exception | None = None
    started = time.perf_counter()
    for attempt in range(1, args.max_retries + 1):
        try:
            response = post_json(chat_endpoint(args.endpoint), payload, args.timeout_seconds)
            content = extract_message_content(response)
            parsed = parse_json_object(content)
            return parsed, content, "", time.perf_counter() - started
        except Exception as exc:  # noqa: BLE001 - record model/API failures.
            last_error = exc
            if attempt < args.max_retries:
                time.sleep(min(10.0, 1.5**attempt))
    return None, "", f"{type(last_error).__name__}: {last_error}", time.perf_counter() - started


def exact_identifier_leaks(original_identifiers: tuple[str, ...], restatement: str) -> list[str]:
    lowered = restatement.lower()
    leaks = []
    for identifier in original_identifiers:
        if identifier and identifier.lower() in lowered:
            leaks.append(identifier)
    return leaks


def token_set(text: str) -> set[str]:
    return {token.lower() for token in WORD_PATTERN.findall(text)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def bool_value(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def counter_positive_delta(before: Counter[str], after: Counter[str]) -> Counter[str]:
    delta: Counter[str] = Counter()
    for key, value in before.items():
        change = value - after.get(key, 0)
        if change > 0:
            delta[key] = change
    return delta


def score_row(row: SourceRow, parsed: dict[str, Any] | None, error_text: str, elapsed: float) -> dict[str, Any]:
    restatement = ""
    parse_ok = parsed is not None
    if parsed is not None:
        raw_restatement = parsed.get("restatement")
        if isinstance(raw_restatement, str):
            restatement = raw_restatement.strip()
    nonempty = bool(restatement)
    length_ratio = len(restatement) / max(len(row.text), 1) if nonempty else 0.0
    similarity = SequenceMatcher(None, row.text, restatement).ratio() if nonempty else 0.0
    token_overlap = jaccard(token_set(row.text), token_set(restatement)) if nonempty else 0.0
    exact_copy = row.text.strip() == restatement.strip() if nonempty else False
    too_short = len(row.text) >= 40 and length_ratio < 0.25
    too_long = len(row.text) >= 40 and length_ratio > 2.0
    model_checks = {
        "meaning_preserved": bool_value(parsed.get("meaning_preserved")) if parsed else False,
        "hs_label_preserved": bool_value(parsed.get("hs_label_preserved")) if parsed else False,
        "target_direction_preserved": bool_value(parsed.get("target_direction_preserved")) if parsed else False,
        "pii_removed": bool_value(parsed.get("pii_removed")) if parsed else False,
    }
    high_conf_after = high_confidence_residual_spans(restatement) if nonempty else []
    exact_leaks = exact_identifier_leaks(row.high_confidence_direct, restatement)
    placeholders_before, _placeholder_chars_before = placeholder_counts(row.text)
    placeholders_after, _placeholder_chars_after = (
        placeholder_counts(restatement) if nonempty else (Counter(), 0)
    )
    placeholder_loss = counter_positive_delta(placeholders_before, placeholders_after)
    placeholder_gain = counter_positive_delta(placeholders_after, placeholders_before)
    placeholder_count_before = sum(placeholders_before.values())
    placeholder_count_after = sum(placeholders_after.values())
    placeholder_retention = (
        min(1.0, placeholder_count_after / placeholder_count_before)
        if placeholder_count_before
        else 1.0
    )
    metrics = row_metric_fast(row.text, restatement) if nonempty else {}
    target_category_retention = float(metrics.get("target_category_retention", 0.0))
    target_cue_retention = float(metrics.get("target_cue_retention", 0.0))
    utility_cue_retention = float(metrics.get("utility_cue_retention", 0.0))
    residual_high_conf = len(high_conf_after)
    valid = (
        parse_ok
        and nonempty
        and not exact_copy
        and not too_short
        and not too_long
        and all(model_checks.values())
        and residual_high_conf == 0
        and not exact_leaks
        and target_category_retention >= 0.95
    )
    return {
        "row_index": row.row_index,
        "id": row.row_id,
        "hs": row.label,
        "original_text": row.text,
        "restatement": restatement,
        "parse_ok": parse_ok,
        "error": error_text,
        "elapsed_seconds": round(elapsed, 4),
        "original_high_confidence_direct_count": len(row.high_confidence_direct),
        "original_high_confidence_direct": list(row.high_confidence_direct),
        "residual_high_confidence_direct_count": residual_high_conf,
        "residual_high_confidence_direct": [
            {"entity_type": span.entity_type, "text": span.text, "source": span.source}
            for span in high_conf_after
        ],
        "exact_original_identifier_leaks": exact_leaks,
        "placeholder_count_before": placeholder_count_before,
        "placeholder_count_after": placeholder_count_after,
        "placeholder_retention": round(placeholder_retention, 4),
        "placeholder_counts_before": dict(sorted(placeholders_before.items())),
        "placeholder_counts_after": dict(sorted(placeholders_after.items())),
        "placeholder_loss_counts": dict(sorted(placeholder_loss.items())),
        "placeholder_gain_counts": dict(sorted(placeholder_gain.items())),
        "meaning_preserved": model_checks["meaning_preserved"],
        "hs_label_preserved": model_checks["hs_label_preserved"],
        "target_direction_preserved": model_checks["target_direction_preserved"],
        "pii_removed": model_checks["pii_removed"],
        "exact_copy": exact_copy,
        "too_short": too_short,
        "too_long": too_long,
        "length_ratio": round(length_ratio, 4),
        "character_similarity": round(similarity, 4),
        "surface_change": round(1.0 - similarity, 4),
        "token_jaccard": round(token_overlap, 4),
        "target_category_retention": target_category_retention,
        "target_cue_retention": target_cue_retention,
        "utility_cue_retention": utility_cue_retention,
        "valid_for_mobile_review": valid,
    }


def load_existing_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def run_model(args: argparse.Namespace, model_id: str, rows: list[SourceRow]) -> list[dict[str, Any]]:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "__", model_id)
    output_path = args.output_dir / f"{safe_name}.rows.csv"
    if output_path.exists() and not args.force:
        return load_existing_rows(output_path)

    model_rows: list[dict[str, Any]] = []
    for offset, row in enumerate(rows, start=1):
        parsed, _raw_content, error_text, elapsed = request_restatement(
            args,
            model_id=model_id,
            row=row,
        )
        scored = score_row(row, parsed, error_text, elapsed)
        scored["model"] = model_id
        model_rows.append(scored)
        print(
            json.dumps(
                {
                    "model": model_id,
                    "row": offset,
                    "rows": len(rows),
                    "id": row.row_id,
                    "valid": scored["valid_for_mobile_review"],
                    "parse_ok": scored["parse_ok"],
                    "elapsed_seconds": scored["elapsed_seconds"],
                },
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
    write_rows_csv(output_path, model_rows)
    return model_rows


def numeric_mean(rows: list[dict[str, Any]], key: str, default: float = 0.0) -> float:
    values = []
    for row in rows:
        try:
            values.append(float(row.get(key, default)))
        except (TypeError, ValueError):
            values.append(default)
    return round(statistics.mean(values), 4) if values else 0.0


def truthy_count(rows: list[dict[str, Any]], key: str) -> int:
    return sum(str(row.get(key, "")).lower() == "true" for row in rows)


def int_sum(rows: list[dict[str, Any]], key: str) -> int:
    total = 0
    for row in rows:
        try:
            total += int(row.get(key, 0))
        except (TypeError, ValueError):
            continue
    return total


def parse_json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def mapping_value_sum(rows: list[dict[str, Any]], key: str) -> int:
    total = 0
    for row in rows:
        for value in parse_json_mapping(row.get(key)).values():
            try:
                total += int(value)
            except (TypeError, ValueError):
                continue
    return total


def rows_with_mapping_values(rows: list[dict[str, Any]], key: str) -> int:
    count = 0
    for row in rows:
        has_value = False
        for value in parse_json_mapping(row.get(key)).values():
            try:
                if int(value) > 0:
                    has_value = True
                    break
            except (TypeError, ValueError):
                continue
        count += int(has_value)
    return count


def summarize_model(model_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    row_count = len(rows)
    parse_count = truthy_count(rows, "parse_ok")
    valid_count = truthy_count(rows, "valid_for_mobile_review")
    residual_high_conf = int_sum(rows, "residual_high_confidence_direct_count")
    exact_leak_rows = sum(
        1
        for row in rows
        if row.get("exact_original_identifier_leaks")
        not in ("", "[]", [], None)
    )
    error_counts = Counter(str(row.get("error", ""))[:120] for row in rows if row.get("error"))
    checks = {
        "meaning_preserved_rate": truthy_count(rows, "meaning_preserved") / row_count if row_count else 0.0,
        "hs_label_preserved_rate": truthy_count(rows, "hs_label_preserved") / row_count if row_count else 0.0,
        "target_direction_preserved_rate": truthy_count(rows, "target_direction_preserved") / row_count if row_count else 0.0,
        "pii_removed_rate": truthy_count(rows, "pii_removed") / row_count if row_count else 0.0,
    }
    mobile_ready_rate = valid_count / row_count if row_count else 0.0
    score = (
        100.0 * mobile_ready_rate
        + 12.0 * (parse_count / row_count if row_count else 0.0)
        + 8.0 * checks["hs_label_preserved_rate"]
        + 8.0 * checks["meaning_preserved_rate"]
        + 6.0 * numeric_mean(rows, "target_category_retention")
        + 4.0 * numeric_mean(rows, "surface_change")
        - 25.0 * (residual_high_conf / max(row_count, 1))
        - 20.0 * (exact_leak_rows / max(row_count, 1))
    )
    return {
        "model": model_id,
        "row_count": row_count,
        "parse_count": parse_count,
        "parse_rate": round(parse_count / row_count, 4) if row_count else 0.0,
        "mobile_ready_count": valid_count,
        "mobile_ready_rate": round(mobile_ready_rate, 4),
        "mean_elapsed_seconds": numeric_mean(rows, "elapsed_seconds"),
        "mean_length_ratio": numeric_mean(rows, "length_ratio"),
        "mean_surface_change": numeric_mean(rows, "surface_change"),
        "mean_token_jaccard": numeric_mean(rows, "token_jaccard"),
        "mean_target_category_retention": numeric_mean(rows, "target_category_retention"),
        "mean_target_cue_retention": numeric_mean(rows, "target_cue_retention"),
        "mean_utility_cue_retention": numeric_mean(rows, "utility_cue_retention"),
        "residual_high_confidence_direct_count": residual_high_conf,
        "exact_identifier_leak_rows": exact_leak_rows,
        "placeholder_count_before": int_sum(rows, "placeholder_count_before"),
        "placeholder_count_after": int_sum(rows, "placeholder_count_after"),
        "placeholder_retention_mean": numeric_mean(
            rows,
            "placeholder_retention",
            default=1.0,
        ),
        "placeholder_loss_total": mapping_value_sum(rows, "placeholder_loss_counts"),
        "placeholder_loss_rows": rows_with_mapping_values(rows, "placeholder_loss_counts"),
        "exact_copy_count": truthy_count(rows, "exact_copy"),
        "too_short_count": truthy_count(rows, "too_short"),
        "too_long_count": truthy_count(rows, "too_long"),
        "benchmark_score": round(score, 4),
        **{key: round(value, 4) for key, value in checks.items()},
        "error_counts": dict(error_counts.most_common(5)),
    }


def write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "model",
        "row_index",
        "id",
        "hs",
        "parse_ok",
        "valid_for_mobile_review",
        "meaning_preserved",
        "hs_label_preserved",
        "target_direction_preserved",
        "pii_removed",
        "elapsed_seconds",
        "length_ratio",
        "surface_change",
        "token_jaccard",
        "target_category_retention",
        "target_cue_retention",
        "utility_cue_retention",
        "original_high_confidence_direct_count",
        "residual_high_confidence_direct_count",
        "exact_copy",
        "too_short",
        "too_long",
        "placeholder_count_before",
        "placeholder_count_after",
        "placeholder_retention",
        "placeholder_counts_before",
        "placeholder_counts_after",
        "placeholder_loss_counts",
        "placeholder_gain_counts",
        "error",
        "original_high_confidence_direct",
        "residual_high_confidence_direct",
        "exact_original_identifier_leaks",
        "original_text",
        "restatement",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            serialized = {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (list, dict))
                else value
                for key, value in row.items()
            }
            writer.writerow(serialized)


def write_summary_json(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_summary_markdown(path: Path, summary: dict[str, Any]) -> None:
    rankings = summary["rankings"]
    lines = [
        "# LM Studio Restatement Benchmark",
        "",
        f"Input: `{summary['input']}`",
        f"Endpoint: `{summary['endpoint']}`",
        f"Sample rows: `{summary['sample_row_count']}`",
        f"Finished UTC: `{summary['finished_utc']}`",
        "",
        "## Ranking",
        "",
        "| Rank | Model | Score | Mobile-ready | Parse | PII leaks | Placeholder loss | Mean sec | Surface change | Target category |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, item in enumerate(rankings, start=1):
        leaks = item["residual_high_confidence_direct_count"] + item["exact_identifier_leak_rows"]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(rank),
                    f"`{item['model']}`",
                    f"{item['benchmark_score']:.2f}",
                    f"{item['mobile_ready_rate']:.2%}",
                    f"{item['parse_rate']:.2%}",
                    str(leaks),
                    str(item.get("placeholder_loss_total", 0)),
                    f"{item['mean_elapsed_seconds']:.2f}",
                    f"{item['mean_surface_change']:.2f}",
                    f"{item['mean_target_category_retention']:.2f}",
                ]
            )
            + " |"
        )
    if rankings:
        best = rankings[0]
        lines.extend(
            [
                "",
                "## Recommendation",
                "",
                (
                    f"Use `{best['model']}` for the next larger restatement test. "
                    f"It had the top benchmark score, `{best['mobile_ready_rate']:.2%}` "
                    "mobile-ready outputs, and "
                    f"{best['residual_high_confidence_direct_count']} residual "
                    "high-confidence direct identifiers on this sample. "
                    f"Placeholder loss total was `{best.get('placeholder_loss_total', 0)}`."
                ),
                "",
                "## Scoring Notes",
                "",
                "- Mobile-ready requires parseable JSON, nonempty changed text, all model preservation booleans true, no high-confidence direct identifier after restatement, no exact original identifier leak, and target-category retention >= 0.95.",
                "- The PII score uses high-confidence direct identifier detection only, not fuzzy context identifiers.",
                "- This is a model-selection benchmark, not an official leaderboard metric.",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.sample_size < 1:
        raise SystemExit("--sample-size must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    explicit_models = split_model_args(args.models)
    available_models = fetch_model_ids(args.endpoint, args.timeout_seconds)
    model_ids = explicit_models or default_small_models(
        available_models,
        include_risky=args.include_risky_models,
    )
    if not model_ids:
        raise SystemExit("no models selected")

    rows = read_rows(args)
    sampled_rows = sample_rows(rows, sample_size=args.sample_size, seed=args.seed)
    sample_manifest = [
        {
            "row_index": row.row_index,
            "id": row.row_id,
            "hs": row.label,
            "high_confidence_direct_count": len(row.high_confidence_direct),
        }
        for row in sampled_rows
    ]
    write_summary_json(args.output_dir / "sample_manifest.json", {"rows": sample_manifest})

    all_model_rows: dict[str, list[dict[str, Any]]] = {}
    for model_id in model_ids:
        all_model_rows[model_id] = run_model(args, model_id, sampled_rows)

    rankings = sorted(
        (summarize_model(model_id, model_rows) for model_id, model_rows in all_model_rows.items()),
        key=lambda item: (
            item["benchmark_score"],
            item["mobile_ready_rate"],
            -item["mean_elapsed_seconds"],
        ),
        reverse=True,
    )
    summary = {
        "input": str(args.input),
        "output_dir": str(args.output_dir),
        "endpoint": normalize_base_endpoint(args.endpoint),
        "available_models": available_models,
        "models": model_ids,
        "sample_row_count": len(sampled_rows),
        "seed": args.seed,
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rankings": rankings,
    }
    write_summary_json(args.output_dir / "summary.json", summary)
    write_summary_markdown(args.output_dir / "summary.md", summary)
    print(json.dumps({"output_dir": str(args.output_dir), "rankings": rankings}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
