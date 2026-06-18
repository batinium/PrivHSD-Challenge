"""Backend/admin CSV bundle orchestration.

This module builds staged CSV artifacts for the admin/backend flow:

1. DeHateBERT token-importance CSV, reused when already present.
2. Locked PII/style scrubbed CSV.
3. LLM descriptive restatement CSVs for review backends.
4. Optional final high-confidence direct-identifier scrub on restatements.
5. Source-vs-restatement deviation audit for admin triage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib import error, request

from .csv_pipeline import read_csv, write_csv, write_json
from .metrics import cleanup_high_confidence_residuals, high_confidence_residual_spans
from .models.hf_hsd_classifier_runtime import (
    DEFAULT_HF_HSD_BATCH_SIZE,
    DEFAULT_HF_HSD_MAX_LENGTH,
    DEFAULT_HF_HSD_MODEL_PATH,
    DEFAULT_HF_HSD_THRESHOLD,
    HfHsdClassifierRuntime,
)
from .restatement_audit import run_restatement_deviation_audit
from .simple_pipeline import run_final_csv_pipeline
from .submission import sha256_file, validate_submission


DEFAULT_RESTATEMENT_ENDPOINT = "http://100.120.207.64:1234"
DEFAULT_RESTATEMENT_MODEL = "qwen3.5-4b"
DEFAULT_TOKEN_PROTECT_THRESHOLD = 0.03
RESTATEMENT_TOOL_NAME = "record_backend_restatement_batch"
SOURCE_TEXT_COL = "source_text"
SCRUBBED_TEXT_COL = "scrubbed_text"
PREDICTED_LABEL_COL = "hs_predicted"
PREDICTION_SCORE_COL = "hf_hsd_score"

TOKEN_PATTERN = re.compile(
    r"\[[A-Z][A-Z_]*(?::[A-Za-z0-9_/-]+)?\]"
    r"|https?://\S+"
    r"|@[A-Za-z0-9._-]+"
    r"|#[A-Za-z0-9_]{2,}"
    r"|[A-Za-z][A-Za-z'-]*"
    r"|\d+(?:[./-]\d+)*"
)

RESTATEMENT_SYSTEM_PROMPT = f"""Call the required {RESTATEMENT_TOOL_NAME} tool. Do not explain. /no_think

You rewrite already privacy-protected comments into concise third-person
evidence sentences for a hate-speech review backend.

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


class BackendBundleError(ValueError):
    pass


@dataclass(frozen=True)
class TokenSpan:
    index: int
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class BackendBundlePaths:
    importance_csv: Path
    prediction_csv: Path
    scrubbed_csv: Path
    scrubbed_manifest: Path
    scrubbed_audit: Path
    restatement_input_csv: Path
    restated_csv: Path
    restatement_annotated_csv: Path
    restatement_cache: Path
    deviation_audit_csv: Path
    deviation_audit_summary: Path
    manifest: Path
    validation_json: Path


def default_bundle_paths(input_path: Path, output_dir: Path) -> BackendBundlePaths:
    stem = input_path.stem
    return BackendBundlePaths(
        importance_csv=output_dir / f"{stem}.dehatebert_token_importance.csv",
        prediction_csv=output_dir / f"{stem}.dehatebert_predictions.csv",
        scrubbed_csv=output_dir / f"{stem}.scrubbed.csv",
        scrubbed_manifest=output_dir / f"{stem}.scrubbed.manifest.json",
        scrubbed_audit=output_dir / f"{stem}.scrubbed.audit.json",
        restatement_input_csv=output_dir / f"{stem}.restatement_input.csv",
        restated_csv=output_dir / f"{stem}.restated.csv",
        restatement_annotated_csv=output_dir / f"{stem}.restated.annotated.csv",
        restatement_cache=output_dir / f"{stem}.restatement.cache.jsonl",
        deviation_audit_csv=output_dir / f"{stem}.restated.deviation_audit.csv",
        deviation_audit_summary=(
            output_dir / f"{stem}.restated.deviation_audit.summary.json"
        ),
        manifest=output_dir / f"{stem}.backend_bundle.manifest.json",
        validation_json=output_dir / f"{stem}.restated.validation.json",
    )


def iter_tokens(text: str) -> list[TokenSpan]:
    return [
        TokenSpan(index=index, text=match.group(0), start=match.start(), end=match.end())
        for index, match in enumerate(TOKEN_PATTERN.finditer(text))
    ]


def masked_text(text: str, token: TokenSpan, mask_token: str) -> str:
    return f"{text[: token.start]}{mask_token}{text[token.end :]}"


def generate_token_importance_csv(
    input_path: Path,
    output_path: Path,
    *,
    text_col: str = "text",
    id_col: str | None = None,
    model_path: str = DEFAULT_HF_HSD_MODEL_PATH,
    threshold: float = DEFAULT_HF_HSD_THRESHOLD,
    device: str = "auto",
    max_length: int = DEFAULT_HF_HSD_MAX_LENGTH,
    batch_size: int = DEFAULT_HF_HSD_BATCH_SIZE,
    protect_threshold: float = DEFAULT_TOKEN_PROTECT_THRESHOLD,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    if text_col not in fieldnames:
        raise BackendBundleError(f"missing text column {text_col!r}")
    if id_col and id_col not in fieldnames:
        raise BackendBundleError(f"missing id column {id_col!r}")
    classifier = HfHsdClassifierRuntime(
        model_path=model_path,
        threshold=threshold,
        device=device,
        max_length=max_length,
    )
    mask_token = classifier._tokenizer.mask_token or "[MASK]"
    output_rows: list[dict[str, Any]] = []
    total = len(rows)
    for row_index, row in enumerate(rows, start=1):
        if progress_callback and row_index == 1:
            progress_callback(
                {
                    "stage": "token_importance",
                    "processed": 0,
                    "total": total,
                    "detail": "Computing DeHateBERT occlusion importances.",
                }
            )
        row_id = str(row.get(id_col or "", "") or row_index)
        text = str(row.get(text_col, "") or "")
        tokens = iter_tokens(text)
        if not tokens:
            continue
        baseline_score = classifier._scores([text])[0]
        masked_texts = [masked_text(text, token, mask_token) for token in tokens]
        masked_scores: list[float] = []
        for offset in range(0, len(masked_texts), batch_size):
            masked_scores.extend(
                classifier._scores(masked_texts[offset : offset + batch_size])
            )
        predicted_hate = bool(baseline_score >= classifier.threshold)
        for token, masked_score in zip(tokens, masked_scores, strict=True):
            delta = float(baseline_score - masked_score)
            abs_delta = abs(delta)
            output_rows.append(
                {
                    "row_index": row_index,
                    "row_id": row_id,
                    "token_index": token.index,
                    "token": token.text,
                    "start": token.start,
                    "end": token.end,
                    "baseline_hate_score": round(float(baseline_score), 6),
                    "masked_hate_score": round(float(masked_score), 6),
                    "delta_hate_score": round(delta, 6),
                    "abs_delta_hate_score": round(abs_delta, 6),
                    "predicted_hate": int(predicted_hate),
                    "protect_hsd_token": int(abs_delta >= protect_threshold),
                }
            )
        if progress_callback:
            progress_callback(
                {
                    "stage": "token_importance",
                    "processed": row_index,
                    "total": total,
                    "detail": "Computed DeHateBERT token importances.",
                }
            )
    output_rows.sort(
        key=lambda item: (
            int(item["row_index"]),
            -float(item["abs_delta_hate_score"]),
            int(item["token_index"]),
        )
    )
    fieldnames_out = [
        "row_index",
        "row_id",
        "token_index",
        "token",
        "start",
        "end",
        "baseline_hate_score",
        "masked_hate_score",
        "delta_hate_score",
        "abs_delta_hate_score",
        "predicted_hate",
        "protect_hsd_token",
    ]
    write_csv(output_path, output_rows, fieldnames_out)
    protected = sum(int(row["protect_hsd_token"]) for row in output_rows)
    return {
        "status": "generated",
        "path": str(output_path),
        "sha256": sha256_file(output_path),
        "row_count": len(rows),
        "token_rows": len(output_rows),
        "protected_tokens": protected,
        "model_path": model_path,
        "threshold": threshold,
        "protect_threshold": protect_threshold,
    }


def generate_hsd_predictions_csv(
    input_path: Path,
    output_path: Path,
    *,
    text_col: str = "text",
    id_col: str | None = None,
    model_path: str = DEFAULT_HF_HSD_MODEL_PATH,
    threshold: float = DEFAULT_HF_HSD_THRESHOLD,
    device: str = "auto",
    max_length: int = DEFAULT_HF_HSD_MAX_LENGTH,
    batch_size: int = DEFAULT_HF_HSD_BATCH_SIZE,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    if text_col not in fieldnames:
        raise BackendBundleError(f"missing text column {text_col!r}")
    if id_col and id_col not in fieldnames:
        raise BackendBundleError(f"missing id column {id_col!r}")
    if batch_size < 1:
        raise BackendBundleError("classification batch size must be positive")

    classifier = HfHsdClassifierRuntime(
        model_path=model_path,
        threshold=threshold,
        device=device,
        max_length=max_length,
    )
    output_rows: list[dict[str, Any]] = []
    total = len(rows)
    processed = 0
    for offset in range(0, total, batch_size):
        batch = rows[offset : offset + batch_size]
        scores = classifier._scores([str(row.get(text_col, "") or "") for row in batch])
        for batch_index, (row, score) in enumerate(zip(batch, scores, strict=True), start=1):
            row_index = offset + batch_index
            predicted_label = int(float(score) >= classifier.threshold)
            output_rows.append(
                {
                    "row_index": row_index,
                    "row_id": str(row.get(id_col or "", "") or row_index),
                    PREDICTION_SCORE_COL: round(float(score), 6),
                    PREDICTED_LABEL_COL: predicted_label,
                    "hf_hsd_threshold": classifier.threshold,
                }
            )
        processed += len(batch)
        if progress_callback:
            progress_callback(
                {
                    "stage": "hs_classification",
                    "processed": processed,
                    "total": total,
                    "detail": "Generated DeHateBERT labels for unlabeled rows.",
                }
            )

    write_csv(
        output_path,
        output_rows,
        [
            "row_index",
            "row_id",
            PREDICTION_SCORE_COL,
            PREDICTED_LABEL_COL,
            "hf_hsd_threshold",
        ],
    )
    positives = sum(int(row[PREDICTED_LABEL_COL]) for row in output_rows)
    return {
        "status": "generated",
        "path": str(output_path),
        "sha256": sha256_file(output_path),
        "row_count": len(rows),
        "positive_rows": positives,
        "negative_rows": len(rows) - positives,
        "model_path": model_path,
        "threshold": threshold,
    }


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


def restatement_tool_schema() -> dict[str, Any]:
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


def build_restatement_user_message(
    batch: list[dict[str, str]],
    *,
    text_col: str,
    id_col: str | None,
    label_col: str,
) -> str:
    payload = [
        {
            "id": str(row.get(id_col or "", "") or index + 1),
            "hs": str(row.get(label_col, "")),
            "protected_text": str(row.get(text_col, "") or ""),
        }
        for index, row in enumerate(batch)
    ]
    return "Rewrite these rows into ordered descriptive restatements:\n" + json.dumps(
        payload,
        ensure_ascii=False,
    )


def build_restatement_payload(
    batch: list[dict[str, str]],
    *,
    model: str,
    text_col: str,
    id_col: str | None,
    label_col: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": RESTATEMENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_restatement_user_message(
                    batch,
                    text_col=text_col,
                    id_col=id_col,
                    label_col=label_col,
                ),
            },
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": RESTATEMENT_TOOL_NAME,
                    "description": "Record exactly one ordered restatement for each input item.",
                    "parameters": restatement_tool_schema(),
                },
            }
        ],
        "tool_choice": "required",
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
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


def normalize_restatement(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


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


def request_restatement_batch(
    batch: list[dict[str, str]],
    *,
    endpoint: str,
    model: str,
    text_col: str,
    id_col: str | None,
    label_col: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    timeout_seconds: float,
    max_retries: int,
) -> tuple[list[str] | None, str, float]:
    payload = build_restatement_payload(
        batch,
        model=model,
        text_col=text_col,
        id_col=id_col,
        label_col=label_col,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )
    started = time.perf_counter()
    last_error = ""
    url = chat_endpoint(endpoint)
    for attempt in range(max_retries + 1):
        try:
            response = post_json(url, payload, timeout_seconds)
            return parse_tool_response(response, len(batch)), "", time.perf_counter() - started
        except (RuntimeError, json.JSONDecodeError, TimeoutError, error.URLError, error.HTTPError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
    return None, last_error, time.perf_counter() - started


def row_key(row: dict[str, str], *, id_col: str | None, row_index: int) -> str:
    return str(row.get(id_col or "", "") or row_index)


def load_restatement_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                records[str(record["id"])] = record
    return records


def append_restatement_cache(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def run_llm_restatement_csv(
    input_path: Path,
    *,
    restated_csv: Path,
    annotated_csv: Path,
    cache_path: Path,
    text_col: str = "text",
    id_col: str | None = None,
    label_col: str = "hs",
    endpoint: str = DEFAULT_RESTATEMENT_ENDPOINT,
    model: str = DEFAULT_RESTATEMENT_MODEL,
    batch_size: int = 5,
    temperature: float = 0.2,
    top_p: float = 0.9,
    max_tokens: int = 2200,
    timeout_seconds: float = 180.0,
    max_retries: int = 2,
    final_scrub: bool = True,
    allow_fallback: bool = False,
    force: bool = False,
    output_fieldnames: list[str] | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    if text_col not in fieldnames:
        raise BackendBundleError(f"missing text column {text_col!r}")
    if id_col and id_col not in fieldnames:
        raise BackendBundleError(f"missing id column {id_col!r}")
    if label_col not in fieldnames:
        raise BackendBundleError(f"missing label column {label_col!r}")
    if batch_size < 1:
        raise BackendBundleError("restatement batch size must be positive")
    restated_fieldnames = output_fieldnames or fieldnames
    if text_col not in restated_fieldnames:
        raise BackendBundleError(
            f"restated output fieldnames must contain text column {text_col!r}"
        )

    if force and cache_path.exists():
        cache_path.unlink()
    cache = {} if force else load_restatement_cache(cache_path)
    generated: dict[str, dict[str, Any]] = dict(cache)
    keyed_rows = [
        (row_key(row, id_col=id_col, row_index=index), row)
        for index, row in enumerate(rows, start=1)
    ]
    pending = [
        (key, row)
        for key, row in keyed_rows
        if generated.get(key, {}).get("status") not in {"ok", "ok_fallback"}
    ]
    total_pending = len(pending)
    processed_pending = 0

    def record_batch(batch_keys: list[str], batch_rows: list[dict[str, str]]) -> None:
        nonlocal processed_pending
        restatements, error_message, elapsed = request_restatement_batch(
            batch_rows,
            endpoint=endpoint,
            model=model,
            text_col=text_col,
            id_col=id_col,
            label_col=label_col,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        records: list[dict[str, Any]] = []
        if restatements is None and len(batch_rows) > 1:
            for single_key, single_row in zip(batch_keys, batch_rows, strict=True):
                record_batch([single_key], [single_row])
            return
        if restatements is None:
            for key, row in zip(batch_keys, batch_rows, strict=True):
                fallback = str(row.get(text_col, "") or "")
                status = "failed"
                restatement = ""
                if allow_fallback:
                    status = "ok_fallback"
                    restatement = fallback
                records.append(
                    {
                        "id": key,
                        "status": status,
                        "error": error_message,
                        "elapsed_seconds": round(elapsed / max(len(batch_rows), 1), 4),
                        "restatement": restatement,
                    }
                )
        else:
            for key, restatement in zip(batch_keys, restatements, strict=True):
                records.append(
                    {
                        "id": key,
                        "status": "ok" if restatement else "empty",
                        "error": "",
                        "elapsed_seconds": round(elapsed / max(len(batch_rows), 1), 4),
                        "restatement": restatement,
                    }
                )
        append_restatement_cache(cache_path, records)
        generated.update({str(record["id"]): record for record in records})
        processed_pending += len(records)
        if progress_callback:
            progress_callback(
                {
                    "stage": "llm_restatement",
                    "processed": processed_pending,
                    "total": total_pending,
                    "detail": "Generated backend review restatements.",
                }
            )

    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        record_batch([key for key, _row in batch], [row for _key, row in batch])

    annotated_rows: list[dict[str, Any]] = []
    restated_rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    final_cleanup_rows = 0
    final_cleanup_spans = 0
    residual_rows = 0
    for index, row in enumerate(rows, start=1):
        key = row_key(row, id_col=id_col, row_index=index)
        record = generated.get(key, {})
        status = str(record.get("status", "missing"))
        status_counts[status] = status_counts.get(status, 0) + 1
        restatement = str(record.get("restatement", "") or "")
        cleanup = cleanup_high_confidence_residuals(restatement) if final_scrub else {
            "text": restatement,
            "changed": False,
            "cleanup_count": 0,
            "counts_by_entity_type": {},
        }
        final_text = str(cleanup["text"])
        if cleanup.get("changed"):
            final_cleanup_rows += 1
            final_cleanup_spans += int(cleanup.get("cleanup_count") or 0)
        if high_confidence_residual_spans(final_text):
            residual_rows += 1
        annotated_rows.append(
            {
                **row,
                "backend_restatement": restatement,
                "backend_restatement_final": final_text,
                "restatement_status": status,
                "restatement_error": record.get("error", ""),
                "final_scrub_changed": int(bool(cleanup.get("changed"))),
                "final_scrub_count": int(cleanup.get("cleanup_count") or 0),
            }
        )
        out_row = dict(row)
        out_row[text_col] = final_text
        restated_rows.append(
            {fieldname: out_row.get(fieldname, "") for fieldname in restated_fieldnames}
        )
    if not allow_fallback:
        bad_statuses = {
            status: count
            for status, count in status_counts.items()
            if status != "ok"
        }
        if bad_statuses:
            raise BackendBundleError(
                f"restatement did not complete cleanly: {bad_statuses}"
            )
    annotated_fieldnames = [
        *fieldnames,
        "backend_restatement",
        "backend_restatement_final",
        "restatement_status",
        "restatement_error",
        "final_scrub_changed",
        "final_scrub_count",
    ]
    write_csv(annotated_csv, annotated_rows, annotated_fieldnames)
    write_csv(restated_csv, restated_rows, restated_fieldnames)
    return {
        "status": "ok" if status_counts.get("ok", 0) == len(rows) else "partial",
        "model": model,
        "endpoint": endpoint,
        "input": str(input_path),
        "restated_csv": str(restated_csv),
        "annotated_csv": str(annotated_csv),
        "cache": str(cache_path),
        "row_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "final_scrub": final_scrub,
        "final_cleanup_rows": final_cleanup_rows,
        "final_cleanup_spans": final_cleanup_spans,
        "residual_direct_rows": residual_rows,
        "restated_sha256": sha256_file(restated_csv),
        "annotated_sha256": sha256_file(annotated_csv),
    }


def insert_after_field(
    fieldnames: list[str],
    *,
    anchor: str,
    additions: list[str],
) -> list[str]:
    output: list[str] = []
    inserted = False
    for fieldname in fieldnames:
        if fieldname in additions:
            continue
        output.append(fieldname)
        if fieldname == anchor:
            output.extend(addition for addition in additions if addition not in output)
            inserted = True
    if not inserted:
        return [*additions, *output]
    return output


def add_admin_source_columns(
    annotated_csv: Path,
    source_csv: Path,
    *,
    text_col: str,
    id_col: str | None,
) -> dict[str, Any]:
    annotated_rows, annotated_fieldnames = read_csv(annotated_csv)
    source_rows, source_fieldnames = read_csv(source_csv)
    if text_col not in source_fieldnames:
        raise BackendBundleError(f"missing source text column {text_col!r}")
    if id_col and id_col not in source_fieldnames:
        raise BackendBundleError(f"missing source id column {id_col!r}")

    source_by_key = {
        row_key(row, id_col=id_col, row_index=index): row
        for index, row in enumerate(source_rows, start=1)
    }
    augmented_rows: list[dict[str, Any]] = []
    for index, row in enumerate(annotated_rows, start=1):
        key = row_key(row, id_col=id_col, row_index=index)
        source_row = source_by_key.get(key)
        if source_row is None and index <= len(source_rows):
            source_row = source_rows[index - 1]
        if source_row is None:
            raise BackendBundleError(f"could not map annotated row {index} to source")
        augmented = dict(row)
        augmented[SOURCE_TEXT_COL] = str(source_row.get(text_col, "") or "")
        augmented[SCRUBBED_TEXT_COL] = str(row.get(text_col, "") or "")
        augmented_rows.append(augmented)

    fieldnames = insert_after_field(
        annotated_fieldnames,
        anchor=text_col,
        additions=[SOURCE_TEXT_COL, SCRUBBED_TEXT_COL],
    )
    write_csv(annotated_csv, augmented_rows, fieldnames)
    return {
        "source_text_col": SOURCE_TEXT_COL,
        "scrubbed_text_col": SCRUBBED_TEXT_COL,
        "row_count": len(augmented_rows),
        "annotated_sha256": sha256_file(annotated_csv),
    }


def ensure_token_importance(
    input_path: Path,
    output_path: Path,
    *,
    text_col: str,
    id_col: str | None,
    model_path: str,
    threshold: float,
    device: str,
    max_length: int,
    batch_size: int,
    protect_threshold: float,
    force: bool,
    progress_callback: Any | None,
) -> dict[str, Any]:
    if output_path.exists() and not force:
        rows, _fieldnames = read_csv(output_path)
        return {
            "status": "loaded",
            "path": str(output_path),
            "sha256": sha256_file(output_path),
            "token_rows": len(rows),
            "model_path": model_path,
            "threshold": threshold,
            "protect_threshold": protect_threshold,
        }
    return generate_token_importance_csv(
        input_path,
        output_path,
        text_col=text_col,
        id_col=id_col,
        model_path=model_path,
        threshold=threshold,
        device=device,
        max_length=max_length,
        batch_size=batch_size,
        protect_threshold=protect_threshold,
        progress_callback=progress_callback,
    )


def ensure_hsd_predictions(
    input_path: Path,
    output_path: Path,
    *,
    text_col: str,
    id_col: str | None,
    model_path: str,
    threshold: float,
    device: str,
    max_length: int,
    batch_size: int,
    force: bool,
    progress_callback: Any | None,
) -> dict[str, Any]:
    if output_path.exists() and not force:
        rows, _fieldnames = read_csv(output_path)
        positives = sum(
            int(str(row.get(PREDICTED_LABEL_COL, "")).strip() == "1") for row in rows
        )
        return {
            "status": "loaded",
            "path": str(output_path),
            "sha256": sha256_file(output_path),
            "row_count": len(rows),
            "positive_rows": positives,
            "negative_rows": len(rows) - positives,
            "model_path": model_path,
            "threshold": threshold,
        }
    return generate_hsd_predictions_csv(
        input_path,
        output_path,
        text_col=text_col,
        id_col=id_col,
        model_path=model_path,
        threshold=threshold,
        device=device,
        max_length=max_length,
        batch_size=batch_size,
        progress_callback=progress_callback,
    )


def prediction_rows_by_key(
    prediction_csv: Path,
    *,
    id_col: str | None,
) -> dict[str, dict[str, str]]:
    rows, _fieldnames = read_csv(prediction_csv)
    records: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=1):
        key = str(row.get("row_id") or row.get(id_col or "", "") or index)
        records[key] = row
    return records


def build_restatement_input_csv(
    scrubbed_csv: Path,
    output_path: Path,
    *,
    prediction_csv: Path,
    text_col: str,
    id_col: str | None,
    label_col: str,
    force: bool,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(scrubbed_csv)
    if label_col in fieldnames:
        return {
            "status": "provided",
            "path": str(scrubbed_csv),
            "sha256": sha256_file(scrubbed_csv),
            "label_col": label_col,
            "label_source": "provided",
            "output_fieldnames": fieldnames,
            "helper_columns": [],
        }
    helper_columns = [label_col]
    if label_col != PREDICTED_LABEL_COL:
        helper_columns.append(PREDICTED_LABEL_COL)
    helper_columns.append(PREDICTION_SCORE_COL)
    output_fieldnames = list(fieldnames)
    internal_fieldnames = [*fieldnames, *helper_columns]
    if output_path.exists() and not force:
        return {
            "status": "loaded",
            "path": str(output_path),
            "sha256": sha256_file(output_path),
            "label_col": label_col,
            "label_source": "predicted",
            "output_fieldnames": output_fieldnames,
            "helper_columns": helper_columns,
        }

    predictions = prediction_rows_by_key(prediction_csv, id_col=id_col)
    augmented_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        key = row_key(row, id_col=id_col, row_index=index)
        prediction = predictions.get(key) or predictions.get(str(index))
        if prediction is None:
            raise BackendBundleError(f"missing classifier prediction for row {index}")
        label = str(prediction.get(PREDICTED_LABEL_COL, "") or "")
        score = str(prediction.get(PREDICTION_SCORE_COL, "") or "")
        augmented = dict(row)
        augmented[label_col] = label
        if label_col != PREDICTED_LABEL_COL:
            augmented[PREDICTED_LABEL_COL] = label
        augmented[PREDICTION_SCORE_COL] = score
        augmented_rows.append(augmented)
    write_csv(output_path, augmented_rows, internal_fieldnames)
    return {
        "status": "generated",
        "path": str(output_path),
        "sha256": sha256_file(output_path),
        "label_col": label_col,
        "label_source": "predicted",
        "output_fieldnames": output_fieldnames,
        "helper_columns": helper_columns,
    }


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_backend_bundle(
    input_path: Path,
    output_dir: Path,
    *,
    text_col: str = "text",
    id_col: str | None = None,
    label_col: str = "hs",
    importance_csv: Path | None = None,
    scrubbed_csv: Path | None = None,
    restated_csv: Path | None = None,
    restatement_annotated_csv: Path | None = None,
    deviation_audit_csv: Path | None = None,
    deviation_audit_summary: Path | None = None,
    manifest_path: Path | None = None,
    force_token_importance: bool = False,
    force_classification: bool = False,
    force_scrubbed: bool = False,
    force_restatement: bool = False,
    force_deviation_audit: bool = False,
    hf_hsd_model_path: str = DEFAULT_HF_HSD_MODEL_PATH,
    hf_hsd_threshold: float = DEFAULT_HF_HSD_THRESHOLD,
    hf_hsd_device: str = "auto",
    hf_hsd_batch_size: int = DEFAULT_HF_HSD_BATCH_SIZE,
    hf_hsd_max_length: int = DEFAULT_HF_HSD_MAX_LENGTH,
    token_protect_threshold: float = DEFAULT_TOKEN_PROTECT_THRESHOLD,
    restatement_endpoint: str = DEFAULT_RESTATEMENT_ENDPOINT,
    restatement_model: str = DEFAULT_RESTATEMENT_MODEL,
    restatement_batch_size: int = 5,
    restatement_temperature: float = 0.2,
    restatement_top_p: float = 0.9,
    restatement_max_tokens: int = 2200,
    restatement_timeout_seconds: float = 180.0,
    restatement_max_retries: int = 2,
    final_scrub: bool = True,
    allow_restatement_fallback: bool = False,
    progress_callback: Any | None = None,
    command: list[str] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = default_bundle_paths(input_path, output_dir)
    paths = BackendBundlePaths(
        importance_csv=importance_csv or paths.importance_csv,
        prediction_csv=paths.prediction_csv,
        scrubbed_csv=scrubbed_csv or paths.scrubbed_csv,
        scrubbed_manifest=(scrubbed_csv or paths.scrubbed_csv).with_suffix(".manifest.json")
        if scrubbed_csv
        else paths.scrubbed_manifest,
        scrubbed_audit=(scrubbed_csv or paths.scrubbed_csv).with_suffix(".audit.json")
        if scrubbed_csv
        else paths.scrubbed_audit,
        restatement_input_csv=paths.restatement_input_csv,
        restated_csv=restated_csv or paths.restated_csv,
        restatement_annotated_csv=restatement_annotated_csv or paths.restatement_annotated_csv,
        restatement_cache=(restatement_annotated_csv or paths.restatement_annotated_csv).with_suffix(".cache.jsonl"),
        deviation_audit_csv=deviation_audit_csv or paths.deviation_audit_csv,
        deviation_audit_summary=deviation_audit_summary or paths.deviation_audit_summary,
        manifest=manifest_path or paths.manifest,
        validation_json=(restated_csv or paths.restated_csv).with_suffix(".validation.json"),
    )
    token_importance = ensure_token_importance(
        input_path,
        paths.importance_csv,
        text_col=text_col,
        id_col=id_col,
        model_path=hf_hsd_model_path,
        threshold=hf_hsd_threshold,
        device=hf_hsd_device,
        max_length=hf_hsd_max_length,
        batch_size=hf_hsd_batch_size,
        protect_threshold=token_protect_threshold,
        force=force_token_importance,
        progress_callback=progress_callback,
    )
    scrubbed_loaded = (
        paths.scrubbed_csv.exists()
        and paths.scrubbed_manifest.exists()
        and paths.scrubbed_audit.exists()
        and not force_scrubbed
    )
    if scrubbed_loaded:
        scrubbed_manifest = load_json_file(paths.scrubbed_manifest)
    else:
        scrubbed_manifest = run_final_csv_pipeline(
            input_path,
            paths.scrubbed_csv,
            text_col=text_col,
            id_col=id_col,
            manifest_path=paths.scrubbed_manifest,
            audit_path=paths.scrubbed_audit,
            command=command,
            preset="exact",
            metric_depth="fast",
            hsd_classification_backend="hf_classifier",
            hf_hsd_model_path=hf_hsd_model_path,
            hf_hsd_threshold=hf_hsd_threshold,
            hf_hsd_device=hf_hsd_device,
            hf_hsd_batch_size=hf_hsd_batch_size,
            hf_hsd_max_length=hf_hsd_max_length,
            llm_review="off",
            llm_verifier="off",
            disabled_providers=[],
            candidate_selection=True,
            style_scrub=True,
            style_simplify_language=False,
            hsd_token_importance_path=str(paths.importance_csv),
            hsd_token_protect_threshold=token_protect_threshold,
            progress_callback=progress_callback,
        )
    scrubbed_rows, scrubbed_fieldnames = read_csv(paths.scrubbed_csv)
    classification: dict[str, Any] = {
        "status": "provided",
        "label_col": label_col,
        "label_source": "provided",
        "row_count": len(scrubbed_rows),
    }
    if label_col not in scrubbed_fieldnames:
        classification = ensure_hsd_predictions(
            paths.scrubbed_csv,
            paths.prediction_csv,
            text_col=text_col,
            id_col=id_col,
            model_path=hf_hsd_model_path,
            threshold=hf_hsd_threshold,
            device=hf_hsd_device,
            max_length=hf_hsd_max_length,
            batch_size=hf_hsd_batch_size,
            force=force_classification,
            progress_callback=progress_callback,
        )
        classification["label_col"] = label_col
        classification["label_source"] = "predicted"
    restatement_input = build_restatement_input_csv(
        paths.scrubbed_csv,
        paths.restatement_input_csv,
        prediction_csv=paths.prediction_csv,
        text_col=text_col,
        id_col=id_col,
        label_col=label_col,
        force=force_classification or force_restatement,
    )
    restatement = run_llm_restatement_csv(
        Path(str(restatement_input["path"])),
        restated_csv=paths.restated_csv,
        annotated_csv=paths.restatement_annotated_csv,
        cache_path=paths.restatement_cache,
        text_col=text_col,
        id_col=id_col,
        label_col=label_col,
        endpoint=restatement_endpoint,
        model=restatement_model,
        batch_size=restatement_batch_size,
        temperature=restatement_temperature,
        top_p=restatement_top_p,
        max_tokens=restatement_max_tokens,
        timeout_seconds=restatement_timeout_seconds,
        max_retries=restatement_max_retries,
        final_scrub=final_scrub,
        allow_fallback=allow_restatement_fallback,
        force=force_restatement,
        output_fieldnames=list(restatement_input["output_fieldnames"]),
        progress_callback=progress_callback,
    )
    admin_annotations = add_admin_source_columns(
        paths.restatement_annotated_csv,
        input_path,
        text_col=text_col,
        id_col=id_col,
    )
    restatement["admin_annotations"] = admin_annotations
    restatement["annotated_sha256"] = admin_annotations["annotated_sha256"]
    deviation_loaded = (
        paths.deviation_audit_csv.exists()
        and paths.deviation_audit_summary.exists()
        and not force_deviation_audit
    )
    if deviation_loaded:
        deviation_audit = load_json_file(paths.deviation_audit_summary)
    else:
        if progress_callback:
            progress_callback(
                {
                    "stage": "deviation_audit",
                    "processed": 0,
                    "total": 1,
                    "detail": "Auditing source-to-restatement drift.",
                }
            )
        deviation_audit = run_restatement_deviation_audit(
            paths.restatement_annotated_csv,
            paths.deviation_audit_csv,
            summary_path=paths.deviation_audit_summary,
            text_col=SOURCE_TEXT_COL,
            restatement_col="backend_restatement_final",
            id_col=id_col,
            label_col=label_col,
        )
    deviation_audit["summary"] = str(paths.deviation_audit_summary)
    deviation_audit["sha256"] = sha256_file(paths.deviation_audit_csv)
    deviation_audit["status"] = "loaded" if deviation_loaded else "generated"
    if progress_callback:
        progress_callback(
            {
                "stage": "deviation_audit",
                "processed": 1,
                "total": 1,
                "detail": "Audited source-to-restatement drift.",
            }
        )
    validation = validate_submission(
        input_path,
        paths.restated_csv,
        text_cols=[text_col],
        id_col=id_col,
        output_path=paths.validation_json,
    )
    if not validation["valid"]:
        codes = ", ".join(issue["code"] for issue in validation["issues"])
        raise BackendBundleError(f"restated CSV validation failed: {codes}")

    manifest = {
        "artifact_type": "backend_admin_csv_bundle",
        "pipeline": "backend_bundle",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "input": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
        },
        "text_col": text_col,
        "id_col": id_col,
        "label_col": label_col,
        "classification": classification,
        "restatement_input": {
            key: value
            for key, value in restatement_input.items()
            if key != "output_fieldnames"
        },
        "token_importance": token_importance,
        "scrubbed": {
            "csv": str(paths.scrubbed_csv),
            "manifest": str(paths.scrubbed_manifest),
            "audit": str(paths.scrubbed_audit),
            "sha256": sha256_file(paths.scrubbed_csv),
            "status": "loaded" if scrubbed_loaded else "generated",
            "pipeline": scrubbed_manifest.get("pipeline"),
            "validation": scrubbed_manifest.get("validation"),
        },
        "restatement": restatement,
        "deviation_audit": deviation_audit,
        "validation": validation,
        "outputs": {
            "importance_csv": str(paths.importance_csv),
            "prediction_csv": str(paths.prediction_csv),
            "restatement_input_csv": str(paths.restatement_input_csv),
            "scrubbed_csv": str(paths.scrubbed_csv),
            "restated_csv": str(paths.restated_csv),
            "restatement_annotated_csv": str(paths.restatement_annotated_csv),
            "deviation_audit_csv": str(paths.deviation_audit_csv),
            "deviation_audit_summary": str(paths.deviation_audit_summary),
            "manifest": str(paths.manifest),
            "validation_json": str(paths.validation_json),
        },
    }
    write_json(paths.manifest, manifest)
    return manifest
