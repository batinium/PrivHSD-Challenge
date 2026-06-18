#!/usr/bin/env python3
"""Rewrite a CSV text column with an LM Studio tool-calling model.

This is a research helper for challenge submissions. It preserves the input CSV
schema and rewrites only the selected text column. Progress is cached as JSONL
so long LM Studio runs can be resumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

import pandas as pd
import requests


DEFAULT_ENDPOINT = "http://localhost:1234"
DEFAULT_MODEL = "openai/gpt-oss-20b"
TOOL_NAME = "record_contextual_rewrites"


SYSTEM_PROMPT = """You rewrite dataset rows for a privacy-preserving hate-speech-detection challenge.

Use the DP-MLM paper as a rewriting discipline: treat the original row as the fixed context, then produce a contextual replacement that preserves semantic utility while obfuscating the surface form. This is not summarization.

For every item:
1. Preserve the supplied hs-label semantics. If hs=1, the rewrite must still read as hate/offensive toward the same kind of target. If hs=0, the rewrite must not become hate speech. HSD utility is more important than politeness.
2. Preserve stance, target category, protected group references needed for classification, negation, quotation/reporting status, counterspeech status, sarcasm, and intensity. Do not turn an attack into support, do not turn criticism into endorsement, and do not swap the attacked group with the opposing group.
3. Change wording and syntax substantially. Avoid copying long spans. Reorder clauses, swap constructions, and alter phrasing while keeping the same row-level context.
4. Synthesize private identifiers into plausible counterparts of the same type. Change personal names, usernames, handles, emails, phone numbers, street addresses, non-essential locations, URLs, account IDs, hashtags used as personal tags, and other unique identifiers. Preserve only public/protected category words required for the hate-speech label, such as religions, nationalities, ethnic groups, gender/sexuality terms, or political categories when they are the target.
5. Randomize phone numbers, emails, handles, URLs, and IDs in realistic formats without copying original digits or strings. Replace incidental people with different plausible names. Replace special or distinctive names with unrelated plausible names unless the name itself is a protected/public target necessary for classification. In the tool result, set private_identifiers_synthesized=true when every private identifier was synthesized, or when the input contained no private identifiers.
6. Change action wording and predicate structure with semantically equivalent alternatives. Do not flip who did what to whom, do not change accusation polarity, and do not alter whether the row is threat, insult, exclusion, counterspeech, quotation, or neutral discussion.
7. Do not add, remove, or change claims beyond identifier synthesis. Do not invent new events or factual details that change the label.
8. Do not censor, moralize, apologize, explain, or refuse. If profanity or abusive intent is part of the original signal, keep comparable intensity in the rewrite.
9. Keep the same language and roughly comparable length. Do not return bullets unless the input is already a list.

Critical target-direction examples:
- If the original attacks women while defending men, the rewrite must still attack women while defending men.
- If the original attacks men while defending women, the rewrite must still attack men while defending women.
- If the original calls something misandrist, do not rewrite it as misogynistic. If it calls something misogynistic, do not rewrite it as misandrist.
- If the original uses a slur or vulgar insult as the hate/offense signal, replace it with a different but similarly strong insult; do not sanitize it into neutral language.
- If the original says women do not deserve opinions equal to men's until they accomplish what men have, the rewrite must preserve that discriminatory claim. It must not become "women deserve equal influence" or any other egalitarian statement.
- If the original says a group should leave, be removed, be silenced, be harmed, or be denied status, the rewrite must preserve the same exclusionary or hostile action in different words.

Return exactly one rewrite for each input item by calling the required tool."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Morph a CSV text column using LM Studio tool calling."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/train/train_split.csv"),
        help="Input CSV path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/outputs/lmstudio_contextual_morph_20260617/"
            "train_split.gpt_oss20b_contextual_morph.csv"
        ),
        help="Output CSV path.",
    )
    parser.add_argument("--text-col", default="text", help="Text column to rewrite.")
    parser.add_argument("--id-col", default="ID", help="Stable row id column.")
    parser.add_argument("--label-col", default="hs", help="Optional HSD label column.")
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="LM Studio base URL or /v1/chat/completions URL.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LM Studio model id.")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument(
        "--batch-char-limit",
        type=int,
        default=4500,
        help="Maximum total input characters per request before splitting a batch.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.55)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--max-tokens", type=int, default=3500)
    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high"],
        default="low",
        help="Optional gpt-oss reasoning effort hint.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only rewrite this many rows. The output CSV still keeps all rows.",
    )
    parser.add_argument("--offset", type=int, default=0, help="First row index to rewrite.")
    parser.add_argument(
        "--cache",
        type=Path,
        help="JSONL cache path. Defaults to output path with .rewrites.jsonl suffix.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        help="Summary JSON path. Defaults to output path with .summary.json suffix.",
    )
    parser.add_argument(
        "--min-change-chars",
        type=int,
        default=12,
        help="Exact unchanged rewrites are rejected for texts at least this long.",
    )
    parser.add_argument("--min-length-ratio", type=float, default=0.45)
    parser.add_argument("--max-length-ratio", type=float, default=1.9)
    parser.add_argument(
        "--retry-passes",
        type=int,
        default=2,
        help="End-of-run retry passes for rows that failed the main pass.",
    )
    parser.add_argument(
        "--retry-batch-size",
        type=int,
        default=10,
        help="Batch size for aggregated failed-row retry passes.",
    )
    parser.add_argument(
        "--retry-batch-char-limit",
        type=int,
        default=4500,
        help="Character cap for aggregated failed-row retry batches.",
    )
    parser.add_argument(
        "--require-model-checks",
        action="store_true",
        help="Reject rows when the model's boolean preservation checks are false.",
    )
    parser.add_argument(
        "--fail-on-unrewritten",
        action="store_true",
        help="Exit non-zero if any selected row failed or remained unchanged.",
    )
    return parser.parse_args()


def normalize_endpoint(endpoint: str) -> str:
    stripped = endpoint.rstrip("/")
    if stripped.endswith("/v1/chat/completions"):
        return stripped
    if stripped.endswith("/chat/completions"):
        return stripped
    if stripped.endswith("/v1"):
        return f"{stripped}/chat/completions"
    return f"{stripped}/v1/chat/completions"


def rewrite_schema() -> dict[str, Any]:
    item_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "id",
            "rewritten_text",
            "meaning_preserved",
            "surface_changed",
            "hs_label_preserved",
            "target_direction_preserved",
            "private_identifiers_synthesized",
        ],
        "properties": {
            "id": {"type": "string"},
            "rewritten_text": {"type": "string"},
            "meaning_preserved": {"type": "boolean"},
            "surface_changed": {"type": "boolean"},
            "hs_label_preserved": {"type": "boolean"},
            "target_direction_preserved": {"type": "boolean"},
            "private_identifiers_synthesized": {"type": "boolean"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "items": item_schema,
            }
        },
    }


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def cache_key(row_index: int, row_id: str) -> str:
    return f"{row_index}\t{row_id}"


def load_cache(path: Path, original_hashes: dict[str, str]) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{path}:{line_number}: invalid JSONL cache") from exc
            key = cache_key(int(record["row_index"]), str(record["id"]))
            if record.get("status") != "ok":
                continue
            if record.get("original_sha256") != original_hashes.get(key):
                continue
            rewritten_text = record.get("rewritten_text")
            if isinstance(rewritten_text, str):
                records[key] = record
    return records


def append_cache(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_output(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


def selected_row_indices(row_count: int, offset: int, limit: int | None) -> set[int]:
    start = max(offset, 0)
    stop = row_count if limit is None else min(row_count, start + max(limit, 0))
    return set(range(start, stop))


def make_batches(
    pending: list[dict[str, Any]],
    *,
    batch_size: int,
    batch_char_limit: int,
) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for item in pending:
        item_chars = len(item["text"])
        would_exceed_size = len(current) >= batch_size
        would_exceed_chars = current and current_chars + item_chars > batch_char_limit
        if would_exceed_size or would_exceed_chars:
            batches.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += item_chars
    if current:
        batches.append(current)
    return batches


def make_payload(args: argparse.Namespace, batch: list[dict[str, Any]]) -> dict[str, Any]:
    user_items = [
        {
            "id": item["id"],
            "row_index": item["row_index"],
            "hs": item.get("label"),
            "text": item["text"],
        }
        for item in batch
    ]
    payload: dict[str, Any] = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": (
                            "Rewrite each text with the same context and label "
                            "semantics, but a different surface form."
                        ),
                        "items": user_items,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": TOOL_NAME,
                    "description": (
                        "Record one contextual semantic morph for each input row."
                    ),
                    "parameters": rewrite_schema(),
                    "strict": True,
                },
            }
        ],
        "tool_choice": "required",
    }
    if args.reasoning_effort:
        payload["reasoning_effort"] = args.reasoning_effort
    return payload


def post_completion(
    endpoint: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: float,
    max_retries: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(endpoint, json=payload, timeout=timeout_seconds)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP {response.status_code}: {response.text[:1000]}"
                )
            return response.json()
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt == max_retries:
                break
            time.sleep(min(30.0, 2.0**attempt))
    raise RuntimeError(f"LM Studio request failed: {last_error}") from last_error


def extract_tool_payload(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("response has no choices")
    message = choices[0].get("message") or {}
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        if function.get("name") != TOOL_NAME:
            continue
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            raise RuntimeError("tool arguments are not a JSON string")
        return json.loads(arguments)
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return json.loads(content)
    raise RuntimeError("response did not contain tool call arguments")


def validate_rewrite(
    *,
    original: str,
    rewritten: str,
    returned: dict[str, Any],
    args: argparse.Namespace,
) -> tuple[bool, str]:
    if args.require_model_checks:
        for field in (
            "meaning_preserved",
            "surface_changed",
            "hs_label_preserved",
            "target_direction_preserved",
        ):
            if returned.get(field) is not True:
                return False, f"model_check_failed:{field}"
    cleaned = rewritten.strip()
    if not cleaned:
        return False, "empty_rewrite"
    if len(original.strip()) >= args.min_change_chars and cleaned == original.strip():
        return False, "unchanged"
    if len(original.strip()) >= args.min_change_chars:
        ratio = len(cleaned) / max(len(original.strip()), 1)
        if ratio < args.min_length_ratio:
            return False, f"too_short:{ratio:.3f}"
        if ratio > args.max_length_ratio:
            return False, f"too_long:{ratio:.3f}"
    return True, "ok"


def normalize_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise RuntimeError("tool payload missing items array")
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("tool payload item is not an object")
        row_id = item.get("id")
        rewritten_text = item.get("rewritten_text")
        if not isinstance(row_id, str) or not isinstance(rewritten_text, str):
            raise RuntimeError("tool payload item has invalid id or rewritten_text")
        normalized.append(item)
    return normalized


def rewrite_batch_once(
    *,
    args: argparse.Namespace,
    endpoint: str,
    batch: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    response = post_completion(
        endpoint,
        make_payload(args, batch),
        timeout_seconds=args.timeout_seconds,
        max_retries=args.max_retries,
    )
    payload = extract_tool_payload(response)
    items = normalize_items(payload)
    expected_ids = [item["id"] for item in batch]
    returned_ids = [item["id"] for item in items]
    if returned_ids != expected_ids:
        raise RuntimeError(f"id order mismatch: expected {expected_ids}, got {returned_ids}")
    return items


def record_for_result(
    *,
    source_item: dict[str, Any],
    rewritten_text: str,
    status: str,
    reason: str,
    model: str,
) -> dict[str, Any]:
    original = source_item["text"]
    return {
        "id": source_item["id"],
        "row_index": source_item["row_index"],
        "status": status,
        "reason": reason,
        "model": model,
        "timestamp_utc": now_utc(),
        "original_sha256": sha256_text(original),
        "rewritten_sha256": sha256_text(rewritten_text),
        "original_length": len(original),
        "rewritten_length": len(rewritten_text),
        "rewritten_text": rewritten_text,
    }


def rewrite_batch(
    *,
    args: argparse.Namespace,
    endpoint: str,
    batch: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        returned_items = rewrite_batch_once(args=args, endpoint=endpoint, batch=batch)
    except Exception as exc:
        return [
            record_for_result(
                source_item=item,
                rewritten_text=item["text"],
                status="failed",
                reason=type(exc).__name__ + ":" + str(exc)[:500],
                model=args.model,
            )
            for item in batch
        ]

    records = []
    for source_item, returned in zip(batch, returned_items, strict=True):
        rewritten = returned["rewritten_text"].strip()
        ok, reason = validate_rewrite(
            original=source_item["text"],
            rewritten=rewritten,
            returned=returned,
            args=args,
        )
        if not ok:
            records.append(
                record_for_result(
                    source_item=source_item,
                    rewritten_text=source_item["text"],
                    status="failed",
                    reason=reason,
                    model=args.model,
                )
            )
            continue
        records.append(
            record_for_result(
                source_item=source_item,
                rewritten_text=rewritten,
                status="ok",
                reason=reason,
                model=args.model,
            )
        )
    return records


def apply_records(
    *,
    records: list[dict[str, Any]],
    rewritten_df: pd.DataFrame,
    text_col: str,
    failed_items_by_key: dict[str, dict[str, Any]],
    source_by_key: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    ok_count = 0
    failed_count = 0
    for record in records:
        key = cache_key(int(record["row_index"]), str(record["id"]))
        if record["status"] == "ok":
            rewritten_df.at[record["row_index"], text_col] = record["rewritten_text"]
            failed_items_by_key.pop(key, None)
            ok_count += 1
            continue
        source_item = source_by_key.get(key)
        if source_item is not None:
            failed_items_by_key[key] = source_item
        failed_count += 1
    return ok_count, failed_count


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")
    if args.retry_batch_size < 1:
        raise SystemExit("--retry-batch-size must be positive")
    if args.retry_passes < 0:
        raise SystemExit("--retry-passes must be non-negative")
    endpoint = normalize_endpoint(args.endpoint)
    cache_path = args.cache or args.output.with_suffix(".rewrites.jsonl")
    summary_path = args.summary or args.output.with_suffix(".summary.json")

    df = pd.read_csv(args.input)
    if args.text_col not in df.columns:
        raise SystemExit(f"missing text column: {args.text_col}")
    if args.id_col not in df.columns:
        raise SystemExit(f"missing id column: {args.id_col}")
    label_col = args.label_col if args.label_col in df.columns else None

    rewritten_df = df.copy()
    selected_indices = selected_row_indices(len(df), args.offset, args.limit)
    source_items: list[dict[str, Any]] = []
    original_hashes: dict[str, str] = {}
    for row_index, row in df.iterrows():
        row_id = str(row[args.id_col])
        text = "" if pd.isna(row[args.text_col]) else str(row[args.text_col])
        key = cache_key(row_index, row_id)
        original_hashes[key] = sha256_text(text)
        if row_index not in selected_indices:
            continue
        source_items.append(
            {
                "id": row_id,
                "row_index": int(row_index),
                "label": None if label_col is None else row[label_col],
                "text": text,
            }
        )

    source_by_key = {
        cache_key(item["row_index"], item["id"]): item for item in source_items
    }
    cached = load_cache(cache_path, original_hashes)
    for key, record in cached.items():
        row_index_text, _row_id = key.split("\t", 1)
        row_index = int(row_index_text)
        if row_index in selected_indices:
            rewritten_df.at[row_index, args.text_col] = record["rewritten_text"]

    pending = [
        item for item in source_items if cache_key(item["row_index"], item["id"]) not in cached
    ]
    batches = make_batches(
        pending,
        batch_size=args.batch_size,
        batch_char_limit=args.batch_char_limit,
    )

    print(
        json.dumps(
            {
                "input": str(args.input),
                "output": str(args.output),
                "cache": str(cache_path),
                "endpoint": endpoint,
                "model": args.model,
                "selected_rows": len(source_items),
                "cached_rows": len(cached),
                "pending_rows": len(pending),
                "batches": len(batches),
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )

    completed = 0
    failed_records = 0
    failed_items_by_key: dict[str, dict[str, Any]] = {}
    for batch_number, batch in enumerate(batches, start=1):
        started = time.perf_counter()
        records = rewrite_batch(args=args, endpoint=endpoint, batch=batch)
        append_cache(cache_path, records)
        ok_count, failed_count = apply_records(
            records=records,
            rewritten_df=rewritten_df,
            text_col=args.text_col,
            failed_items_by_key=failed_items_by_key,
            source_by_key=source_by_key,
        )
        completed += ok_count
        failed_records += failed_count
        write_output(rewritten_df, args.output)
        elapsed = time.perf_counter() - started
        print(
            json.dumps(
                {
                    "batch": batch_number,
                    "batches": len(batches),
                    "phase": "main",
                    "rows": len(batch),
                    "ok_total": completed,
                    "failed_record_total": failed_records,
                    "failed_pending": len(failed_items_by_key),
                    "elapsed_seconds": round(elapsed, 3),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )

    for retry_pass in range(1, args.retry_passes + 1):
        if not failed_items_by_key:
            break
        retry_pending = list(failed_items_by_key.values())
        retry_batches = make_batches(
            retry_pending,
            batch_size=args.retry_batch_size,
            batch_char_limit=args.retry_batch_char_limit,
        )
        print(
            json.dumps(
                {
                    "phase": "retry",
                    "retry_pass": retry_pass,
                    "pending_rows": len(retry_pending),
                    "batches": len(retry_batches),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        for batch_number, batch in enumerate(retry_batches, start=1):
            started = time.perf_counter()
            records = rewrite_batch(args=args, endpoint=endpoint, batch=batch)
            append_cache(cache_path, records)
            ok_count, failed_count = apply_records(
                records=records,
                rewritten_df=rewritten_df,
                text_col=args.text_col,
                failed_items_by_key=failed_items_by_key,
                source_by_key=source_by_key,
            )
            completed += ok_count
            failed_records += failed_count
            write_output(rewritten_df, args.output)
            elapsed = time.perf_counter() - started
            print(
                json.dumps(
                    {
                        "batch": batch_number,
                        "batches": len(retry_batches),
                        "phase": "retry",
                        "retry_pass": retry_pass,
                        "rows": len(batch),
                        "ok_total": completed,
                        "failed_record_total": failed_records,
                        "failed_pending": len(failed_items_by_key),
                        "elapsed_seconds": round(elapsed, 3),
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )

    if not batches:
        write_output(rewritten_df, args.output)

    selected_changed = 0
    selected_unchanged = 0
    for row_index in selected_indices:
        if row_index >= len(df):
            continue
        if str(df.at[row_index, args.text_col]) == str(
            rewritten_df.at[row_index, args.text_col]
        ):
            selected_unchanged += 1
        else:
            selected_changed += 1

    summary = {
        "input": str(args.input),
        "output": str(args.output),
        "cache": str(cache_path),
        "endpoint": endpoint,
        "model": args.model,
        "row_count": len(df),
        "selected_rows": len(source_items),
        "selected_changed": selected_changed,
        "selected_unchanged": selected_unchanged,
        "pending_at_start": len(pending),
        "failed_records_this_run": failed_records,
        "final_failed_rows": len(failed_items_by_key),
        "finished_utc": now_utc(),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True), file=sys.stderr)

    if args.fail_on_unrewritten and (failed_items_by_key or selected_unchanged):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
