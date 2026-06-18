#!/usr/bin/env python3
"""Benchmark batched restatement of already-redacted comments via LM Studio.

This script matches the intended mobile-app path:
- input text is already redacted;
- the model receives batches of rows;
- the model returns only ordered restatements;
- all quality/privacy decisions are made by local validators.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import math
from pathlib import Path
import random
import re
import statistics
import sys
import time
from typing import Any
from urllib import error, request

from contextsafe_hsd.metrics import high_confidence_residual_spans, row_metric_fast


DEFAULT_ENDPOINT = "http://100.120.207.64:1234"
DEFAULT_INPUT = Path(
    "data/locked_baseline_train_split_no_simplify_hf_recovered_20260618_timed/"
    "train_split.no_simplify_hf.recovered.protected.csv"
)
DEFAULT_OUTPUT_DIR = Path("data/outputs/lmstudio_batched_restatement_20260618")
DEFAULT_EMBEDDING_MODEL = "text-embedding-bge-m3"
TOOL_NAME = "record_restatement_batch"
BRACKET_TOKEN_PATTERN = re.compile(r"\[[A-Z][A-Z0-9_:-]*\]")
WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")
JSON_OBJECT_PATTERN = re.compile(r"\{", re.S)


RESTATEMENT_INSTRUCTIONS = """

You restate already-redacted comments for a mobile hate/non-hate swipe card.

The input is already privacy-redacted. Your only job is to make each comment a
clearer neutral-style restatement while preserving the same classification
meaning.

Rules:
1. Return exactly one restatement for each input item, in the same order.
2. Do not summarize as "the comment says" or describe the text from outside.
3. Do not add new bracket placeholders.
4. Do not remove existing bracket placeholders.
5. Do not change placeholder types. [PERSON] must stay [PERSON], [URL] must stay
   [URL], [LOCATION] must stay [LOCATION], etc.
6. Preserve protected group words and public target words needed for hate-speech
   classification, such as Muslims, Jews, women, men, Americans, Christians,
   Nazis, gay, trans, immigrants, and similar group terms.
7. Preserve stance, negation, quote/reporting status, target direction, and
   whether the comment is hate/offensive or non-hate.
8. Keep comparable intensity. Do not sanitize hateful meaning into non-hate, and
   do not make non-hate comments hateful.
9. Every restatement must make real wording or syntax changes. Do not copy the
   input verbatim. Punctuation/capitalization-only edits are not enough.
10. For short comments, use a small meaning-preserving wording change instead
    of copying.
11. Keep roughly comparable length.

"""

SYSTEM_PROMPT = (
    f"Call the required {TOOL_NAME} tool. Do not explain. /no_think"
    + RESTATEMENT_INSTRUCTIONS
    + "\nReturn only the ordered restatements via the required tool."
)

PLAIN_JSON_SYSTEM_PROMPT = (
    "Return compact JSON only. Do not explain. /no_think"
    + RESTATEMENT_INSTRUCTIONS
    + '\nReturn exactly this JSON shape: {"restatements":["..."]}'
)


@dataclass(frozen=True)
class SourceRow:
    row_index: int
    row_id: str
    label: str
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark batched redacted-comment restatement via LM Studio."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", required=True)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--text-col", default="text")
    parser.add_argument("--id-col", default="ID")
    parser.add_argument("--label-col", default="hs")
    parser.add_argument("--sample-size", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260618)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=5000)
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--min-semantic-similarity", type=float, default=0.82)
    parser.add_argument("--min-target-category-retention", type=float, default=0.95)
    parser.add_argument("--min-length-ratio", type=float, default=0.35)
    parser.add_argument("--max-length-ratio", type=float, default=1.8)
    parser.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Skip embedding cosine similarity and rely on deterministic checks.",
    )
    parser.add_argument(
        "--plain-json",
        action="store_true",
        help="Use plain JSON output instead of an LM Studio tool call.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run requests even when row CSV already exists.",
    )
    return parser.parse_args()


def normalize_base_endpoint(endpoint: str) -> str:
    stripped = endpoint.rstrip("/")
    if stripped.endswith("/v1/chat/completions"):
        return stripped[: -len("/v1/chat/completions")]
    if stripped.endswith("/v1/embeddings"):
        return stripped[: -len("/v1/embeddings")]
    if stripped.endswith("/chat/completions"):
        return stripped[: -len("/chat/completions")]
    if stripped.endswith("/embeddings"):
        return stripped[: -len("/embeddings")]
    if stripped.endswith("/v1"):
        return stripped[: -len("/v1")]
    return stripped


def chat_endpoint(endpoint: str) -> str:
    return normalize_base_endpoint(endpoint) + "/v1/chat/completions"


def embeddings_endpoint(endpoint: str) -> str:
    return normalize_base_endpoint(endpoint) + "/v1/embeddings"


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
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


def bracket_token_counts(text: str) -> Counter[str]:
    return Counter(BRACKET_TOKEN_PATTERN.findall(text))


def counter_positive_delta(before: Counter[str], after: Counter[str]) -> Counter[str]:
    delta: Counter[str] = Counter()
    for key, value in before.items():
        change = value - after.get(key, 0)
        if change > 0:
            delta[key] = change
    return delta


def read_rows(args: argparse.Namespace) -> list[SourceRow]:
    with args.input.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [
            column
            for column in (args.text_col, args.id_col, args.label_col)
            if column not in (reader.fieldnames or [])
        ]
        if missing:
            raise SystemExit(f"{args.input}: missing columns: {', '.join(missing)}")
        return [
            SourceRow(
                row_index=index,
                row_id=str(row.get(args.id_col, "") or index),
                label=str(row.get(args.label_col, "") or ""),
                text=str(row.get(args.text_col, "") or ""),
            )
            for index, row in enumerate(reader, start=1)
        ]


def sample_rows(rows: list[SourceRow], *, sample_size: int, seed: int) -> list[SourceRow]:
    rng = random.Random(seed)
    buckets: dict[tuple[bool, str], list[SourceRow]] = defaultdict(list)
    for row in rows:
        buckets[(bool(bracket_token_counts(row.text)), row.label)].append(row)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    keys = sorted(buckets)
    selected: list[SourceRow] = []
    base = max(1, sample_size // max(1, len(keys)))
    for key in keys:
        selected.extend(buckets[key][:base])
    if len(selected) < sample_size:
        selected_ids = {row.row_index for row in selected}
        rest = [row for row in rows if row.row_index not in selected_ids]
        rng.shuffle(rest)
        selected.extend(rest[: sample_size - len(selected)])
    return sorted(selected[:sample_size], key=lambda row: row.row_index)


def make_batches(rows: list[SourceRow], batch_size: int) -> list[list[SourceRow]]:
    return [rows[index : index + batch_size] for index in range(0, len(rows), batch_size)]


def restatement_tool_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["restatements"],
        "properties": {
            "restatements": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
    }


def make_payload(args: argparse.Namespace, batch: list[SourceRow]) -> dict[str, Any]:
    return_mode = (
        "Return only a JSON object with the ordered restatements array."
        if args.plain_json
        else "Return only the ordered restatements array via the tool."
    )
    payload: dict[str, Any] = {
        "model": args.model,
        "messages": [
            {
                "role": "system",
                "content": PLAIN_JSON_SYSTEM_PROMPT if args.plain_json else SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": "/no_think\n"
                + json.dumps(
                    {
                        "task": (
                            "Restate each already-redacted text. " + return_mode
                        ),
                        "items": [
                            {
                                "id": row.row_id,
                                "hs": row.label,
                                "text": row.text,
                            }
                            for row in batch
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
    }
    if args.plain_json:
        return payload
    payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": TOOL_NAME,
                    "description": (
                        "Record exactly one ordered restatement for each input item."
                    ),
                    "parameters": restatement_tool_schema(),
                    "strict": True,
                },
            }
        ]
    payload["tool_choice"] = "required"
    return payload


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise RuntimeError("content was not a JSON string")
    stripped = value.strip()
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


def extract_tool_payload(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("response missing choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("response missing message")
    for tool_call in message.get("tool_calls") or []:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function")
        if not isinstance(function, dict):
            continue
        if function.get("name") == TOOL_NAME:
            return parse_json_object(function.get("arguments", ""))
    function_call = message.get("function_call")
    if isinstance(function_call, dict) and function_call.get("name") == TOOL_NAME:
        return parse_json_object(function_call.get("arguments", ""))
    raise RuntimeError(f"response did not contain {TOOL_NAME} tool call")


def extract_plain_json_payload(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("response missing choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("response missing message")
    return parse_json_object(message.get("content", ""))


def request_batch(
    args: argparse.Namespace,
    batch: list[SourceRow],
) -> tuple[list[str] | None, str, float]:
    last_error: Exception | None = None
    started = time.perf_counter()
    for attempt in range(1, args.max_retries + 1):
        try:
            response = post_json(
                chat_endpoint(args.endpoint),
                make_payload(args, batch),
                args.timeout_seconds,
            )
            payload = (
                extract_plain_json_payload(response)
                if args.plain_json
                else extract_tool_payload(response)
            )
            restatements = payload.get("restatements")
            if not isinstance(restatements, list):
                raise RuntimeError("tool payload missing restatements array")
            if len(restatements) != len(batch):
                raise RuntimeError(
                    f"restatement count mismatch: expected {len(batch)}, got {len(restatements)}"
                )
            return [str(item or "").strip() for item in restatements], "", time.perf_counter() - started
        except Exception as exc:  # noqa: BLE001 - benchmark records all failures.
            last_error = exc
            if attempt < args.max_retries:
                time.sleep(min(10.0, 1.5**attempt))
    return None, f"{type(last_error).__name__}: {last_error}", time.perf_counter() - started


def request_embeddings(
    *,
    endpoint: str,
    model: str,
    texts: list[str],
    timeout: float,
) -> list[list[float]]:
    response = post_json(
        embeddings_endpoint(endpoint),
        {"model": model, "input": texts},
        timeout,
    )
    data = response.get("data")
    if not isinstance(data, list) or len(data) != len(texts):
        raise RuntimeError("embedding response did not match input count")
    vectors: list[list[float]] = []
    for item in sorted(data, key=lambda value: int(value.get("index", 0))):
        embedding = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(embedding, list):
            raise RuntimeError("embedding item missing vector")
        vectors.append([float(value) for value in embedding])
    return vectors


def cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def token_set(text: str) -> set[str]:
    return {token.lower() for token in WORD_PATTERN.findall(text)}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def score_row(
    *,
    row: SourceRow,
    restatement: str,
    elapsed_seconds: float,
    batch_status: str,
    semantic_similarity: float | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    nonempty = bool(restatement.strip())
    length_ratio = len(restatement) / max(1, len(row.text)) if nonempty else 0.0
    char_similarity = SequenceMatcher(None, row.text, restatement).ratio() if nonempty else 0.0
    token_jaccard = jaccard(token_set(row.text), token_set(restatement)) if nonempty else 0.0
    exact_copy = row.text.strip() == restatement.strip() if nonempty else False
    bracket_before = bracket_token_counts(row.text)
    bracket_after = bracket_token_counts(restatement) if nonempty else Counter()
    bracket_loss = counter_positive_delta(bracket_before, bracket_after)
    bracket_gain = counter_positive_delta(bracket_after, bracket_before)
    residual_spans = high_confidence_residual_spans(restatement) if nonempty else []
    metrics = row_metric_fast(row.text, restatement) if nonempty else {}
    target_category_retention = float(metrics.get("target_category_retention", 0.0))
    target_cue_retention = float(metrics.get("target_cue_retention", 0.0))
    utility_cue_retention = float(metrics.get("utility_cue_retention", 0.0))
    semantic_ok = (
        True
        if semantic_similarity is None
        else semantic_similarity >= args.min_semantic_similarity
    )
    valid = (
        batch_status == "ok"
        and nonempty
        and not exact_copy
        and args.min_length_ratio <= length_ratio <= args.max_length_ratio
        and not bracket_loss
        and not bracket_gain
        and not residual_spans
        and target_category_retention >= args.min_target_category_retention
        and semantic_ok
    )
    return {
        "model": args.model,
        "row_index": row.row_index,
        "id": row.row_id,
        "hs": row.label,
        "batch_status": batch_status,
        "valid_for_mobile_review": valid,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "restatement": restatement,
        "original_text": row.text,
        "exact_copy": exact_copy,
        "length_ratio": round(length_ratio, 4),
        "character_similarity": round(char_similarity, 4),
        "surface_change": round(1.0 - char_similarity, 4),
        "token_jaccard": round(token_jaccard, 4),
        "semantic_similarity": (
            None if semantic_similarity is None else round(semantic_similarity, 4)
        ),
        "semantic_ok": semantic_ok,
        "target_category_retention": round(target_category_retention, 4),
        "target_cue_retention": round(target_cue_retention, 4),
        "utility_cue_retention": round(utility_cue_retention, 4),
        "bracket_token_counts_before": dict(sorted(bracket_before.items())),
        "bracket_token_counts_after": dict(sorted(bracket_after.items())),
        "bracket_token_loss_counts": dict(sorted(bracket_loss.items())),
        "bracket_token_gain_counts": dict(sorted(bracket_gain.items())),
        "residual_high_confidence_direct_count": len(residual_spans),
        "residual_high_confidence_direct": [
            {"entity_type": span.entity_type, "text": span.text, "source": span.source}
            for span in residual_spans
        ],
    }


def score_batch(
    *,
    args: argparse.Namespace,
    batch: list[SourceRow],
    restatements: list[str] | None,
    batch_error: str,
    elapsed_seconds: float,
) -> list[dict[str, Any]]:
    if restatements is None:
        return [
            score_row(
                row=row,
                restatement="",
                elapsed_seconds=elapsed_seconds,
                batch_status=batch_error or "failed",
                semantic_similarity=None,
                args=args,
            )
            for row in batch
        ]

    semantic_similarities: list[float | None]
    if args.no_embeddings:
        semantic_similarities = [None] * len(batch)
    else:
        try:
            originals = [row.text for row in batch]
            vectors = request_embeddings(
                endpoint=args.endpoint,
                model=args.embedding_model,
                texts=[*originals, *restatements],
                timeout=args.timeout_seconds,
            )
            original_vectors = vectors[: len(batch)]
            restatement_vectors = vectors[len(batch) :]
            semantic_similarities = [
                cosine(left, right)
                for left, right in zip(
                    original_vectors,
                    restatement_vectors,
                    strict=True,
                )
            ]
        except Exception as exc:  # noqa: BLE001 - keep generation scoreable.
            print(
                json.dumps(
                    {
                        "phase": "embedding",
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            semantic_similarities = [None] * len(batch)
    return [
        score_row(
            row=row,
            restatement=restatement,
            elapsed_seconds=elapsed_seconds,
            batch_status="ok",
            semantic_similarity=semantic_similarity,
            args=args,
        )
        for row, restatement, semantic_similarity in zip(
            batch,
            restatements,
            semantic_similarities,
            strict=True,
        )
    ]


def safe_model_name(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", model)


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "model",
        "row_index",
        "id",
        "hs",
        "batch_status",
        "valid_for_mobile_review",
        "elapsed_seconds",
        "exact_copy",
        "length_ratio",
        "surface_change",
        "token_jaccard",
        "semantic_similarity",
        "semantic_ok",
        "target_category_retention",
        "target_cue_retention",
        "utility_cue_retention",
        "residual_high_confidence_direct_count",
        "bracket_token_counts_before",
        "bracket_token_counts_after",
        "bracket_token_loss_counts",
        "bracket_token_gain_counts",
        "residual_high_confidence_direct",
        "original_text",
        "restatement",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )


def numeric_mean(rows: list[dict[str, Any]], key: str, default: float = 0.0) -> float:
    values = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            values.append(default)
    return round(statistics.mean(values), 4) if values else 0.0


def truthy_count(rows: list[dict[str, Any]], key: str) -> int:
    return sum(str(row.get(key, "")).lower() == "true" for row in rows)


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
        mapping = row.get(key) if isinstance(row.get(key), dict) else parse_json_mapping(row.get(key))
        for value in mapping.values():
            try:
                total += int(value)
            except (TypeError, ValueError):
                continue
    return total


def rows_with_mapping_values(rows: list[dict[str, Any]], key: str) -> int:
    count = 0
    for row in rows:
        mapping = row.get(key) if isinstance(row.get(key), dict) else parse_json_mapping(row.get(key))
        has_value = False
        for value in mapping.values():
            try:
                if int(value) > 0:
                    has_value = True
                    break
            except (TypeError, ValueError):
                continue
        count += int(has_value)
    return count


def summarize(args: argparse.Namespace, rows: list[dict[str, Any]]) -> dict[str, Any]:
    row_count = len(rows)
    valid_count = truthy_count(rows, "valid_for_mobile_review")
    ok_batches = sum(1 for row in rows if row.get("batch_status") == "ok")
    residual_direct = sum(
        int(row.get("residual_high_confidence_direct_count") or 0)
        for row in rows
    )
    return {
        "model": args.model,
        "row_count": row_count,
        "valid_count": valid_count,
        "valid_rate": round(valid_count / row_count, 4) if row_count else 0.0,
        "generation_parse_rate": round(ok_batches / row_count, 4) if row_count else 0.0,
        "mean_elapsed_seconds": numeric_mean(rows, "elapsed_seconds"),
        "mean_semantic_similarity": numeric_mean(rows, "semantic_similarity"),
        "semantic_fail_count": row_count - truthy_count(rows, "semantic_ok"),
        "exact_copy_count": truthy_count(rows, "exact_copy"),
        "bracket_token_loss_total": mapping_value_sum(rows, "bracket_token_loss_counts"),
        "bracket_token_loss_rows": rows_with_mapping_values(
            rows,
            "bracket_token_loss_counts",
        ),
        "bracket_token_gain_total": mapping_value_sum(rows, "bracket_token_gain_counts"),
        "bracket_token_gain_rows": rows_with_mapping_values(
            rows,
            "bracket_token_gain_counts",
        ),
        "residual_high_confidence_direct_count": residual_direct,
        "target_category_retention_mean": numeric_mean(
            rows,
            "target_category_retention",
        ),
        "target_category_loss_rows": sum(
            1
            for row in rows
            if float(row.get("target_category_retention") or 0.0)
            < args.min_target_category_retention
        ),
        "too_short_count": sum(
            1 for row in rows if float(row.get("length_ratio") or 0.0) < args.min_length_ratio
        ),
        "too_long_count": sum(
            1 for row in rows if float(row.get("length_ratio") or 0.0) > args.max_length_ratio
        ),
    }


def write_summary(path: Path, summary: dict[str, Any], args: argparse.Namespace) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.with_suffix(".json")).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Batched LM Studio Restatement Benchmark",
        "",
        f"Input: `{args.input}`",
        f"Model: `{args.model}`",
        f"Batch size: `{args.batch_size}`",
        f"Embedding model: `{None if args.no_embeddings else args.embedding_model}`",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Valid rows | {summary['valid_count']}/{summary['row_count']} |",
        f"| Generation parse rate | {summary['generation_parse_rate']:.2%} |",
        f"| Mean semantic similarity | {summary['mean_semantic_similarity']:.4f} |",
        f"| Semantic fail count | {summary['semantic_fail_count']} |",
        f"| Exact copies | {summary['exact_copy_count']} |",
        f"| Bracket gains | {summary['bracket_token_gain_total']} |",
        f"| Bracket losses | {summary['bracket_token_loss_total']} |",
        f"| Residual direct identifiers | {summary['residual_high_confidence_direct_count']} |",
        f"| Target category loss rows | {summary['target_category_loss_rows']} |",
        f"| Mean elapsed seconds per row | {summary['mean_elapsed_seconds']:.4f} |",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = args.output_dir / f"{safe_model_name(args.model)}.rows.csv"
    if rows_path.exists() and not args.force:
        print(json.dumps({"rows": str(rows_path), "status": "exists"}, sort_keys=True))
        return 0

    source_rows = sample_rows(
        read_rows(args),
        sample_size=args.sample_size,
        seed=args.seed,
    )
    all_rows: list[dict[str, Any]] = []
    batches = make_batches(source_rows, args.batch_size)
    for batch_number, batch in enumerate(batches, start=1):
        restatements, batch_error, elapsed = request_batch(args, batch)
        scored = score_batch(
            args=args,
            batch=batch,
            restatements=restatements,
            batch_error=batch_error,
            elapsed_seconds=elapsed / max(1, len(batch)),
        )
        all_rows.extend(scored)
        print(
            json.dumps(
                {
                    "batch": batch_number,
                    "batches": len(batches),
                    "rows": len(batch),
                    "status": "ok" if restatements is not None else "failed",
                    "valid_total": truthy_count(all_rows, "valid_for_mobile_review"),
                    "elapsed_seconds": round(elapsed, 4),
                    "error": batch_error,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
        write_rows(rows_path, all_rows)

    summary = summarize(args, all_rows)
    write_summary(args.output_dir / "summary.md", summary, args)
    print(json.dumps({"output_dir": str(args.output_dir), "summary": summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
