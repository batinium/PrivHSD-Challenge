"""Structured local LLM HSD review runtime.

The runtime only receives post-cleaning text. It classifies hate/not-hate and
records residual PII suggestions as review metadata; it never rewrites or masks
text.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
import re
import time
from typing import Any
from urllib import error, request

from contextsafe_hsd.detectors import TARGET_GROUP_TERMS, target_group_spans
from contextsafe_hsd.metrics import UTILITY_CUES
from contextsafe_hsd.resource_config import load_utility_cue_terms


ALLOWED_HSD_REASON_TAGS = frozenset(
    {
        "protected_target",
        "identity_attack",
        "dehumanization",
        "threat",
        "exclusion",
        "inferiority_claim",
        "quote_or_report",
        "counterspeech",
        "ambiguous_context",
        "none",
    }
)
PLACEHOLDER_PATTERN = re.compile(
    r"^\s*(?:"
    r"\[[A-Z][A-Z0-9_:-]*\]"
    r"|<[A-Z][A-Z0-9_:-]*>"
    r"|(?:PERSON|NAME|EMAIL|PHONE|ADDRESS|LOCATION|ORG|ORGANIZATION|USER|"
    r"USERNAME|HANDLE|URL|IP|IDENTIFIER|ID|DATE)"
    r")\s*$",
    re.I,
)
WORD_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)
SENTENCE_END_PATTERN = re.compile(r"[.!?][\"')\]]?\s*$")
TOO_BROAD_WORD_LIMIT = 12
TOO_BROAD_CHAR_LIMIT = 120
REQUEST_FUNCTION_NAME = "record_hsd_review"
LOCAL_LLM_HSD_SYSTEM_PROMPT = (
    "Classify cleaned text for a hate-speech dataset. Hate speech means the text "
    "itself endorses, advocates, commands, or asserts abuse, inferiority, "
    "exclusion, dehumanization, or violence against a protected identity group. "
    "Return hate=false for quotations, reports, moderation requests, "
    "condemnation, counterspeech, negation, hypotheticals, questions, or "
    "examples that mention hateful words without endorsing them. Offensive "
    "profanity without a protected target is not HSD. Return binary labels, "
    "allowed reason tags, exact residual PII substrings only, and no confidence "
    "or explanation."
)


class LocalLlmHsdReviewError(ValueError):
    """Raised when the local LLM response cannot satisfy the review contract."""


@dataclass(frozen=True)
class SuggestionRecord:
    text: str
    text_hash: str
    start: int | None
    end: int | None
    validator_status: str
    rejection_reasons: tuple[str, ...]
    source: str
    model_id: str

    def to_metadata(self, *, include_text: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "text_hash": self.text_hash,
            "start": self.start,
            "end": self.end,
            "validator_status": self.validator_status,
            "rejection_reasons": list(self.rejection_reasons),
            "source": self.source,
            "model_id": self.model_id,
        }
        if include_text:
            data["text"] = self.text
        return data


@dataclass(frozen=True)
class LocalLlmRowReview:
    row_id: str
    label: str
    hate: bool | None
    hsd_reasons: tuple[str, ...]
    review_needed: bool
    pii_suggestions: tuple[SuggestionRecord, ...]
    parse_status: str
    error_class: str | None = None
    error: str | None = None

    def to_metadata(self, *, include_suggestion_text: bool = False) -> dict[str, Any]:
        suggestion_counts = Counter(
            suggestion.validator_status for suggestion in self.pii_suggestions
        )
        return {
            "id": self.row_id,
            "label": self.label,
            "hate": self.hate,
            "hsd_reasons": list(self.hsd_reasons),
            "review_needed": self.review_needed,
            "parse_status": self.parse_status,
            "error_class": self.error_class,
            "pii_suggestion_count": len(self.pii_suggestions),
            "accepted_pii_suggestion_count": int(
                suggestion_counts.get("accepted_for_review", 0)
            ),
            "pii_suggestion_status_counts": dict(sorted(suggestion_counts.items())),
            "pii_suggestions": [
                suggestion.to_metadata(include_text=include_suggestion_text)
                for suggestion in self.pii_suggestions
            ],
        }


@dataclass(frozen=True)
class LocalLlmReviewResult:
    rows: tuple[LocalLlmRowReview, ...]
    model_id: str
    endpoint: str
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

    def by_id(self) -> dict[str, LocalLlmRowReview]:
        return {row.row_id: row for row in self.rows}

    def summary(self, *, include_suggestion_text: bool = False) -> dict[str, Any]:
        prediction_counts = Counter(
            row.label for row in self.rows if row.parse_status == "ok"
        )
        reason_counts: Counter[str] = Counter()
        suggestion_counts: Counter[str] = Counter()
        for row in self.rows:
            if row.parse_status == "ok":
                reason_counts.update(row.hsd_reasons)
            suggestion_counts.update(
                suggestion.validator_status for suggestion in row.pii_suggestions
            )
        return {
            "backend": "local_llm",
            "status": self.status,
            "row_count": self.row_count,
            "model_id": self.model_id,
            "endpoint": self.endpoint,
            "elapsed_seconds": round(self.elapsed_seconds, 4),
            "request_count": self.request_count,
            "parse_count": self.parsed_count,
            "fallback_count": self.fallback_count,
            "skipped_count": self.skipped_count,
            "prediction_counts": dict(sorted(prediction_counts.items())),
            "reason_tag_counts": dict(sorted(reason_counts.items())),
            "pii_suggestion_status_counts": dict(sorted(suggestion_counts.items())),
            "row_reviews": [
                row.to_metadata(include_suggestion_text=include_suggestion_text)
                for row in self.rows
            ],
        }


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalized_phrase(value: str) -> str:
    return " ".join(value.strip().lower().split())


def phrase_terms() -> frozenset[str]:
    terms = {normalized_phrase(cue) for cue in UTILITY_CUES}
    for section in (
        "action_terms",
        "negation_modality_terms",
        "target_generalization_context",
    ):
        terms.update(normalized_phrase(term) for term in load_utility_cue_terms(section))
    for category_terms in TARGET_GROUP_TERMS.values():
        terms.update(normalized_phrase(term) for term in category_terms)
    return frozenset(term for term in terms if term)


PROTECTED_OR_HSD_TERMS = phrase_terms()


def contains_protected_or_hsd_cue(value: str) -> bool:
    phrase = normalized_phrase(value)
    if not phrase:
        return False
    if phrase in PROTECTED_OR_HSD_TERMS:
        return True
    words = set(WORD_PATTERN.findall(phrase))
    for term in PROTECTED_OR_HSD_TERMS:
        if not term:
            continue
        if " " in term:
            pattern = r"(?<![^\W_])" + re.escape(term) + r"(?![^\W_])"
            if re.search(pattern, phrase, flags=re.I):
                return True
            continue
        if term in words:
            return True
    return False


def protected_target_overlap(cleaned_text: str, start: int, end: int) -> bool:
    return any(start < span.end and end > span.start for span in target_group_spans(cleaned_text))


def looks_too_broad(suggestion: str, cleaned_text: str) -> bool:
    stripped = suggestion.strip()
    if not stripped:
        return False
    if stripped == cleaned_text.strip():
        return True
    words = WORD_PATTERN.findall(stripped)
    if len(words) > TOO_BROAD_WORD_LIMIT:
        return True
    if len(stripped) > min(TOO_BROAD_CHAR_LIMIT, max(40, int(len(cleaned_text) * 0.45))):
        return True
    return len(words) >= 6 and bool(SENTENCE_END_PATTERN.search(stripped))


def validate_pii_suggestions(
    cleaned_text: str,
    suggestions: Iterable[Any],
    *,
    model_id: str,
) -> tuple[SuggestionRecord, ...]:
    records: list[SuggestionRecord] = []
    seen: set[str] = set()
    for raw_suggestion in suggestions:
        suggestion = str(raw_suggestion or "").strip()
        start = cleaned_text.find(suggestion) if suggestion else -1
        end = start + len(suggestion) if start >= 0 else -1
        reasons: list[str] = []
        if not suggestion:
            reasons.append("rejected_empty")
        if suggestion and normalized_phrase(suggestion) in seen:
            reasons.append("rejected_duplicate")
        if suggestion and start < 0:
            reasons.append("rejected_not_substring")
        if suggestion and PLACEHOLDER_PATTERN.fullmatch(suggestion):
            reasons.append("rejected_placeholder")
        if suggestion and contains_protected_or_hsd_cue(suggestion):
            reasons.append("rejected_protected_or_hsd_cue")
        if suggestion and start >= 0 and protected_target_overlap(cleaned_text, start, end):
            reasons.append("rejected_protected_or_hsd_cue")
        if suggestion and looks_too_broad(suggestion, cleaned_text):
            reasons.append("rejected_too_broad")
        if reasons:
            status = reasons[0]
        else:
            status = "accepted_for_review"
        if suggestion and "rejected_duplicate" not in reasons:
            seen.add(normalized_phrase(suggestion))
        records.append(
            SuggestionRecord(
                text=suggestion,
                text_hash=sha256_text(suggestion),
                start=start if start >= 0 else None,
                end=end if start >= 0 else None,
                validator_status=status,
                rejection_reasons=tuple(dict.fromkeys(reasons)),
                source="local_llm",
                model_id=model_id,
            )
        )
    return tuple(records)


def post_chat_completion(
    *,
    endpoint: str,
    payload: Mapping[str, Any],
    timeout: float,
) -> dict[str, Any]:
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
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LocalLlmHsdReviewError(
            f"local LLM request failed with HTTP {exc.code}: {detail or exc.reason}"
        ) from exc
    except (OSError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LocalLlmHsdReviewError(f"local LLM request failed: {exc}") from exc


def review_payload_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "hate": {"type": "boolean"},
                        "hsd_reasons": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": sorted(ALLOWED_HSD_REASON_TAGS),
                            },
                        },
                        "pii_leftover": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "review_needed": {"type": "boolean"},
                    },
                    "required": [
                        "id",
                        "hate",
                        "hsd_reasons",
                        "pii_leftover",
                        "review_needed",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise LocalLlmHsdReviewError("response payload was not a JSON object")
    stripped = value.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for start, character in enumerate(stripped):
            if character != "{":
                continue
            try:
                parsed, _offset = decoder.raw_decode(stripped[start:])
            except json.JSONDecodeError:
                continue
            break
        else:
            raise LocalLlmHsdReviewError("response content was not valid JSON")
    if not isinstance(parsed, dict):
        raise LocalLlmHsdReviewError("response content was not a JSON object")
    return parsed


def extract_review_payload(response: Mapping[str, Any]) -> dict[str, Any]:
    try:
        message = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LocalLlmHsdReviewError("response did not contain a chat message") from exc
    if not isinstance(message, Mapping):
        raise LocalLlmHsdReviewError("response message was not an object")
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


def normalize_response_items(
    payload: Mapping[str, Any],
    *,
    input_rows: list[dict[str, str]],
    model_id: str,
    enable_pii_suggestions: bool,
) -> tuple[LocalLlmRowReview, ...]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise LocalLlmHsdReviewError("review payload missing items list")
    input_by_id = {str(row["id"]): row for row in input_rows}
    if len(items) != len(input_by_id):
        raise LocalLlmHsdReviewError("review item count did not match input count")
    seen: set[str] = set()
    reviews: list[LocalLlmRowReview] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise LocalLlmHsdReviewError("review item was not an object")
        row_id = str(item.get("id", "") or "")
        if row_id not in input_by_id:
            raise LocalLlmHsdReviewError("review item id did not match input rows")
        if row_id in seen:
            raise LocalLlmHsdReviewError("review item id was duplicated")
        seen.add(row_id)
        hate = item.get("hate")
        if not isinstance(hate, bool):
            raise LocalLlmHsdReviewError("review item hate field was not boolean")
        reasons_raw = item.get("hsd_reasons")
        if not isinstance(reasons_raw, list) or not reasons_raw:
            raise LocalLlmHsdReviewError("review item missing hsd_reasons")
        reasons = tuple(str(reason) for reason in reasons_raw)
        if any(reason not in ALLOWED_HSD_REASON_TAGS for reason in reasons):
            raise LocalLlmHsdReviewError("review item used an unsupported hsd reason")
        pii_raw = item.get("pii_leftover") or []
        if not isinstance(pii_raw, list):
            raise LocalLlmHsdReviewError("review item pii_leftover was not a list")
        suggestions = (
            validate_pii_suggestions(
                str(input_by_id[row_id].get("text", "") or ""),
                pii_raw,
                model_id=model_id,
            )
            if enable_pii_suggestions
            else ()
        )
        reviews.append(
            LocalLlmRowReview(
                row_id=row_id,
                label="1" if hate else "0",
                hate=hate,
                hsd_reasons=reasons,
                review_needed=bool(item.get("review_needed", hate)),
                pii_suggestions=suggestions,
                parse_status="ok",
            )
        )
    return tuple(reviews)


def skipped_review(row: Mapping[str, str], exc: Exception) -> LocalLlmRowReview:
    return LocalLlmRowReview(
        row_id=str(row.get("id", "") or ""),
        label="",
        hate=None,
        hsd_reasons=(),
        review_needed=True,
        pii_suggestions=(),
        parse_status="skipped",
        error_class=type(exc).__name__,
        error=str(exc),
    )


class LocalLlmHsdReviewRuntime:
    """Review cleaned rows with a local OpenAI-compatible chat model."""

    def __init__(
        self,
        *,
        endpoint: str,
        model_id: str,
        timeout_seconds: float = 120.0,
        enable_pii_suggestions: bool = True,
        require_structured_output: bool = True,
        request_callable: Callable[[Mapping[str, Any], float], dict[str, Any]] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        self.enable_pii_suggestions = enable_pii_suggestions
        self.require_structured_output = require_structured_output
        self._request_callable = request_callable

    def status_metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "endpoint": self.endpoint,
            "timeout_seconds": self.timeout_seconds,
            "pii_suggestions_enabled": self.enable_pii_suggestions,
            "require_structured_output": self.require_structured_output,
            "approved_use": "post-cleaning HSD classification and review metadata only",
        }

    def review_texts(
        self,
        rows: list[dict[str, str]],
        *,
        batch_size: int,
    ) -> LocalLlmReviewResult:
        started = time.perf_counter()
        all_reviews: list[LocalLlmRowReview] = []
        request_count = 0
        fallback_count = 0
        for start in range(0, len(rows), max(1, batch_size)):
            batch = rows[start : start + max(1, batch_size)]
            try:
                reviews = self._review_batch(batch)
                request_count += 1
                all_reviews.extend(reviews)
            except Exception:
                request_count += 1
                fallback_count += len(batch)
                for row in batch:
                    try:
                        reviews = self._review_batch([row])
                        request_count += 1
                        all_reviews.extend(reviews)
                    except Exception as row_exc:
                        request_count += 1
                        all_reviews.append(skipped_review(row, row_exc))
        return LocalLlmReviewResult(
            rows=tuple(all_reviews),
            model_id=self.model_id,
            endpoint=self.endpoint,
            elapsed_seconds=time.perf_counter() - started,
            request_count=request_count,
            fallback_count=fallback_count,
        )

    def _review_batch(self, rows: list[dict[str, str]]) -> tuple[LocalLlmRowReview, ...]:
        response = self._post(self._payload(rows, with_tools=True))
        try:
            payload = extract_review_payload(response)
            return normalize_response_items(
                payload,
                input_rows=rows,
                model_id=self.model_id,
                enable_pii_suggestions=self.enable_pii_suggestions,
            )
        except LocalLlmHsdReviewError:
            if self.require_structured_output:
                raise
        response = self._post(self._payload(rows, with_tools=False))
        payload = extract_review_payload(response)
        return normalize_response_items(
            payload,
            input_rows=rows,
            model_id=self.model_id,
            enable_pii_suggestions=self.enable_pii_suggestions,
        )

    def _post(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if self._request_callable is not None:
            return self._request_callable(payload, self.timeout_seconds)
        return post_chat_completion(
            endpoint=self.endpoint,
            payload=payload,
            timeout=self.timeout_seconds,
        )

    def _payload(self, rows: list[dict[str, str]], *, with_tools: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": LOCAL_LLM_HSD_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "items": [
                                {
                                    "id": str(row.get("id", "") or ""),
                                    "text": str(row.get("text", "") or ""),
                                }
                                for row in rows
                            ],
                            "allowed_hsd_reasons": sorted(ALLOWED_HSD_REASON_TAGS),
                            "pii_leftover_rule": (
                                "Only exact substrings from the cleaned text."
                            ),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0,
        }
        if not with_tools:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "hsd_review",
                    "strict": True,
                    "schema": review_payload_schema(),
                },
            }
            return payload
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": REQUEST_FUNCTION_NAME,
                    "description": (
                        "Record structured HSD review items for cleaned rows."
                    ),
                    "parameters": review_payload_schema(),
                },
            }
        ]
        payload["tool_choice"] = "required"
        return payload


__all__ = [
    "ALLOWED_HSD_REASON_TAGS",
    "LOCAL_LLM_HSD_SYSTEM_PROMPT",
    "LocalLlmHsdReviewError",
    "LocalLlmHsdReviewRuntime",
    "LocalLlmReviewResult",
    "LocalLlmRowReview",
    "SuggestionRecord",
    "validate_pii_suggestions",
]
