"""Optional second-pass local LLM verifier for HSD sidecar labels.

The verifier receives cleaned text only. It audits positive labels from the main
local LLM reviewer and writes sidecar metadata; it never rewrites text and never
changes the exact-format CSV.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import time
from typing import Any

from contextsafe_hsd.models.local_llm_hsd_review_runtime import (
    parse_json_object,
    post_chat_completion,
)


REQUEST_FUNCTION_NAME = "record_hsd_verifier"
ALLOWED_VERIFIER_DECISIONS = frozenset({"agree", "disagree", "uncertain"})
ALLOWED_VERIFIER_REASONS = frozenset(
    {
        "protected_identity_attack",
        "no_protected_target",
        "quote_report_or_counterspeech",
        "identity_cue_but_ambiguous",
        "non_identity_profanity",
        "other",
    }
)
PROMPT_STYLES = frozenset({"current", "human_review_router"})

BASE_VERIFIER_PROMPT = (
    "You are a second-pass verifier for an existing positive hate-speech label. "
    "The text has already been privacy-cleaned. Hate speech requires a protected "
    "identity target or identity-coded slur plus abuse, exclusion, dehumanizing "
    "language, threat, inferiority, contempt, or celebration of harm. Disagree "
    "only when the positive label is clearly wrong. Use uncertain when the text "
    "is ambiguous, quoted, reported, context-dependent, or missing enough "
    "information. Return exactly one item for every input row and copy ids "
    "exactly."
)
HUMAN_REVIEW_ROUTER_PROMPT = (
    BASE_VERIFIER_PROMPT
    + " Treat disagreement and uncertainty as human-review routing signals, not "
    "as automatic label changes. Prefer uncertainty over disagreement when a "
    "protected identity cue is present but endorsement is unclear."
)


class LocalLlmHsdVerifierError(ValueError):
    """Raised when verifier output does not satisfy the structured contract."""


@dataclass(frozen=True)
class LocalLlmVerifierRow:
    row_id: str
    decision: str
    suggested_label: bool | None
    reason: str
    parse_status: str
    action: str
    error_class: str | None = None
    error: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "id": self.row_id,
            "decision": self.decision,
            "suggested_label": self.suggested_label,
            "reason": self.reason,
            "parse_status": self.parse_status,
            "action": self.action,
            "error_class": self.error_class,
        }


@dataclass(frozen=True)
class LocalLlmVerifierResult:
    rows: tuple[LocalLlmVerifierRow, ...]
    model_id: str
    endpoint: str
    prompt_style: str
    elapsed_seconds: float
    request_count: int
    fallback_count: int

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def parsed_count(self) -> int:
        return sum(row.parse_status == "ok" for row in self.rows)

    @property
    def skipped_count(self) -> int:
        return self.row_count - self.parsed_count

    @property
    def status(self) -> str:
        if not self.rows:
            return "skipped"
        if self.parsed_count == self.row_count:
            return "ok"
        if self.parsed_count:
            return "partial"
        return "skipped"

    def summary(self) -> dict[str, Any]:
        parsed_rows = [row for row in self.rows if row.parse_status == "ok"]
        decision_counts = Counter(row.decision for row in parsed_rows)
        reason_counts = Counter(row.reason for row in parsed_rows)
        action_counts = Counter(row.action for row in parsed_rows)
        return {
            "backend": "local_llm_verifier",
            "status": self.status,
            "row_count": self.row_count,
            "reviewed_scope": "main_classifier_positive_rows_only",
            "model_id": self.model_id,
            "endpoint": self.endpoint,
            "prompt_style": self.prompt_style,
            "elapsed_seconds": round(self.elapsed_seconds, 4),
            "request_count": self.request_count,
            "parse_count": self.parsed_count,
            "fallback_count": self.fallback_count,
            "skipped_count": self.skipped_count,
            "decision_counts": dict(sorted(decision_counts.items())),
            "reason_counts": dict(sorted(reason_counts.items())),
            "action_counts": dict(sorted(action_counts.items())),
            "human_review_candidate_count": int(
                action_counts.get("human_review_candidate", 0)
            ),
            "label_override_applied": False,
            "approved_use": (
                "optional audit safeguard only; does not change CSV labels or text"
            ),
            "row_reviews": [row.to_metadata() for row in self.rows],
        }


def verifier_payload_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "decision": {
                            "type": "string",
                            "enum": sorted(ALLOWED_VERIFIER_DECISIONS),
                        },
                        "suggested_label": {"type": "boolean"},
                        "reason": {
                            "type": "string",
                            "enum": sorted(ALLOWED_VERIFIER_REASONS),
                        },
                    },
                    "required": [
                        "id",
                        "decision",
                        "suggested_label",
                        "reason",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def extract_verifier_payload(response: Mapping[str, Any]) -> dict[str, Any]:
    try:
        message = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LocalLlmHsdVerifierError("response did not contain a chat message") from exc
    if not isinstance(message, Mapping):
        raise LocalLlmHsdVerifierError("response message was not an object")
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") if isinstance(tool_call, Mapping) else None
        if not isinstance(function, Mapping):
            continue
        name = str(function.get("name", "") or "")
        if name and name != REQUEST_FUNCTION_NAME:
            continue
        return parse_json_object(function.get("arguments"))
    function_call = message.get("function_call")
    if isinstance(function_call, Mapping):
        return parse_json_object(function_call.get("arguments"))
    return parse_json_object(message.get("content"))


def action_for_decision(decision: str, suggested_label: bool | None) -> str:
    if decision == "agree":
        return "none"
    if decision == "disagree" and suggested_label is False:
        return "human_review_candidate"
    if decision == "uncertain":
        return "human_review_candidate"
    return "needs_review"


def normalize_verifier_items(
    payload: Mapping[str, Any],
    *,
    input_rows: list[dict[str, str]],
) -> tuple[LocalLlmVerifierRow, ...]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise LocalLlmHsdVerifierError("verifier payload missing items list")
    input_by_id = {str(row["id"]): row for row in input_rows}
    if len(items) != len(input_by_id):
        raise LocalLlmHsdVerifierError("verifier item count did not match input count")
    seen: set[str] = set()
    reviews: list[LocalLlmVerifierRow] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise LocalLlmHsdVerifierError("verifier item was not an object")
        row_id = str(item.get("id", "") or "")
        if row_id not in input_by_id:
            raise LocalLlmHsdVerifierError("verifier item id did not match input rows")
        if row_id in seen:
            raise LocalLlmHsdVerifierError("verifier item id was duplicated")
        seen.add(row_id)
        decision = str(item.get("decision", "") or "")
        if decision not in ALLOWED_VERIFIER_DECISIONS:
            raise LocalLlmHsdVerifierError("verifier item used unsupported decision")
        suggested_label = item.get("suggested_label")
        if not isinstance(suggested_label, bool):
            raise LocalLlmHsdVerifierError("verifier item suggested_label was not boolean")
        reason = str(item.get("reason", "") or "")
        if reason not in ALLOWED_VERIFIER_REASONS:
            raise LocalLlmHsdVerifierError("verifier item used unsupported reason")
        reviews.append(
            LocalLlmVerifierRow(
                row_id=row_id,
                decision=decision,
                suggested_label=suggested_label,
                reason=reason,
                parse_status="ok",
                action=action_for_decision(decision, suggested_label),
            )
        )
    return tuple(reviews)


def skipped_verifier_row(
    row: Mapping[str, str],
    exc: Exception,
) -> LocalLlmVerifierRow:
    return LocalLlmVerifierRow(
        row_id=str(row.get("id", "") or ""),
        decision="uncertain",
        suggested_label=None,
        reason="other",
        parse_status="skipped",
        action="needs_review",
        error_class=type(exc).__name__,
        error=str(exc),
    )


def prompt_for_style(style: str) -> str:
    normalized = style.strip().lower().replace("-", "_")
    if normalized == "human_review_router":
        return HUMAN_REVIEW_ROUTER_PROMPT
    if normalized == "current":
        return BASE_VERIFIER_PROMPT
    raise LocalLlmHsdVerifierError(
        "verifier prompt_style must be current or human_review_router"
    )


class LocalLlmHsdVerifierRuntime:
    """Audit main positive HSD labels with a local OpenAI-compatible chat model."""

    def __init__(
        self,
        *,
        endpoint: str,
        model_id: str,
        timeout_seconds: float = 120.0,
        prompt_style: str = "current",
        reasoning_effort: str | None = None,
        request_callable: Callable[[Mapping[str, Any], float], dict[str, Any]] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        self.prompt_style = prompt_style.strip().lower().replace("-", "_")
        if self.prompt_style not in PROMPT_STYLES:
            raise LocalLlmHsdVerifierError(
                "verifier prompt_style must be current or human_review_router"
            )
        self.reasoning_effort = reasoning_effort
        self._request_callable = request_callable

    def status_metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "endpoint": self.endpoint,
            "timeout_seconds": self.timeout_seconds,
            "prompt_style": self.prompt_style,
            "reasoning_effort": self.reasoning_effort,
            "approved_use": (
                "optional post-classification audit metadata only; no label overrides"
            ),
        }

    def verify_texts(
        self,
        rows: list[dict[str, str]],
        *,
        batch_size: int,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> LocalLlmVerifierResult:
        started = time.perf_counter()
        all_reviews: list[LocalLlmVerifierRow] = []
        request_count = 0
        fallback_count = 0
        total_rows = len(rows)
        chunk_size = max(1, batch_size)
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "local_llm_verifier",
                    "processed": 0,
                    "total": total_rows,
                    "detail": "Running second-pass HSD verifier on positive labels.",
                }
            )
        for start in range(0, total_rows, chunk_size):
            batch = rows[start : start + chunk_size]
            try:
                reviews = self._verify_batch(batch)
                request_count += 1
                all_reviews.extend(reviews)
            except Exception:
                request_count += 1
                fallback_count += len(batch)
                for row in batch:
                    try:
                        reviews = self._verify_batch([row])
                        request_count += 1
                        all_reviews.extend(reviews)
                    except Exception as row_exc:
                        request_count += 1
                        all_reviews.append(skipped_verifier_row(row, row_exc))
            if progress_callback is not None:
                progress_callback(
                    {
                        "stage": "local_llm_verifier",
                        "processed": min(start + len(batch), total_rows),
                        "total": total_rows,
                        "detail": "Verified positive HSD sidecar labels.",
                        "request_count": request_count,
                        "fallback_count": fallback_count,
                    }
                )
        return LocalLlmVerifierResult(
            rows=tuple(all_reviews),
            model_id=self.model_id,
            endpoint=self.endpoint,
            prompt_style=self.prompt_style,
            elapsed_seconds=time.perf_counter() - started,
            request_count=request_count,
            fallback_count=fallback_count,
        )

    def _verify_batch(self, rows: list[dict[str, str]]) -> tuple[LocalLlmVerifierRow, ...]:
        response = self._post(self._payload(rows))
        payload = extract_verifier_payload(response)
        return normalize_verifier_items(payload, input_rows=rows)

    def _post(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if self._request_callable is not None:
            return self._request_callable(payload, self.timeout_seconds)
        return post_chat_completion(
            endpoint=self.endpoint,
            payload=payload,
            timeout=self.timeout_seconds,
        )

    def _payload(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": prompt_for_style(self.prompt_style),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "items": [
                                {
                                    "id": str(row.get("id", "") or ""),
                                    "text": str(row.get("text", "") or ""),
                                    "main_label": True,
                                }
                                for row in rows
                            ],
                            "allowed_decisions": sorted(ALLOWED_VERIFIER_DECISIONS),
                            "allowed_reasons": sorted(ALLOWED_VERIFIER_REASONS),
                            "decision_rule": (
                                "agree means the positive label is reasonable; "
                                "disagree means clearly not hate speech; uncertain "
                                "means route for human review."
                            ),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": REQUEST_FUNCTION_NAME,
                        "description": (
                            "Record second-pass HSD verifier decisions for rows."
                        ),
                        "parameters": verifier_payload_schema(),
                    },
                }
            ],
            "tool_choice": "required",
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        return payload


__all__ = [
    "ALLOWED_VERIFIER_DECISIONS",
    "ALLOWED_VERIFIER_REASONS",
    "LocalLlmHsdVerifierError",
    "LocalLlmHsdVerifierRuntime",
    "LocalLlmVerifierResult",
    "LocalLlmVerifierRow",
    "normalize_verifier_items",
    "verifier_payload_schema",
]
