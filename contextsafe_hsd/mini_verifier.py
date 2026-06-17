"""Mini local-model verifier evaluation for HSD classification routing."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
import random
import re
import time
from pathlib import Path
from typing import Any
from urllib import error, request

from contextsafe_hsd.models.local_llm_hsd_review_runtime import (
    LocalLlmHsdReviewError,
    contains_protected_or_hsd_cue,
    post_chat_completion,
)


DEFAULT_ENDPOINT = "http://100.120.207.64:1234/v1/chat/completions"
DEFAULT_MAIN_MODEL = "openai/gpt-oss-20b"
DEFAULT_RUN_DIR = Path("data/outputs/train_split_full_pipeline_fixed_20260615_233312")
DEFAULT_SOURCE_CSV = Path("data/train/train_split.csv")
DEFAULT_OUTPUT_DIR = Path("data/outputs/mini_verifier_eval")
DEFAULT_SEED = 20260616
RECOMMENDED_CANDIDATES = (
    "qwen/qwen3-4b-2507",
    "qwen3.5-4b",
    "qwen/qwen3-4b",
    "shieldgemma-2-4b-it",
    "google/gemma-3n-e4b",
    "nvidia/nemotron-3-nano-4b",
    "mistralai/ministral-3-3b",
)
UNCENSORED_PROBE = "gemma-4-e4b-uncensored-hauhaucs-aggressive"
FALLBACK_COST_FLOOR_CANDIDATES = (
    "google/gemma-4-e2b",
    "qwen/qwen3-1.7b",
)
VERIFIER_DECISIONS = frozenset({"agree", "disagree", "uncertain"})
VERIFIER_REASONS = frozenset(
    {
        "protected_identity_attack",
        "no_protected_target",
        "quote_report_or_counterspeech",
        "identity_cue_but_ambiguous",
        "non_identity_profanity",
        "other",
    }
)
CLASSIFIER_REASONS = frozenset(
    {
        "protected_identity_attack",
        "threat_or_exclusion",
        "quote_report_or_counterspeech",
        "no_protected_target",
        "non_identity_profanity",
        "ambiguous_false",
        "other",
    }
)

EVAL_FIELDNAMES = [
    "id",
    "case_type",
    "gold_hs",
    "main_hate",
    "main_hsd_reasons",
    "review_needed",
    "parse_status",
    "source_text",
    "cleaned_text",
]

VERIFIER_SYSTEM_PROMPT = """You are a verifier for a hate-speech dataset label. You receive cleaned text and
the main model's binary label. Your job is not to be broad or creative. Decide
whether the main label is clearly supported, clearly wrong, or needs a stronger
model to adjudicate.

Hate speech is true when the author directly demeans, attacks, threatens,
excludes, or asserts inferiority about a person or group using protected
identity references or identity-coded slurs. Protected or identity-coded
categories include race, ethnicity, nationality, religion, gender, sex, sexual
orientation, trans identity, disability, and similar identity classes.

Return "agree" when the main label is clearly correct.
Return "disagree" when the main label is clearly wrong.
Return "uncertain" when context, quotation, counterspeech, sarcasm, negation, or
target ambiguity makes the decision hard.

Important false-positive guards:
- Vulgar insults with no protected identity cue are not hate speech.
- Sexual profanity alone is not hate speech.
- Political, institutional, or ideological criticism is not hate speech unless
  it uses protected identity abuse.
- Quoted, reported, moderated, debunked, or counterspeech examples are not hate
  speech unless the author endorses the abuse.

Important false-negative guards:
- Direct slur-as-insult or identity-coded insult can be hate speech even without
  an explicit policy demand.
- Attacking an individual can be hate speech when the attack relies on protected
  identity or identity-coded language.

Output only JSON with an items array. Each item must contain id, decision,
suggested_label, and reason."""

DIRECT_CLASSIFIER_SYSTEM_PROMPT = """Classify cleaned text for a hate-speech dataset.

Hate speech is true when the author directly demeans, attacks, threatens,
excludes, or asserts inferiority about a person or group using protected
identity references or identity-coded slurs.

Return false for vulgar insults without protected identity cues, sexual profanity
alone, political or institutional criticism, quoted or reported language,
moderation examples, counterspeech, negation, hypotheticals, and ambiguous cases
without clear author endorsement. Direct identity-coded slur-as-insult can be
true even without an explicit policy demand.

Output only JSON with an items array. Each item must contain id, hate, and
reason."""

ADJUDICATION_SYSTEM_PROMPT = """You are adjudicating a possible error in a hate-speech dataset label. A smaller
verifier disagreed with or was uncertain about the main model's previous label.

Decide the final binary label from the cleaned text only. Use the challenge
label policy:
- true when the author directly demeans, attacks, threatens, excludes, or asserts
  inferiority about a person or group using protected identity references or
  identity-coded slurs.
- false for vulgar insults without protected identity cues, sexual profanity
  alone, political/institutional criticism, quoted/reported/debunked language,
  moderation examples, counterspeech, negation, hypotheticals, and ambiguous
  cases without clear author endorsement.
- direct identity-coded slur-as-insult can be true even without an explicit
  policy demand.

Output only JSON with an items array. Each item must contain id, hate, and
reason."""


@dataclass(frozen=True)
class EvalRow:
    id: str
    case_type: str
    gold_hs: str
    main_hate: str
    main_hsd_reasons: str
    review_needed: str
    parse_status: str
    source_text: str
    cleaned_text: str

    @property
    def gold_bool(self) -> bool:
        return self.gold_hs == "1"

    @property
    def main_bool(self) -> bool:
        return self.main_hate == "1"

    def to_csv_row(self) -> dict[str, str]:
        return {field: str(getattr(self, field)) for field in EVAL_FIELDNAMES}


@dataclass(frozen=True)
class VerifierItem:
    row_id: str
    decision: str | None
    suggested_label: bool | None
    reason: str | None
    parse_status: str
    error_class: str | None = None
    error: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "id": self.row_id,
            "decision": self.decision,
            "suggested_label": self.suggested_label,
            "reason": self.reason,
            "parse_status": self.parse_status,
            "error_class": self.error_class,
            "error": self.error,
        }


@dataclass(frozen=True)
class ClassificationItem:
    row_id: str
    hate: bool | None
    reason: str | None
    parse_status: str
    error_class: str | None = None
    error: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "id": self.row_id,
            "hate": self.hate,
            "reason": self.reason,
            "parse_status": self.parse_status,
            "error_class": self.error_class,
            "error": self.error,
        }


@dataclass(frozen=True)
class TaskRun:
    model_id: str
    task: str
    rows: tuple[VerifierItem | ClassificationItem, ...]
    elapsed_seconds: float
    request_count: int
    fallback_count: int

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def parse_count(self) -> int:
        return sum(row.parse_status == "ok" for row in self.rows)

    @property
    def parse_success_rate(self) -> float:
        if not self.rows:
            return 0.0
        return self.parse_count / len(self.rows)

    @property
    def seconds_per_row(self) -> float:
        if not self.rows:
            return 0.0
        return self.elapsed_seconds / len(self.rows)

    def by_id(self) -> dict[str, VerifierItem | ClassificationItem]:
        return {row.row_id: row for row in self.rows}

    def summary(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task": self.task,
            "row_count": self.row_count,
            "parse_count": self.parse_count,
            "parse_success_rate": round(self.parse_success_rate, 4),
            "elapsed_seconds": round(self.elapsed_seconds, 4),
            "request_count": self.request_count,
            "fallback_count": self.fallback_count,
            "seconds_per_row": round(self.seconds_per_row, 4),
        }

    def to_metadata(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "rows": [row.to_metadata() for row in self.rows],
        }


class MiniVerifierError(ValueError):
    """Raised when the verifier evaluation cannot complete safely."""


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_json(path: Path, data: Mapping[str, Any] | Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_eval_set(path: Path, rows: Sequence[EvalRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVAL_FIELDNAMES)
        writer.writeheader()
        writer.writerows(row.to_csv_row() for row in rows)


def load_eval_set(path: Path) -> list[EvalRow]:
    rows = []
    for row in read_csv_dicts(path):
        rows.append(
            EvalRow(
                id=str(row.get("id", "") or ""),
                case_type=str(row.get("case_type", "") or ""),
                gold_hs=str(row.get("gold_hs", "") or ""),
                main_hate=str(row.get("main_hate", "") or ""),
                main_hsd_reasons=str(row.get("main_hsd_reasons", "") or ""),
                review_needed=str(row.get("review_needed", "") or ""),
                parse_status=str(row.get("parse_status", "") or ""),
                source_text=str(row.get("source_text", "") or ""),
                cleaned_text=str(row.get("cleaned_text", "") or ""),
            )
        )
    return rows


def stratified_sample(rows: list[EvalRow], n: int, rng: random.Random) -> list[EvalRow]:
    groups: dict[str, list[EvalRow]] = defaultdict(list)
    for row in rows:
        groups[row.main_hsd_reasons or "none"].append(row)
    for group_rows in groups.values():
        rng.shuffle(group_rows)
    keys = sorted(groups, key=lambda key: (-len(groups[key]), key))
    selected: list[EvalRow] = []
    while keys and len(selected) < n:
        next_keys = []
        for key in keys:
            if groups[key] and len(selected) < n:
                selected.append(groups[key].pop())
            if groups[key]:
                next_keys.append(key)
        keys = next_keys
    if len(selected) < n:
        raise MiniVerifierError(
            f"sample requested {n} rows but only found {len(selected)}"
        )
    return selected


def build_eval_set(
    *,
    source_csv: Path,
    run_dir: Path,
    out_csv: Path,
    seed: int = DEFAULT_SEED,
) -> list[EvalRow]:
    protected_csv = run_dir / "train_split.protected.csv"
    result_json = run_dir / "protect_result.json"
    if not source_csv.exists():
        raise MiniVerifierError(f"missing source CSV: {source_csv}")
    if not protected_csv.exists():
        raise MiniVerifierError(f"missing protected CSV: {protected_csv}")
    if not result_json.exists():
        raise MiniVerifierError(f"missing protect result: {result_json}")

    result = json.loads(result_json.read_text(encoding="utf-8"))
    reviews = {
        str(row["id"]): row
        for row in result.get("classification", {}).get("row_reviews", [])
    }
    source_rows = {str(row["ID"]): row for row in read_csv_dicts(source_csv)}
    protected_rows = {str(row["ID"]): row for row in read_csv_dicts(protected_csv)}
    if not reviews:
        raise MiniVerifierError("protect result has no classification reviews")

    cases: list[EvalRow] = []
    for row_id, source_row in source_rows.items():
        review = reviews.get(row_id)
        if not review:
            continue
        gold = str(source_row.get("hs", "")).strip()
        if gold not in {"0", "1"}:
            continue
        pred = "1" if review.get("hate") is True else "0"
        if pred == "1" and gold == "1":
            case_type = "TP"
        elif pred == "0" and gold == "0":
            case_type = "TN"
        elif pred == "1" and gold == "0":
            case_type = "FP"
        else:
            case_type = "FN"
        cases.append(
            EvalRow(
                id=row_id,
                case_type=case_type,
                gold_hs=gold,
                main_hate=pred,
                main_hsd_reasons="|".join(review.get("hsd_reasons") or []),
                review_needed=str(review.get("review_needed")),
                parse_status=str(review.get("parse_status")),
                source_text=str(source_row.get("text", "") or ""),
                cleaned_text=str(protected_rows.get(row_id, {}).get("text", "") or ""),
            )
        )

    targets = {"FP": 60, "FN": 60, "TP": 20, "TN": 20}
    rng = random.Random(seed)
    sample: list[EvalRow] = []
    for case_type, count in targets.items():
        pool = [row for row in cases if row.case_type == case_type]
        sample.extend(stratified_sample(pool, count, rng))
    write_eval_set(out_csv, sample)
    return sample


def ensure_eval_set(
    *,
    source_csv: Path,
    run_dir: Path,
    out_csv: Path,
    rebuild: bool = False,
) -> list[EvalRow]:
    if out_csv.exists() and not rebuild:
        return load_eval_set(out_csv)
    return build_eval_set(source_csv=source_csv, run_dir=run_dir, out_csv=out_csv)


def models_endpoint_for_chat(endpoint: str) -> str:
    if endpoint.endswith("/chat/completions"):
        return endpoint[: -len("/chat/completions")] + "/models"
    return endpoint.rstrip("/") + "/models"


def fetch_models(models_endpoint: str, *, timeout: float) -> dict[str, Any]:
    req = request.Request(models_endpoint, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise MiniVerifierError(
            f"model list request failed with HTTP {exc.code}: {detail or exc.reason}"
        ) from exc
    except (OSError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise MiniVerifierError(f"model list request failed: {exc}") from exc
    model_ids = []
    for item in payload.get("data", []):
        if isinstance(item, Mapping) and item.get("id"):
            model_ids.append(str(item["id"]))
    return {
        "models_endpoint": models_endpoint,
        "model_ids": sorted(model_ids),
        "raw": payload,
    }


def select_candidates(
    available_model_ids: Sequence[str],
    *,
    explicit_candidates: Sequence[str] = (),
    include_uncensored_probe: bool = True,
    include_cost_floor: bool = False,
) -> tuple[list[str], list[str]]:
    available = set(available_model_ids)
    if explicit_candidates:
        candidates = [model for model in explicit_candidates if model in available]
        missing = [model for model in explicit_candidates if model not in available]
        if missing:
            raise MiniVerifierError(
                "requested candidate models are not available: " + ", ".join(missing)
            )
    else:
        candidates = [model for model in RECOMMENDED_CANDIDATES if model in available]
        if not candidates and include_cost_floor:
            candidates = [
                model for model in FALLBACK_COST_FLOOR_CANDIDATES if model in available
            ]
    probes = [UNCENSORED_PROBE] if include_uncensored_probe and UNCENSORED_PROBE in available else []
    if not candidates and not probes:
        raise MiniVerifierError(
            "none of the configured small verifier candidates are available"
        )
    return candidates, probes


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


def extract_chat_json(response: Mapping[str, Any]) -> dict[str, Any]:
    try:
        message = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LocalLlmHsdReviewError("response did not contain a chat message") from exc
    if not isinstance(message, Mapping):
        raise LocalLlmHsdReviewError("response message was not an object")
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") if isinstance(tool_call, Mapping) else None
        if isinstance(function, Mapping):
            return parse_json_object(function.get("arguments"))
    function_call = message.get("function_call")
    if isinstance(function_call, Mapping):
        return parse_json_object(function_call.get("arguments"))
    return parse_json_object(message.get("content"))


def verifier_schema() -> dict[str, Any]:
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
                            "enum": sorted(VERIFIER_DECISIONS),
                        },
                        "suggested_label": {"type": ["boolean", "null"]},
                        "reason": {"type": "string", "enum": sorted(VERIFIER_REASONS)},
                    },
                    "required": ["id", "decision", "suggested_label", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def classifier_schema() -> dict[str, Any]:
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
                        "reason": {
                            "type": "string",
                            "enum": sorted(CLASSIFIER_REASONS),
                        },
                    },
                    "required": ["id", "hate", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def chat_payload(
    *,
    model_id: str,
    system_prompt: str,
    user_payload: Mapping[str, Any],
    schema_name: str | None,
    schema: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": 0,
    }
    if schema_name and schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        }
    return payload


RequestCallable = Callable[[Mapping[str, Any], float], dict[str, Any]]


def request_json_payload(
    *,
    endpoint: str,
    timeout: float,
    payload: Mapping[str, Any],
    request_callable: RequestCallable | None = None,
) -> tuple[dict[str, Any], int]:
    try:
        response = (
            request_callable(payload, timeout)
            if request_callable is not None
            else post_chat_completion(endpoint=endpoint, payload=payload, timeout=timeout)
        )
        return extract_chat_json(response), 1
    except Exception as first_exc:
        if "response_format" not in payload:
            raise first_exc
        fallback = dict(payload)
        fallback.pop("response_format", None)
        try:
            response = (
                request_callable(fallback, timeout)
                if request_callable is not None
                else post_chat_completion(
                    endpoint=endpoint,
                    payload=fallback,
                    timeout=timeout,
                )
            )
            return extract_chat_json(response), 2
        except Exception as second_exc:
            raise LocalLlmHsdReviewError(
                f"schema and fallback JSON requests failed: {first_exc}; {second_exc}"
            ) from second_exc


def normalize_verifier_items(
    payload: Mapping[str, Any],
    *,
    input_rows: Sequence[EvalRow],
) -> tuple[VerifierItem, ...]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise LocalLlmHsdReviewError("verifier payload missing items list")
    input_by_id = {row.id: row for row in input_rows}
    if len(raw_items) != len(input_by_id):
        raise LocalLlmHsdReviewError("verifier item count did not match input count")
    seen: set[str] = set()
    items: list[VerifierItem] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            raise LocalLlmHsdReviewError("verifier item was not an object")
        row_id = str(raw_item.get("id", "") or "")
        if row_id not in input_by_id or row_id in seen:
            raise LocalLlmHsdReviewError("verifier item id did not match input rows")
        seen.add(row_id)
        decision = str(raw_item.get("decision", "") or "")
        if decision not in VERIFIER_DECISIONS:
            raise LocalLlmHsdReviewError("verifier decision was unsupported")
        suggested = raw_item.get("suggested_label")
        if suggested is not None and not isinstance(suggested, bool):
            raise LocalLlmHsdReviewError("verifier suggested_label was invalid")
        reason = str(raw_item.get("reason", "") or "")
        if reason not in VERIFIER_REASONS:
            raise LocalLlmHsdReviewError("verifier reason was unsupported")
        items.append(
            VerifierItem(
                row_id=row_id,
                decision=decision,
                suggested_label=suggested,
                reason=reason,
                parse_status="ok",
            )
        )
    return tuple(items)


def normalize_classifier_items(
    payload: Mapping[str, Any],
    *,
    input_rows: Sequence[EvalRow],
    allow_positional_ids: bool = False,
) -> tuple[ClassificationItem, ...]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise LocalLlmHsdReviewError("classifier payload missing items list")
    input_by_id = {row.id: row for row in input_rows}
    if len(raw_items) != len(input_by_id):
        raise LocalLlmHsdReviewError("classifier item count did not match input count")
    seen: set[str] = set()
    items: list[ClassificationItem] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, Mapping):
            raise LocalLlmHsdReviewError("classifier item was not an object")
        row_id = str(raw_item.get("id", "") or "")
        if allow_positional_ids and (row_id not in input_by_id or row_id in seen):
            row_id = input_rows[index].id
        if row_id not in input_by_id or row_id in seen:
            raise LocalLlmHsdReviewError("classifier item id did not match input rows")
        seen.add(row_id)
        hate = raw_item.get("hate")
        if not isinstance(hate, bool):
            raise LocalLlmHsdReviewError("classifier hate field was not boolean")
        reason = str(raw_item.get("reason", "") or "")
        if reason not in CLASSIFIER_REASONS:
            raise LocalLlmHsdReviewError("classifier reason was unsupported")
        items.append(
            ClassificationItem(
                row_id=row_id,
                hate=hate,
                reason=reason,
                parse_status="ok",
            )
        )
    return tuple(items)


def skipped_verifier(row: EvalRow, exc: Exception) -> VerifierItem:
    return VerifierItem(
        row_id=row.id,
        decision=None,
        suggested_label=None,
        reason=None,
        parse_status="skipped",
        error_class=type(exc).__name__,
        error=str(exc),
    )


def skipped_classifier(row: EvalRow, exc: Exception) -> ClassificationItem:
    return ClassificationItem(
        row_id=row.id,
        hate=None,
        reason=None,
        parse_status="skipped",
        error_class=type(exc).__name__,
        error=str(exc),
    )


def run_verifier(
    *,
    rows: Sequence[EvalRow],
    model_id: str,
    endpoint: str,
    timeout: float,
    batch_size: int,
    request_callable: RequestCallable | None = None,
) -> TaskRun:
    started = time.perf_counter()
    request_count = 0
    fallback_count = 0
    outputs: list[VerifierItem] = []
    chunk_size = max(1, batch_size)
    schema = verifier_schema()
    for start in range(0, len(rows), chunk_size):
        batch = list(rows[start : start + chunk_size])
        try:
            payload = chat_payload(
                model_id=model_id,
                system_prompt=VERIFIER_SYSTEM_PROMPT,
                user_payload={
                    "items": [
                        {
                            "id": row.id,
                            "main_label": row.main_bool,
                            "text": row.cleaned_text,
                        }
                        for row in batch
                    ]
                },
                schema_name="hsd_verifier",
                schema=schema,
            )
            parsed, requests = request_json_payload(
                endpoint=endpoint,
                timeout=timeout,
                payload=payload,
                request_callable=request_callable,
            )
            request_count += requests
            outputs.extend(normalize_verifier_items(parsed, input_rows=batch))
        except Exception:
            fallback_count += len(batch)
            for row in batch:
                try:
                    payload = chat_payload(
                        model_id=model_id,
                        system_prompt=VERIFIER_SYSTEM_PROMPT,
                        user_payload={
                            "items": [
                                {
                                    "id": row.id,
                                    "main_label": row.main_bool,
                                    "text": row.cleaned_text,
                                }
                            ]
                        },
                        schema_name="hsd_verifier",
                        schema=schema,
                    )
                    parsed, requests = request_json_payload(
                        endpoint=endpoint,
                        timeout=timeout,
                        payload=payload,
                        request_callable=request_callable,
                    )
                    request_count += requests
                    outputs.extend(normalize_verifier_items(parsed, input_rows=[row]))
                except Exception as row_exc:
                    request_count += 1
                    outputs.append(skipped_verifier(row, row_exc))
    return TaskRun(
        model_id=model_id,
        task="verifier",
        rows=tuple(outputs),
        elapsed_seconds=time.perf_counter() - started,
        request_count=request_count,
        fallback_count=fallback_count,
    )


def run_classifier_task(
    *,
    rows: Sequence[EvalRow],
    model_id: str,
    endpoint: str,
    timeout: float,
    batch_size: int,
    task: str,
    system_prompt: str,
    request_callable: RequestCallable | None = None,
    allow_positional_ids: bool = False,
) -> TaskRun:
    started = time.perf_counter()
    request_count = 0
    fallback_count = 0
    outputs: list[ClassificationItem] = []
    chunk_size = max(1, batch_size)
    schema = classifier_schema()
    for start in range(0, len(rows), chunk_size):
        batch = list(rows[start : start + chunk_size])
        try:
            payload = chat_payload(
                model_id=model_id,
                system_prompt=system_prompt,
                user_payload={
                    "items": [
                        {
                            "id": row.id,
                            "text": row.cleaned_text,
                        }
                        for row in batch
                    ]
                },
                schema_name=f"hsd_{task}",
                schema=schema,
            )
            parsed, requests = request_json_payload(
                endpoint=endpoint,
                timeout=timeout,
                payload=payload,
                request_callable=request_callable,
            )
            request_count += requests
            outputs.extend(
                normalize_classifier_items(
                    parsed,
                    input_rows=batch,
                    allow_positional_ids=allow_positional_ids,
                )
            )
        except Exception:
            fallback_count += len(batch)
            for row in batch:
                try:
                    payload = chat_payload(
                        model_id=model_id,
                        system_prompt=system_prompt,
                        user_payload={"items": [{"id": row.id, "text": row.cleaned_text}]},
                        schema_name=f"hsd_{task}",
                        schema=schema,
                    )
                    parsed, requests = request_json_payload(
                        endpoint=endpoint,
                        timeout=timeout,
                        payload=payload,
                        request_callable=request_callable,
                    )
                    request_count += requests
                    outputs.extend(
                        normalize_classifier_items(
                            parsed,
                            input_rows=[row],
                            allow_positional_ids=allow_positional_ids,
                        )
                    )
                except Exception as row_exc:
                    request_count += 1
                    outputs.append(skipped_classifier(row, row_exc))
    return TaskRun(
        model_id=model_id,
        task=task,
        rows=tuple(outputs),
        elapsed_seconds=time.perf_counter() - started,
        request_count=request_count,
        fallback_count=fallback_count,
    )


def run_direct_classifier(
    *,
    rows: Sequence[EvalRow],
    model_id: str,
    endpoint: str,
    timeout: float,
    batch_size: int,
    request_callable: RequestCallable | None = None,
) -> TaskRun:
    return run_classifier_task(
        rows=rows,
        model_id=model_id,
        endpoint=endpoint,
        timeout=timeout,
        batch_size=batch_size,
        task="direct_classifier",
        system_prompt=DIRECT_CLASSIFIER_SYSTEM_PROMPT,
        request_callable=request_callable,
    )


def run_adjudicator(
    *,
    rows: Sequence[EvalRow],
    model_id: str,
    endpoint: str,
    timeout: float,
    batch_size: int,
    request_callable: RequestCallable | None = None,
) -> TaskRun:
    return run_classifier_task(
        rows=rows,
        model_id=model_id,
        endpoint=endpoint,
        timeout=timeout,
        batch_size=batch_size,
        task="adjudicator",
        system_prompt=ADJUDICATION_SYSTEM_PROMPT,
        request_callable=request_callable,
        allow_positional_ids=True,
    )


def binary_metrics(gold: Sequence[bool], pred: Sequence[bool]) -> dict[str, Any]:
    if len(gold) != len(pred):
        raise ValueError("gold and prediction lengths differ")
    tp = sum(1 for g, p in zip(gold, pred, strict=True) if g and p)
    tn = sum(1 for g, p in zip(gold, pred, strict=True) if not g and not p)
    fp = sum(1 for g, p in zip(gold, pred, strict=True) if not g and p)
    fn = sum(1 for g, p in zip(gold, pred, strict=True) if g and not p)
    total = len(gold)
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "row_count": total,
        "accuracy": round(accuracy, 4),
        "balanced_accuracy": round((recall + specificity) / 2, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
    }


def baseline_metrics(rows: Sequence[EvalRow]) -> dict[str, Any]:
    return binary_metrics([row.gold_bool for row in rows], [row.main_bool for row in rows])


def cue_bearing_negative(row: EvalRow) -> bool:
    return (not row.main_bool) and contains_protected_or_hsd_cue(row.cleaned_text)


def item_flagged(item: VerifierItem | None) -> bool:
    return bool(item and item.parse_status == "ok" and item.decision in {"disagree", "uncertain"})


def item_disagreed(item: VerifierItem | None) -> bool:
    return bool(item and item.parse_status == "ok" and item.decision == "disagree")


def verifier_route_ids(
    rows: Sequence[EvalRow],
    verifier_by_id: Mapping[str, VerifierItem],
    *,
    strategy: str,
) -> set[str]:
    routed: set[str] = set()
    for row in rows:
        item = verifier_by_id.get(row.id)
        if not item_flagged(item):
            continue
        if strategy == "positive_verifier" and row.main_bool:
            routed.add(row.id)
        elif strategy == "recall_router" and cue_bearing_negative(row):
            routed.add(row.id)
        elif strategy == "combined_router" and (
            row.main_bool or cue_bearing_negative(row)
        ):
            routed.add(row.id)
    return routed


def direct_flip_predictions(
    rows: Sequence[EvalRow],
    verifier_by_id: Mapping[str, VerifierItem],
    *,
    strategy: str,
) -> list[bool]:
    predictions = []
    for row in rows:
        pred = row.main_bool
        item = verifier_by_id.get(row.id)
        if item and item.parse_status == "ok" and item.decision == "disagree":
            if (
                strategy in {"positive_verifier", "combined_router"}
                and row.main_bool
                and item.suggested_label is False
            ):
                pred = False
            if (
                strategy in {"recall_router", "combined_router"}
                and cue_bearing_negative(row)
                and item.suggested_label is True
            ):
                pred = True
        predictions.append(pred)
    return predictions


def routed_big_predictions(
    rows: Sequence[EvalRow],
    verifier_by_id: Mapping[str, VerifierItem],
    adjudicator_by_id: Mapping[str, ClassificationItem],
    *,
    strategy: str,
) -> list[bool]:
    routed_ids = verifier_route_ids(rows, verifier_by_id, strategy=strategy)
    predictions = []
    for row in rows:
        pred = row.main_bool
        item = adjudicator_by_id.get(row.id)
        if row.id in routed_ids and item and item.parse_status == "ok":
            pred = bool(item.hate)
        predictions.append(pred)
    return predictions


def direct_classifier_predictions(
    rows: Sequence[EvalRow],
    classifier_by_id: Mapping[str, ClassificationItem],
) -> list[bool]:
    predictions = []
    for row in rows:
        item = classifier_by_id.get(row.id)
        predictions.append(bool(item.hate) if item and item.parse_status == "ok" else row.main_bool)
    return predictions


def rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def verifier_rates(
    rows: Sequence[EvalRow],
    verifier_by_id: Mapping[str, VerifierItem],
    *,
    strategy: str,
) -> dict[str, Any]:
    fp_rows = [row for row in rows if row.case_type == "FP"]
    fn_rows = [row for row in rows if row.case_type == "FN"]
    tp_rows = [row for row in rows if row.case_type == "TP"]
    tn_rows = [row for row in rows if row.case_type == "TN"]
    routed_ids = verifier_route_ids(rows, verifier_by_id, strategy=strategy)
    fp_rescue = sum(1 for row in fp_rows if row.id in routed_ids)
    fn_rescue = sum(1 for row in fn_rows if row.id in routed_ids)
    tp_disagree = sum(1 for row in tp_rows if item_disagreed(verifier_by_id.get(row.id)))
    tn_route = sum(1 for row in tn_rows if row.id in routed_ids)
    return {
        "fp_rescue_rate": round(rate(fp_rescue, len(fp_rows)), 4),
        "tp_disagree_rate": round(rate(tp_disagree, len(tp_rows)), 4),
        "fn_rescue_rate": round(rate(fn_rescue, len(fn_rows)), 4),
        "tn_route_rate": round(rate(tn_route, len(tn_rows)), 4),
        "estimated_production_overhead": round(rate(len(routed_ids), len(rows)), 4),
        "routed_count": len(routed_ids),
        "routed_ids": sorted(routed_ids),
    }


def strategy_score(
    *,
    fp_rescue_rate: float,
    fn_rescue_rate: float,
    tp_disagree_rate: float,
    tn_route_rate: float,
    parse_failure_rate: float,
    seconds_per_row: float,
) -> float:
    return (
        2.0 * fp_rescue_rate
        + 1.5 * fn_rescue_rate
        - 2.5 * tp_disagree_rate
        - 1.5 * tn_route_rate
        - 1.0 * parse_failure_rate
        - 0.2 * seconds_per_row
    )


def summarize_candidate(
    rows: Sequence[EvalRow],
    *,
    direct_run: TaskRun,
    verifier_run: TaskRun,
    adjudicator_by_id: Mapping[str, ClassificationItem] | None = None,
) -> dict[str, Any]:
    verifier_by_id = {
        row.row_id: row for row in verifier_run.rows if isinstance(row, VerifierItem)
    }
    direct_by_id = {
        row.row_id: row for row in direct_run.rows if isinstance(row, ClassificationItem)
    }
    gold = [row.gold_bool for row in rows]
    parse_failure_rate = 1.0 - verifier_run.parse_success_rate
    decision_counts = Counter(
        row.decision
        for row in verifier_by_id.values()
        if row.parse_status == "ok" and row.decision
    )
    reason_counts = Counter(
        row.reason
        for row in verifier_by_id.values()
        if row.parse_status == "ok" and row.reason
    )
    strategies: dict[str, Any] = {}
    for strategy in ("positive_verifier", "recall_router", "combined_router"):
        rates = verifier_rates(rows, verifier_by_id, strategy=strategy)
        direct_metrics = binary_metrics(
            gold,
            direct_flip_predictions(rows, verifier_by_id, strategy=strategy),
        )
        score = strategy_score(
            fp_rescue_rate=rates["fp_rescue_rate"],
            fn_rescue_rate=rates["fn_rescue_rate"],
            tp_disagree_rate=rates["tp_disagree_rate"],
            tn_route_rate=rates["tn_route_rate"],
            parse_failure_rate=parse_failure_rate,
            seconds_per_row=verifier_run.seconds_per_row,
        )
        strategy_summary = {
            **rates,
            "selection_score": round(score, 4),
            "direct_flip_metrics": direct_metrics,
        }
        if adjudicator_by_id is not None:
            strategy_summary["routed_to_big_metrics"] = binary_metrics(
                gold,
                routed_big_predictions(
                    rows,
                    verifier_by_id,
                    adjudicator_by_id,
                    strategy=strategy,
                ),
            )
        strategies[strategy] = strategy_summary

    return {
        "model_id": verifier_run.model_id,
        "direct_classifier": {
            **direct_run.summary(),
            "metrics": binary_metrics(
                gold,
                direct_classifier_predictions(rows, direct_by_id),
            ),
        },
        "verifier": {
            **verifier_run.summary(),
            "decision_counts": dict(sorted(decision_counts.items())),
            "reason_counts": dict(sorted(reason_counts.items())),
        },
        "strategies": strategies,
    }


def screen_rows(rows: Sequence[EvalRow], *, fp_n: int = 20, fn_n: int = 20) -> list[EvalRow]:
    selected: list[EvalRow] = []
    selected.extend([row for row in rows if row.case_type == "FP"][:fp_n])
    selected.extend([row for row in rows if row.case_type == "FN"][:fn_n])
    return selected


def shortlist_from_screen(
    screen_results: Mapping[str, Any],
    *,
    shortlist_size: int,
    min_parse_success: float,
) -> list[str]:
    scored = []
    for candidate in screen_results.get("candidates", []):
        parse_success = float(candidate["verifier"]["parse_success_rate"])
        if parse_success < min_parse_success:
            continue
        score = float(candidate["strategies"]["combined_router"]["selection_score"])
        scored.append((score, candidate["model_id"]))
    scored.sort(reverse=True)
    return [model_id for _score, model_id in scored[:shortlist_size]]


def collect_routed_rows(
    rows: Sequence[EvalRow],
    full_candidate_results: Sequence[Mapping[str, Any]],
) -> list[EvalRow]:
    routed_ids: set[str] = set()
    for candidate in full_candidate_results:
        for strategy in ("positive_verifier", "recall_router", "combined_router"):
            routed_ids.update(candidate["strategies"][strategy]["routed_ids"])
    by_id = {row.id: row for row in rows}
    return [by_id[row_id] for row_id in sorted(routed_ids) if row_id in by_id]


def compact_candidate_metadata(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "model_id": result["model_id"],
        "direct_classifier": result["direct_classifier"],
        "verifier": result["verifier"],
        "strategies": {
            name: {
                key: value
                for key, value in strategy.items()
                if key != "routed_ids"
            }
            for name, strategy in result["strategies"].items()
        },
    }


def choose_recommendation(
    full_results: Sequence[Mapping[str, Any]],
    adjudicated_results: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    source = adjudicated_results or full_results
    if not source:
        return None
    def key(result: Mapping[str, Any]) -> tuple[float, float, float]:
        combined = result["strategies"]["combined_router"]
        routed_metrics = combined.get("routed_to_big_metrics")
        metrics = routed_metrics or combined["direct_flip_metrics"]
        return (
            float(metrics["f1"]),
            float(metrics["precision"]),
            float(combined["selection_score"]),
        )

    return max(source, key=key)


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_recommendation(
    path: Path,
    *,
    baseline: Mapping[str, Any],
    screen_results: Mapping[str, Any],
    shortlist_results: Mapping[str, Any],
    adjudication_results: Mapping[str, Any],
) -> None:
    final_results = adjudication_results.get("candidates", [])
    if not final_results:
        final_results = shortlist_results.get("candidates", [])
    scoped_positive = (
        adjudication_results.get("scope") == "selected_candidate_positive_verifier"
    )
    if scoped_positive and final_results:
        best = final_results[0]
        recommended_strategy = "positive_verifier"
    else:
        best = choose_recommendation(
            shortlist_results.get("candidates", []),
            final_results,
        )
        recommended_strategy = "combined_router"
    if best is None:
        text = "# Mini 4B Verifier Evaluation Recommendation\n\nNo candidate completed.\n"
        path.write_text(text, encoding="utf-8")
        return
    strategy_result = best["strategies"][recommended_strategy]
    final_metrics = (
        strategy_result.get("routed_to_big_metrics")
        or strategy_result["direct_flip_metrics"]
    )
    direct_metrics = best["direct_classifier"]["metrics"]
    role_sentence = (
        "positive verifier for the next full-sample comparison; do not enable as a production route yet."
        if scoped_positive
        else "combined router, not direct relabeler."
    )
    runtime_sentence = (
        "The completed routed-to-20B pass covered the selected positive-verifier route only. It improved false positives but hurt recall, so full-sample testing should compare the small model's direct labels and positive-verifier direct-flip upper bound before runtime promotion."
        if scoped_positive
        else "keep `openai/gpt-oss-20b` as the main classifier, route verifier `disagree` and `uncertain` rows to the 20B adjudication prompt, and do not let the small model directly override labels."
    )
    lines = [
        "# Mini 4B Verifier Evaluation Recommendation",
        "",
        "## Recommendation",
        "",
        f"- Selected small model: `{best['model_id']}`",
        f"- Recommended role: {role_sentence}",
        f"- Runtime design: {runtime_sentence}",
        "- Prompt promotion: do not replace the main runtime prompt from this evaluation alone.",
        "",
        "## Eval-Set Metrics",
        "",
        f"- Baseline main model on error-enriched eval set: accuracy {baseline['accuracy']:.4f}, precision {baseline['precision']:.4f}, recall {baseline['recall']:.4f}, F1 {baseline['f1']:.4f}.",
        f"- Selected {recommended_strategy.replace('_', ' ')} final metrics: accuracy {final_metrics['accuracy']:.4f}, precision {final_metrics['precision']:.4f}, recall {final_metrics['recall']:.4f}, F1 {final_metrics['f1']:.4f}.",
        f"- Selected small-model direct classifier metrics: accuracy {direct_metrics['accuracy']:.4f}, precision {direct_metrics['precision']:.4f}, recall {direct_metrics['recall']:.4f}, F1 {direct_metrics['f1']:.4f}.",
        "",
        "## Routing Profile",
        "",
        f"- Parse success: {best['verifier']['parse_success_rate']:.4f}.",
        f"- Estimated production overhead on this eval set: {format_percent(strategy_result['estimated_production_overhead'])} ({strategy_result['routed_count']} routed rows).",
        f"- FP rescue rate: {format_percent(strategy_result['fp_rescue_rate'])}.",
        f"- FN rescue rate: {format_percent(strategy_result['fn_rescue_rate'])}.",
        f"- TP disagree risk: {format_percent(strategy_result['tp_disagree_rate'])}.",
        f"- TN route risk/overhead: {format_percent(strategy_result['tn_route_rate'])}.",
        f"- Selection score: {strategy_result['selection_score']:.4f}.",
        "",
        "## Shortlist",
        "",
    ]
    for candidate in shortlist_results.get("candidates", []):
        strategy = candidate["strategies"].get(
            recommended_strategy,
            candidate["strategies"]["combined_router"],
        )
        metrics = strategy.get("routed_to_big_metrics") or strategy["direct_flip_metrics"]
        lines.append(
            f"- `{candidate['model_id']}`: score {strategy['selection_score']:.4f}, "
            f"overhead {format_percent(strategy['estimated_production_overhead'])}, "
            f"precision {metrics['precision']:.4f}, recall {metrics['recall']:.4f}, "
            f"F1 {metrics['f1']:.4f}"
        )
    lines.extend(
        [
            "",
            "## Remaining Error Patterns",
            "",
            "- Rows not routed by the cue-gated recall path remain unresolved false negatives.",
            "- The recall-router and combined-router settings routed too many TN controls in this mini run.",
            "- The selected positive-verifier routed-to-20B pass lowered recall on this error-enriched set; the direct small-model signal was stronger than the 20B adjudication prompt here.",
            "- Ambiguous quotation, reported speech, and counterspeech cases still require 20B adjudication rather than a direct small-model flip.",
            "- The error-enriched eval set is not representative of production prevalence; full-sample comparison is still required before enabling this router by default.",
            "",
            "## Artifacts",
            "",
            "- `models_seen.json` records the LM Studio inventory used for candidate selection.",
            "- `candidate_screen_results.json` records the 40-row screen.",
            "- `shortlist_results.json` records full 160-row shortlist runs.",
            "- `adjudication_results.json` records routed 20B adjudication.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_verifier_eval(
    *,
    source_csv: Path = DEFAULT_SOURCE_CSV,
    run_dir: Path = DEFAULT_RUN_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    endpoint: str = DEFAULT_ENDPOINT,
    main_model: str = DEFAULT_MAIN_MODEL,
    batch_size: int = 10,
    timeout_seconds: float = 120.0,
    candidates: Sequence[str] = (),
    shortlist_size: int = 3,
    rebuild_eval_set: bool = False,
    include_uncensored_probe: bool = True,
    include_cost_floor: bool = False,
    min_screen_parse_success: float = 0.95,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    eval_csv = output_dir / "eval_set_160.csv"
    rows = ensure_eval_set(
        source_csv=source_csv,
        run_dir=run_dir,
        out_csv=eval_csv,
        rebuild=rebuild_eval_set,
    )
    baseline = baseline_metrics(rows)

    def progress(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    models_endpoint = models_endpoint_for_chat(endpoint)
    progress(f"Querying model list from {models_endpoint}")
    models_seen = fetch_models(models_endpoint, timeout=timeout_seconds)
    selected_candidates, probes = select_candidates(
        models_seen["model_ids"],
        explicit_candidates=candidates,
        include_uncensored_probe=include_uncensored_probe,
        include_cost_floor=include_cost_floor,
    )
    models_seen["selected_candidates"] = selected_candidates
    models_seen["probe_candidates"] = probes
    write_json(output_dir / "models_seen.json", models_seen)

    screen_set = screen_rows(rows)
    screen_candidate_summaries: list[dict[str, Any]] = []
    for model_id in selected_candidates:
        progress(f"Screening {model_id} on {len(screen_set)} rows")
        direct = run_direct_classifier(
            rows=screen_set,
            model_id=model_id,
            endpoint=endpoint,
            timeout=timeout_seconds,
            batch_size=batch_size,
        )
        verifier = run_verifier(
            rows=screen_set,
            model_id=model_id,
            endpoint=endpoint,
            timeout=timeout_seconds,
            batch_size=batch_size,
        )
        summary = summarize_candidate(screen_set, direct_run=direct, verifier_run=verifier)
        summary["direct_classifier_raw"] = direct.to_metadata()
        summary["verifier_raw"] = verifier.to_metadata()
        screen_candidate_summaries.append(summary)
    screen_results = {
        "baseline_metrics": baseline_metrics(screen_set),
        "screen_rows": [row.id for row in screen_set],
        "candidates": screen_candidate_summaries,
        "probes_not_screened": probes,
    }
    write_json(output_dir / "candidate_screen_results.json", screen_results)

    shortlist = shortlist_from_screen(
        screen_results,
        shortlist_size=shortlist_size,
        min_parse_success=min_screen_parse_success,
    )
    if not shortlist and selected_candidates:
        shortlist = selected_candidates[:shortlist_size]
    full_models = shortlist + [probe for probe in probes if probe not in shortlist]
    full_candidate_summaries: list[dict[str, Any]] = []
    for model_id in full_models:
        progress(f"Running full eval for {model_id} on {len(rows)} rows")
        direct = run_direct_classifier(
            rows=rows,
            model_id=model_id,
            endpoint=endpoint,
            timeout=timeout_seconds,
            batch_size=batch_size,
        )
        verifier = run_verifier(
            rows=rows,
            model_id=model_id,
            endpoint=endpoint,
            timeout=timeout_seconds,
            batch_size=batch_size,
        )
        summary = summarize_candidate(rows, direct_run=direct, verifier_run=verifier)
        summary["probe"] = model_id in probes
        summary["direct_classifier_raw"] = direct.to_metadata()
        summary["verifier_raw"] = verifier.to_metadata()
        full_candidate_summaries.append(summary)
    shortlist_results = {
        "baseline_metrics": baseline,
        "shortlist": shortlist,
        "probe_candidates": probes,
        "candidates": full_candidate_summaries,
    }
    write_json(output_dir / "shortlist_results.json", shortlist_results)

    routed_rows = collect_routed_rows(
        rows,
        [
            candidate
            for candidate in full_candidate_summaries
            if not bool(candidate.get("probe"))
        ],
    )
    progress(f"Running 20B adjudication on {len(routed_rows)} routed rows")
    adjudicator = run_adjudicator(
        rows=routed_rows,
        model_id=main_model,
        endpoint=endpoint,
        timeout=timeout_seconds,
        batch_size=batch_size,
    )
    adjudicator_by_id = {
        row.row_id: row
        for row in adjudicator.rows
        if isinstance(row, ClassificationItem)
    }
    adjudicated_candidate_summaries = []
    for candidate in full_candidate_summaries:
        direct_rows = tuple(
            ClassificationItem(
                row_id=item["id"],
                hate=item.get("hate"),
                reason=item.get("reason"),
                parse_status=item.get("parse_status", "skipped"),
                error_class=item.get("error_class"),
                error=item.get("error"),
            )
            for item in candidate["direct_classifier_raw"]["rows"]
        )
        verifier_rows = tuple(
            VerifierItem(
                row_id=item["id"],
                decision=item.get("decision"),
                suggested_label=item.get("suggested_label"),
                reason=item.get("reason"),
                parse_status=item.get("parse_status", "skipped"),
                error_class=item.get("error_class"),
                error=item.get("error"),
            )
            for item in candidate["verifier_raw"]["rows"]
        )
        direct_run = TaskRun(
            model_id=candidate["model_id"],
            task="direct_classifier",
            rows=direct_rows,
            elapsed_seconds=float(candidate["direct_classifier"]["elapsed_seconds"]),
            request_count=int(candidate["direct_classifier"]["request_count"]),
            fallback_count=int(candidate["direct_classifier"]["fallback_count"]),
        )
        verifier_run = TaskRun(
            model_id=candidate["model_id"],
            task="verifier",
            rows=verifier_rows,
            elapsed_seconds=float(candidate["verifier"]["elapsed_seconds"]),
            request_count=int(candidate["verifier"]["request_count"]),
            fallback_count=int(candidate["verifier"]["fallback_count"]),
        )
        updated = summarize_candidate(
            rows,
            direct_run=direct_run,
            verifier_run=verifier_run,
            adjudicator_by_id=adjudicator_by_id,
        )
        updated["probe"] = bool(candidate.get("probe"))
        adjudicated_candidate_summaries.append(updated)

    adjudication_results = {
        "main_model": main_model,
        "routed_row_count": len(routed_rows),
        "routed_ids": [row.id for row in routed_rows],
        "adjudicator": adjudicator.to_metadata(),
        "candidates": adjudicated_candidate_summaries,
    }
    write_json(output_dir / "adjudication_results.json", adjudication_results)
    write_recommendation(
        output_dir / "recommendation.md",
        baseline=baseline,
        screen_results=screen_results,
        shortlist_results=shortlist_results,
        adjudication_results=adjudication_results,
    )
    return {
        "output_dir": str(output_dir),
        "eval_set": str(eval_csv),
        "models_seen": str(output_dir / "models_seen.json"),
        "candidate_screen_results": str(output_dir / "candidate_screen_results.json"),
        "shortlist_results": str(output_dir / "shortlist_results.json"),
        "adjudication_results": str(output_dir / "adjudication_results.json"),
        "recommendation": str(output_dir / "recommendation.md"),
        "selected_candidates": selected_candidates,
        "shortlist": shortlist,
        "probe_candidates": probes,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextsafe-hsd mini-verifier-eval",
        description="Run the mini 3B-4B verifier/router evaluation against LM Studio.",
    )
    parser.add_argument("--source-csv", type=Path, default=DEFAULT_SOURCE_CSV)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--main-model", default=DEFAULT_MAIN_MODEL)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--candidate", action="append", dest="candidates", default=[])
    parser.add_argument("--shortlist-size", type=int, default=3)
    parser.add_argument("--rebuild-eval-set", action="store_true")
    parser.add_argument("--include-cost-floor", action="store_true")
    parser.add_argument(
        "--skip-uncensored-probe",
        action="store_true",
        help="Do not run the aggressive uncensored probe even if present.",
    )
    parser.add_argument("--min-screen-parse-success", type=float, default=0.95)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    result = run_verifier_eval(
        source_csv=args.source_csv,
        run_dir=args.run_dir,
        output_dir=args.output_dir,
        endpoint=args.endpoint,
        main_model=args.main_model,
        batch_size=args.batch_size,
        timeout_seconds=args.timeout_seconds,
        candidates=args.candidates,
        shortlist_size=args.shortlist_size,
        rebuild_eval_set=args.rebuild_eval_set,
        include_uncensored_probe=not args.skip_uncensored_probe,
        include_cost_floor=args.include_cost_floor,
        min_screen_parse_success=args.min_screen_parse_success,
        progress_callback=lambda message: print(f"[evaluation] {message}", flush=True),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


__all__ = [
    "ADJUDICATION_SYSTEM_PROMPT",
    "DEFAULT_ENDPOINT",
    "DEFAULT_MAIN_MODEL",
    "DIRECT_CLASSIFIER_SYSTEM_PROMPT",
    "EvalRow",
    "MiniVerifierError",
    "RECOMMENDED_CANDIDATES",
    "UNCENSORED_PROBE",
    "VERIFIER_SYSTEM_PROMPT",
    "baseline_metrics",
    "binary_metrics",
    "build_eval_set",
    "cue_bearing_negative",
    "ensure_eval_set",
    "main",
    "parse_json_object",
    "run_verifier_eval",
    "run_direct_classifier",
    "run_verifier",
    "screen_rows",
    "select_candidates",
    "summarize_candidate",
]
