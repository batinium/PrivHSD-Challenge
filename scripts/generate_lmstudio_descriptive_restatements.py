#!/usr/bin/env python3
"""Generate concise third-person restatements through an LM Studio chat model."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib import error, request


DEFAULT_ENDPOINT = "http://100.120.207.64:1234"
DEFAULT_MODEL = "qwen3.5-4b"
TOOL_NAME = "record_descriptive_restatement_batch"


SYSTEM_PROMPT = f"""Call the required {TOOL_NAME} tool. Do not explain. /no_think

You rewrite already privacy-protected comments into short third-person evidence
sentences for hate-speech pipeline testing.

For each input item:
1. Return exactly one sentence, in the same order.
2. Start with "The comment" whenever natural.
3. Preserve the hate/non-hate label semantics.
4. If hs=1, preserve every protected/minority group, public target group, and
   accused/defended group that affects the hate-speech label. Do not choose only
   one convenient focus if the source has multiple label-relevant targets.
5. If hs=0, do not create hate speech; describe the original discussion,
   criticism, quote, counterspeech, or non-protected insult faithfully.
6. Preserve public/protected group words needed for classification, including
   religions, nationalities, ethnicities, gender, sexuality, disability, age,
   immigration status, political identity when relevant, and similar groups.
7. If the source has typed target placeholders like [TARGET_GROUP:religion],
   expand them into a generic readable category such as "a religious group"
   rather than dropping the category. Do not invent a concrete group name.
8. Keep direct privacy placeholders such as [PERSON], [USER], [URL], [LOCATION],
   [ORG], and [STYLE] exactly as placeholders; do not replace them with real
   names, handles, places, links, emails, or IDs.
9. Preserve accusation context such as anti-semitism, racism, genocide,
   replacement, invasion, grooming, or terrorism claims when present; these can
   be label-relevant even if the sentence also mentions a named public figure.
10. Preserve the direction of hostility: who is attacked, who is defended, and
   who is accused. Do not convert criticism of one group into criticism of a
   different person or group.
11. Preserve accusation roles exactly. If the source says A accuses B of C, the
   restatement must still say A accuses B of C; do not make A the accused, B the
   accuser, or C a label for the wrong side.
   Bad: "criticizes defenders for their anti-semitism."
   Good: "criticizes defenders who accuse critics of anti-semitism."
12. If the source uses a derogatory or offensive term for a political,
   protected, or minority group, include the group and describe the abuse in
   abstract form. For example, "uses an ableist insult against leftist
   defenders" is better than dropping the leftist defenders entirely.
13. Preserve offensive intensity in abstract form when exact wording is unsafe:
   say "uses a slur", "uses profane abuse", or "insults X" instead of silently
   removing the abuse signal.
14. Do not add new facts, new groups, new targets, or stronger threats than the
   input contains.
15. Keep the sentence concise and clear enough for a reviewer to classify.

Return only the ordered restatements via the required tool."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate descriptive restatements for a protected CSV."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--replaced-output",
        type=Path,
        help="Optional CSV preserving the input schema with text replaced by restatements.",
    )
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--text-col", default="text")
    parser.add_argument("--id-col", default="ID")
    parser.add_argument("--label-col", default="hs")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=2200)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def normalize_base_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/v1/chat/completions"):
        return endpoint[: -len("/v1/chat/completions")]
    if endpoint.endswith("/chat/completions"):
        return endpoint[: -len("/chat/completions")]
    if endpoint.endswith("/v1"):
        return endpoint[: -len("/v1")]
    return endpoint


def chat_endpoint(endpoint: str) -> str:
    return normalize_base_endpoint(endpoint) + "/v1/chat/completions"


def tool_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["restatements"],
        "properties": {
            "restatements": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
        "additionalProperties": False,
    }


def build_user_message(batch: list[dict[str, str]]) -> str:
    rows = []
    for item in batch:
        rows.append(
            {
                "id": item["id"],
                "hs": item["hs"],
                "protected_text": item["text"],
            }
        )
    return "Rewrite these rows into ordered descriptive restatements:\n" + json.dumps(
        rows,
        ensure_ascii=False,
    )


def build_payload(args: argparse.Namespace, batch: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "model": args.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(batch)},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": TOOL_NAME,
                    "description": "Record exactly one ordered restatement for each input item.",
                    "parameters": tool_schema(),
                },
            }
        ],
        "tool_choice": "required",
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
    }


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_tool_response(response: dict[str, Any], expected_count: int) -> list[str]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("response missing choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("response missing message")
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        raise RuntimeError("response missing tool_calls")
    function = tool_calls[0].get("function")
    if not isinstance(function, dict):
        raise RuntimeError("tool call missing function")
    arguments = function.get("arguments")
    if not isinstance(arguments, str):
        raise RuntimeError("tool call missing arguments")
    parsed = json.loads(arguments)
    restatements = parsed.get("restatements")
    if not isinstance(restatements, list):
        raise RuntimeError("tool payload missing restatements array")
    if len(restatements) != expected_count:
        raise RuntimeError(
            f"restatement count mismatch: expected {expected_count}, got {len(restatements)}"
        )
    return [normalize_restatement(str(item or "")) for item in restatements]


def normalize_restatement(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value


def load_cache(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            records[str(record["id"])] = record
    return records


def append_cache(path: Path | None, records: list[dict[str, Any]]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_rows(args: argparse.Namespace) -> tuple[list[str], list[dict[str, str]]]:
    with args.input.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        for column in (args.id_col, args.text_col, args.label_col):
            if column not in fieldnames:
                raise SystemExit(f"input missing required column: {column}")
        rows = [
            {
                **row,
                "id": row[args.id_col],
                "text": row[args.text_col],
                "hs": row[args.label_col],
            }
            for row in reader
        ]
    return fieldnames, rows


def request_batch(
    args: argparse.Namespace,
    batch: list[dict[str, str]],
) -> tuple[list[str] | None, str, float]:
    payload = build_payload(args, batch)
    started = time.perf_counter()
    last_error = ""
    url = chat_endpoint(args.endpoint)
    for attempt in range(args.max_retries + 1):
        try:
            response = post_json(url, payload, args.timeout_seconds)
            return parse_tool_response(response, len(batch)), "", time.perf_counter() - started
        except (RuntimeError, json.JSONDecodeError, TimeoutError, error.URLError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < args.max_retries:
                time.sleep(1.5 * (attempt + 1))
    return None, last_error, time.perf_counter() - started


def main() -> None:
    args = parse_args()
    fieldnames, rows = read_rows(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.replaced_output:
        args.replaced_output.parent.mkdir(parents=True, exist_ok=True)
    cache_path = args.cache or args.output.with_suffix(".cache.jsonl")
    summary_path = args.summary or args.output.with_suffix(".summary.json")
    if args.force and cache_path.exists():
        cache_path.unlink()
    cache = {} if args.force else load_cache(cache_path)

    generated: dict[str, dict[str, Any]] = dict(cache)
    pending = [
        row
        for row in rows
        if generated.get(row["id"], {}).get("status") != "ok"
    ]

    for start in range(0, len(pending), args.batch_size):
        batch = pending[start : start + args.batch_size]
        print(f"batch {start // args.batch_size + 1}: {len(batch)} rows", flush=True)
        restatements, error_message, elapsed = request_batch(args, batch)
        records = []
        if restatements is None:
            for row in batch:
                records.append(
                    {
                        "id": row["id"],
                        "status": "failed",
                        "error": error_message,
                        "elapsed_seconds": round(elapsed / max(len(batch), 1), 4),
                        "restatement": "",
                    }
                )
        else:
            for row, restatement in zip(batch, restatements):
                records.append(
                    {
                        "id": row["id"],
                        "status": "ok" if restatement else "empty",
                        "error": "",
                        "elapsed_seconds": round(elapsed / max(len(batch), 1), 4),
                        "restatement": restatement,
                    }
                )
        append_cache(cache_path, records)
        generated.update({str(record["id"]): record for record in records})

    output_fields = [*fieldnames, "qwen35_descriptive_restatement", "generation_status", "generation_error"]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        for row in rows:
            record = generated.get(row["id"], {})
            writer.writerow(
                {
                    **{field: row.get(field, "") for field in fieldnames},
                    "qwen35_descriptive_restatement": record.get("restatement", ""),
                    "generation_status": record.get("status", "missing"),
                    "generation_error": record.get("error", ""),
                }
            )

    if args.replaced_output:
        with args.replaced_output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                record = generated.get(row["id"], {})
                restatement = record.get("restatement") or row[args.text_col]
                out_row = {field: row.get(field, "") for field in fieldnames}
                out_row[args.text_col] = restatement
                writer.writerow(out_row)

    statuses = {}
    for record in generated.values():
        statuses[record.get("status", "missing")] = statuses.get(record.get("status", "missing"), 0) + 1
    summary = {
        "input": str(args.input),
        "output": str(args.output),
        "replaced_output": str(args.replaced_output) if args.replaced_output else None,
        "cache": str(cache_path),
        "endpoint": args.endpoint,
        "model": args.model,
        "rows": len(rows),
        "status_counts": statuses,
        "batch_size": args.batch_size,
        "temperature": args.temperature,
        "top_p": args.top_p,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
