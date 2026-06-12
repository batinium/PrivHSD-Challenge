#!/usr/bin/env python3
"""Generate a large synthetic PrivHSD challenge corpus through LM Studio.

The generator is intentionally resumable and append-only. It asks for one row
per model request, stores the exact prompt and raw response, validates/parses
labels, and enriches the row with local weak token-action labels.

Generated rows are stress-test and augmentation candidates. They are not
trusted training data until reviewed, deduplicated, and balanced.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
import csv
import hashlib
import json
from pathlib import Path
import random
import re
import signal
import sys
import time
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from privhsd.context import analyze_context
from privhsd.detectors import detect_spans, target_group_spans
from privhsd.pipeline import PrivatizerConfig, privatize_text
from privhsd.token_policy import token_examples_for_row, weak_action_spans_for_row


DEFAULT_ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
DEFAULT_MODEL = "gemma-4-e4b-uncensored-hauhaucs-aggressive"
DEFAULT_OUTPUT = Path("data/outputs/synthetic_challenge_corpus.csv")
DEFAULT_ERRORS = Path("data/outputs/synthetic_challenge_corpus.errors.jsonl")
DEFAULT_REPORT = Path("data/outputs/synthetic_challenge_corpus.report.json")
DEFAULT_STATUS = Path("data/outputs/synthetic_challenge_corpus.status.json")

ALLOWED_LABELS = {"hate", "offensive", "not_hate", "ambiguous"}
ALLOWED_SEVERITIES = {"none", "low", "medium", "high"}
TARGET_CATEGORIES = (
    "race_or_ethnicity",
    "religion",
    "nationality_or_origin",
    "gender",
    "sexual_orientation",
    "disability",
    "age",
    "historical_victim_group",
    "mixed_or_intersectional",
    "none",
)
PII_TYPES = (
    "none",
    "person_name",
    "lowercase_person_name",
    "unicode_person_name",
    "city",
    "country",
    "street",
    "school_or_org",
    "email",
    "handle",
    "phone",
    "date",
    "age",
    "case_id",
    "mixed_pii",
)
PII_SCHEDULE = (
    "none",
    "person_name",
    "none",
    "lowercase_person_name",
    "none",
    "unicode_person_name",
    "city",
    "none",
    "country",
    "street",
    "none",
    "school_or_org",
    "email",
    "none",
    "handle",
    "phone",
    "none",
    "date",
    "age",
    "case_id",
    "none",
    "mixed_pii",
)
HSD_FRAMES = (
    "direct_hate",
    "exclusion",
    "dehumanization",
    "threat_or_intimidation",
    "stereotype",
    "coded_language",
    "slur_variant",
    "sarcasm",
    "harassment_reply",
    "reported_speech",
    "quoted_hate",
    "counterspeech",
    "public_interest_criticism",
    "neutral_identity_mention",
    "ambiguous_context",
)
SURFACES = (
    "short social post",
    "reply thread",
    "quoted statement",
    "forum comment",
    "moderation note",
    "news comment",
    "support hotline report",
    "NGO intake note",
    "school incident note",
    "chat message",
    "hashtag-heavy post",
    "typo-heavy post",
)
REGISTERS = (
    "casual",
    "angry",
    "sarcastic",
    "bureaucratic",
    "teen slang",
    "formal report",
    "community organizer",
    "journalistic",
    "broken grammar",
    "code-switched English",
)
PLATFORMS = (
    "x_twitter",
    "facebook",
    "reddit",
    "youtube",
    "tiktok",
    "forum",
    "news_comments",
    "ngo_report",
    "school_report",
    "chat",
)
LENGTH_PROFILES = ("one_clause", "one_sentence", "two_sentences", "three_sentences")

FIELDNAMES = [
    "id",
    "text",
    "label",
    "source",
    "split",
    "target",
    "type",
    "platform",
    "source_id",
    "severity",
    "target_categories",
    "rationale_spans",
    "meta",
    "prompt",
    "raw_response",
    "parsed_json",
    "validation_status",
    "validation_errors",
    "privacy_spans_json",
    "target_spans_json",
    "context_tags_json",
    "token_actions_json",
    "token_action_counts",
    "action_spans_json",
    "balanced_text",
    "privacy_text",
    "text_hash",
    "request_index",
    "scenario_id",
    "phenomena",
    "llm_label_rationale",
    "llm_privacy_rationale",
    "expected_privacy_spans",
    "expected_target_terms",
    "utility_cues",
]


STOP_REQUESTED = False


def handle_stop(_signum: int, _frame: Any) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a large synthetic challenge-oriented CSV through an "
            "LM Studio OpenAI-compatible chat endpoint."
        )
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--errors", type=Path, default=DEFAULT_ERRORS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--target-count", type=int, default=100_000)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--seed", type=int, default=20260612)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-consecutive-errors", type=int, default=50)
    parser.add_argument("--retry-sleep", type=float, default=5.0)
    parser.add_argument("--heartbeat-every", type=int, default=25)
    parser.add_argument("--recent-window", type=int, default=40)
    parser.add_argument(
        "--stop-file",
        type=Path,
        default=Path("data/outputs/STOP_SYNTHETIC_GENERATION"),
        help="Create this file to request a graceful stop.",
    )
    return parser.parse_args()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def normalized_text_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def read_existing_hashes(path: Path) -> tuple[set[str], int]:
    if not path.exists():
        return set(), 0
    hashes: set[str] = set()
    row_count = 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row_count += 1
            value = str(row.get("text_hash", "") or "").strip()
            if value:
                hashes.add(value)
    return hashes, row_count


def open_csv_writer(path: Path, *, resume: bool) -> tuple[Any, csv.DictWriter[str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    append = resume and path.exists() and path.stat().st_size > 0
    handle = path.open("a" if append else "w", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
    if not append:
        writer.writeheader()
        handle.flush()
    return handle, writer


def append_error(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def choose_scenario(request_index: int, rng: random.Random) -> dict[str, Any]:
    target_category = TARGET_CATEGORIES[request_index % len(TARGET_CATEGORIES)]
    pii_type = PII_SCHEDULE[(request_index // len(TARGET_CATEGORIES)) % len(PII_SCHEDULE)]
    frame = HSD_FRAMES[(request_index // (len(TARGET_CATEGORIES) * 3)) % len(HSD_FRAMES)]
    surface = rng.choice(SURFACES)
    register = rng.choice(REGISTERS)
    platform = rng.choice(PLATFORMS)
    length_profile = rng.choice(LENGTH_PROFILES)
    style_constraints = rng.sample(
        [
            "include at most one hashtag",
            "use no hashtag",
            "include one emoji if natural",
            "include typo or obfuscation if natural",
            "include quotation marks if natural",
            "avoid starting with 'They say'",
            "avoid starting with 'I hate'",
            "use a place reference if privacy risk requires it",
            "use a named person only if privacy risk requires it",
            "make it sound like a real moderation queue item",
            "make it sound like raw user-generated content",
        ],
        k=4,
    )
    if frame in {"counterspeech", "neutral_identity_mention", "public_interest_criticism"}:
        label_hint = rng.choice(["not_hate", "ambiguous", "offensive"])
    elif frame in {"reported_speech", "quoted_hate", "ambiguous_context"}:
        label_hint = rng.choice(["ambiguous", "hate", "not_hate"])
    elif frame in {"stereotype", "sarcasm", "coded_language"}:
        label_hint = rng.choice(["hate", "offensive", "ambiguous"])
    else:
        label_hint = rng.choice(["hate", "offensive"])
    if target_category == "none" and label_hint == "hate":
        label_hint = rng.choice(["offensive", "not_hate", "ambiguous"])
    scenario_id = hashlib.sha1(
        "|".join(
            [
                str(request_index),
                target_category,
                pii_type,
                frame,
                surface,
                register,
            ]
        ).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "scenario_id": scenario_id,
        "request_index": request_index,
        "target_category": target_category,
        "pii_type": pii_type,
        "frame": frame,
        "surface": surface,
        "register": register,
        "platform": platform,
        "length_profile": length_profile,
        "label_hint": label_hint,
        "style_constraints": style_constraints,
        "lexical_seed": rng.randrange(1_000_000_000),
    }


def prompt_for_scenario(scenario: dict[str, Any], recent_signatures: list[str]) -> str:
    schema = {
        "text": "synthetic sample text",
        "label": "hate|offensive|not_hate|ambiguous",
        "target": "short target group text or none",
        "target_categories": ["race_or_ethnicity|religion|nationality_or_origin|gender|sexual_orientation|disability|age|historical_victim_group|mixed_or_intersectional|none"],
        "type": "direct_hate|offensive_abuse|counter_speech|quoted_or_reported|neutral_or_benign|ambiguous_edge_case|public_interest",
        "platform": "platform-like source",
        "severity": "none|low|medium|high",
        "pii_annotations": [
            {"text": "exact privacy span", "type": "PERSON|LOCATION|ORG|EMAIL|USER|PHONE|DATE|AGE|ID", "privacy_action": "mask|generalize"}
        ],
        "target_annotations": [
            {"text": "exact target span", "category": "target category"}
        ],
        "utility_cues": [
            {"text": "exact cue", "type": "target|action|threat|dehumanization|exclusion|negation|quotation|counterspeech|sarcasm|style"}
        ],
        "rationale_spans": [
            {"start": 0, "end": 4, "label": "target|action|threat|dehumanization|negation|quote|counter|privacy"}
        ],
        "label_rationale": "one short audit note, not hidden chain-of-thought",
        "privacy_rationale": "one short privacy note",
    }
    task = {
        "task": "create_one_synthetic_privhsd_training_row",
        "scenario": scenario,
        "recent_style_signatures_to_avoid": recent_signatures[-12:],
        "required_json_schema": schema,
        "hard_constraints": [
            "Return exactly one JSON object and no markdown.",
            "The text must be fictional and must not contain real private personal data.",
            "Use one sample only.",
            "Use target-group evidence when the label is hate.",
            "Occasionally include PII or quasi-identifiers according to pii_type, but never real private data.",
            "When PII exists, pii_annotations must include exact text spans.",
            "When target groups exist, target_annotations must include exact text spans.",
            "rationale_spans must use character offsets in the text.",
            "Keep label_rationale and privacy_rationale short; do not reveal hidden chain-of-thought.",
            "Vary wording, syntax, platform style, target group, and privacy surface.",
            "Avoid repeating familiar templates like 'They say ... but ...' unless scenario requires it.",
        ],
        "challenge_goal": (
            "The row should test privacy-preserving hate-speech dataset "
            "preprocessing: hide personal identifiers and quasi-identifiers "
            "while preserving protected target, hostile action, negation, "
            "quotation, counterspeech, and public-interest context."
        ),
    }
    return json.dumps(task, ensure_ascii=False, sort_keys=True)


def chat_payload(
    *,
    model: str,
    prompt: str,
    temperature: float,
) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": temperature,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You generate fictional, structured, safety-audit data for "
                    "privacy-preserving hate-speech detection research. You may "
                    "include offensive or hateful language only when it is "
                    "necessary to test detection and anonymization. Do not use "
                    "real private personal data. Output strict JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }


def post_chat_completion(
    *,
    endpoint: str,
    payload: dict[str, Any],
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
        if exc.code == 400 and "response_format" in payload:
            fallback = dict(payload)
            fallback.pop("response_format", None)
            return post_chat_completion(
                endpoint=endpoint,
                payload=fallback,
                timeout=timeout,
            )
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except (OSError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(str(exc)) from exc


def response_content(response: dict[str, Any]) -> str:
    try:
        return str(response["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("model response did not contain message content") from exc


def parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return value
    decoder = json.JSONDecoder()
    for index, character in enumerate(stripped):
        if character != "{":
            continue
        try:
            candidate, _end = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    raise RuntimeError("model response did not contain a JSON object")


def clean_label(value: Any) -> str:
    label = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "non_hate": "not_hate",
        "not hate": "not_hate",
        "neutral": "not_hate",
        "benign": "not_hate",
        "abusive": "offensive",
        "toxicity": "offensive",
        "toxic": "offensive",
    }
    return aliases.get(label, label)


def clean_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [item.strip() for item in re.split(r"[,;|]", value) if item.strip()]
    elif isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        items = []
    return items


def validate_offsets(text: str, spans: Any, *, text_key: str = "text") -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    valid: list[dict[str, Any]] = []
    if not isinstance(spans, list):
        return valid, errors
    for item in spans:
        if not isinstance(item, dict):
            errors.append("span_not_object")
            continue
        span_text = str(item.get(text_key, item.get("text", "")) or "")
        start = item.get("start")
        end = item.get("end")
        if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text):
            if span_text and text[start:end] != span_text:
                found = text.find(span_text)
                if found >= 0:
                    start = found
                    end = found + len(span_text)
                else:
                    errors.append(f"span_text_mismatch:{span_text[:40]}")
            valid_item = dict(item)
            valid_item["start"] = start
            valid_item["end"] = end
            valid.append(valid_item)
            continue
        if span_text:
            found = text.find(span_text)
            if found >= 0:
                valid_item = dict(item)
                valid_item["start"] = found
                valid_item["end"] = found + len(span_text)
                valid.append(valid_item)
            else:
                errors.append(f"span_not_found:{span_text[:40]}")
    return valid, errors


def local_enrichment(row: dict[str, str]) -> dict[str, Any]:
    text = row["text"]
    privacy_spans = detect_spans(text, include_context=True, include_targets=False)
    target_spans = target_group_spans(text)
    balanced = privatize_text(text, PrivatizerConfig(mode="balanced"))
    privacy = privatize_text(text, PrivatizerConfig(mode="privacy"))
    context = analyze_context(
        text,
        metadata={
            "target": row.get("target", ""),
            "target_categories": row.get("target_categories", ""),
        },
    )
    action_spans = weak_action_spans_for_row(
        row,
        text_col="text",
        source_col="source",
        target_col="target",
        target_categories_col="target_categories",
        rationale_col="rationale_spans",
    )
    token_examples = token_examples_for_row(
        row,
        row_index=int(row["request_index"]) + 1,
        text_col="text",
        id_col="id",
        source_col="source",
        target_col="target",
        target_categories_col="target_categories",
        rationale_col="rationale_spans",
    )
    token_actions = [
        {
            "token_index": item.token_index,
            "token": item.token,
            "start": item.start,
            "end": item.end,
            "action": item.action,
            "reasons": list(item.reasons),
        }
        for item in token_examples
    ]
    return {
        "privacy_spans": [
            {
                "text": span.text,
                "type": span.entity_type,
                "source": span.source,
                "start": span.start,
                "end": span.end,
                "category": span.category,
            }
            for span in privacy_spans
        ],
        "target_spans": [
            {
                "text": span.text,
                "category": span.category,
                "source": span.source,
                "start": span.start,
                "end": span.end,
            }
            for span in target_spans
        ],
        "context_tags": context,
        "action_spans": [
            {
                "start": span.start,
                "end": span.end,
                "action": span.action,
                "reason": span.reason,
                "score": span.score,
            }
            for span in action_spans
        ],
        "token_actions": token_actions,
        "token_action_counts": dict(sorted(Counter(item["action"] for item in token_actions).items())),
        "balanced_text": balanced.text,
        "privacy_text": privacy.text,
    }


def build_row(
    *,
    parsed: dict[str, Any],
    prompt: str,
    raw_response: str,
    scenario: dict[str, Any],
    request_index: int,
    model: str,
) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    text = re.sub(r"\s+", " ", str(parsed.get("text", "") or "")).strip()
    label = clean_label(parsed.get("label"))
    if not text:
        errors.append("missing_text")
    if label not in ALLOWED_LABELS:
        errors.append(f"invalid_label:{label}")
        label = scenario["label_hint"]
    severity = str(parsed.get("severity", "") or "").strip().lower()
    if severity not in ALLOWED_SEVERITIES:
        errors.append(f"invalid_severity:{severity}")
        severity = "none" if label == "not_hate" else "medium"
    target_categories = clean_string_list(parsed.get("target_categories"))
    if not target_categories:
        target_categories = [str(scenario["target_category"])]
    target_categories = [
        category if category in TARGET_CATEGORIES else "mixed_or_intersectional"
        for category in target_categories
    ]
    target = str(parsed.get("target", "") or "").strip() or (
        "none" if target_categories == ["none"] else ";".join(target_categories)
    )
    pii_annotations, pii_errors = validate_offsets(text, parsed.get("pii_annotations"))
    target_annotations, target_errors = validate_offsets(text, parsed.get("target_annotations"))
    rationale_spans, rationale_errors = validate_offsets(
        text,
        parsed.get("rationale_spans"),
        text_key="text",
    )
    errors.extend(pii_errors)
    errors.extend(target_errors)
    errors.extend(rationale_errors)
    row_id = f"synthetic_lmstudio_{request_index:06d}"
    meta = {
        "generator": "lm_studio",
        "model": model,
        "scenario": scenario,
        "pii_annotations": pii_annotations,
        "target_annotations": target_annotations,
        "label_rationale": str(parsed.get("label_rationale", "") or "").strip(),
        "privacy_rationale": str(parsed.get("privacy_rationale", "") or "").strip(),
    }
    row: dict[str, str] = {
        "id": row_id,
        "text": text,
        "label": label,
        "source": "synthetic_lmstudio_privhsd",
        "split": "synthetic",
        "target": target,
        "type": str(parsed.get("type", "") or scenario["frame"]).strip(),
        "platform": str(parsed.get("platform", "") or scenario["platform"]).strip(),
        "source_id": row_id,
        "severity": severity,
        "target_categories": json_dumps(target_categories),
        "rationale_spans": json_dumps(rationale_spans),
        "meta": json_dumps(meta),
        "prompt": prompt,
        "raw_response": raw_response,
        "parsed_json": json_dumps(parsed),
        "validation_status": "ok",
        "validation_errors": "",
        "text_hash": normalized_text_hash(text),
        "request_index": str(request_index),
        "scenario_id": scenario["scenario_id"],
        "phenomena": json_dumps(
            {
                "target_category": scenario["target_category"],
                "pii_type": scenario["pii_type"],
                "frame": scenario["frame"],
                "surface": scenario["surface"],
                "register": scenario["register"],
                "length_profile": scenario["length_profile"],
                "style_constraints": scenario["style_constraints"],
            }
        ),
        "llm_label_rationale": str(parsed.get("label_rationale", "") or "").strip(),
        "llm_privacy_rationale": str(parsed.get("privacy_rationale", "") or "").strip(),
        "expected_privacy_spans": json_dumps(pii_annotations),
        "expected_target_terms": json_dumps(target_annotations),
        "utility_cues": json_dumps(parsed.get("utility_cues", [])),
    }
    if errors:
        row["validation_status"] = "warn"
        row["validation_errors"] = json_dumps(errors)
    enrichment = local_enrichment(row)
    row["privacy_spans_json"] = json_dumps(enrichment["privacy_spans"])
    row["target_spans_json"] = json_dumps(enrichment["target_spans"])
    row["context_tags_json"] = json_dumps(enrichment["context_tags"])
    row["token_actions_json"] = json_dumps(enrichment["token_actions"])
    row["token_action_counts"] = json_dumps(enrichment["token_action_counts"])
    row["action_spans_json"] = json_dumps(enrichment["action_spans"])
    row["balanced_text"] = enrichment["balanced_text"]
    row["privacy_text"] = enrichment["privacy_text"]
    return row, errors


def status_payload(
    *,
    args: argparse.Namespace,
    started: float,
    existing_rows: int,
    written: int,
    duplicate_count: int,
    error_count: int,
    consecutive_errors: int,
    label_counts: Counter[str],
    category_counts: Counter[str],
    pii_counts: Counter[str],
    frame_counts: Counter[str],
    last_row_id: str | None,
) -> dict[str, Any]:
    elapsed = max(time.time() - started, 0.001)
    total_rows = existing_rows + written
    rows_per_hour = written / elapsed * 3600 if written else 0.0
    remaining = max(args.target_count - total_rows, 0)
    eta_hours = remaining / rows_per_hour if rows_per_hour > 0 else None
    return {
        "artifact_type": "synthetic_challenge_corpus_status",
        "output": str(args.output),
        "target_count": args.target_count,
        "existing_rows_at_start": existing_rows,
        "written_this_run": written,
        "total_rows_estimate": total_rows,
        "remaining_estimate": remaining,
        "duplicates_this_run": duplicate_count,
        "errors_this_run": error_count,
        "consecutive_errors": consecutive_errors,
        "rows_per_hour_this_run": round(rows_per_hour, 2),
        "eta_hours_at_current_rate": round(eta_hours, 2) if eta_hours is not None else None,
        "label_counts_this_run": dict(sorted(label_counts.items())),
        "target_category_counts_this_run": dict(sorted(category_counts.items())),
        "pii_type_counts_this_run": dict(sorted(pii_counts.items())),
        "frame_counts_this_run": dict(sorted(frame_counts.items())),
        "last_row_id": last_row_id,
        "runtime_seconds": round(elapsed, 2),
        "stop_requested": STOP_REQUESTED or args.stop_file.exists(),
        "warning": (
            "Synthetic data requires dedupe, label validation, distribution "
            "checks, and spot review before training."
        ),
    }


def main() -> int:
    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)
    args = parse_args()
    if args.target_count < 1:
        raise SystemExit("--target-count must be positive")

    rng = random.Random(args.seed)
    existing_hashes, existing_rows = read_existing_hashes(args.output) if args.resume else (set(), 0)
    csv_handle, writer = open_csv_writer(args.output, resume=args.resume)
    recent_signatures: deque[str] = deque(maxlen=max(args.recent_window, 1))
    started = time.time()
    written = 0
    duplicate_count = 0
    error_count = 0
    consecutive_errors = 0
    label_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    pii_counts: Counter[str] = Counter()
    frame_counts: Counter[str] = Counter()
    last_row_id: str | None = None

    try:
        request_index = existing_rows
        while existing_rows + written < args.target_count:
            if STOP_REQUESTED or args.stop_file.exists():
                break
            scenario = choose_scenario(request_index, rng)
            prompt = prompt_for_scenario(scenario, list(recent_signatures))
            payload = chat_payload(
                model=args.model,
                prompt=prompt,
                temperature=args.temperature,
            )
            try:
                response = post_chat_completion(
                    endpoint=args.endpoint,
                    payload=payload,
                    timeout=args.timeout,
                )
                raw_response = response_content(response)
                parsed = parse_json_object(raw_response)
                row, validation_errors = build_row(
                    parsed=parsed,
                    prompt=prompt,
                    raw_response=raw_response,
                    scenario=scenario,
                    request_index=request_index,
                    model=args.model,
                )
                if row["text_hash"] in existing_hashes:
                    duplicate_count += 1
                    recent_signatures.append(row["text"][:140].lower())
                    request_index += 1
                    consecutive_errors = 0
                    continue
                existing_hashes.add(row["text_hash"])
                writer.writerow(row)
                csv_handle.flush()
                written += 1
                consecutive_errors = 0
                last_row_id = row["id"]
                label_counts[row["label"]] += 1
                for category in clean_string_list(json.loads(row["target_categories"])):
                    category_counts[category] += 1
                pii_counts[scenario["pii_type"]] += 1
                frame_counts[scenario["frame"]] += 1
                signature = " ".join(row["text"].lower().split()[:18])
                recent_signatures.append(signature)
                if validation_errors:
                    append_error(
                        args.errors,
                        {
                            "type": "validation_warning",
                            "request_index": request_index,
                            "row_id": row["id"],
                            "errors": validation_errors,
                        },
                    )
            except Exception as exc:
                error_count += 1
                consecutive_errors += 1
                append_error(
                    args.errors,
                    {
                        "type": "generation_error",
                        "request_index": request_index,
                        "scenario": scenario,
                        "error": str(exc),
                    },
                )
                if consecutive_errors >= args.max_consecutive_errors:
                    break
                time.sleep(args.retry_sleep)
            request_index += 1
            if written and written % args.heartbeat_every == 0:
                status = status_payload(
                    args=args,
                    started=started,
                    existing_rows=existing_rows,
                    written=written,
                    duplicate_count=duplicate_count,
                    error_count=error_count,
                    consecutive_errors=consecutive_errors,
                    label_counts=label_counts,
                    category_counts=category_counts,
                    pii_counts=pii_counts,
                    frame_counts=frame_counts,
                    last_row_id=last_row_id,
                )
                write_json(args.status, status)
                print(json.dumps(status, ensure_ascii=False), flush=True)
    finally:
        status = status_payload(
            args=args,
            started=started,
            existing_rows=existing_rows,
            written=written,
            duplicate_count=duplicate_count,
            error_count=error_count,
            consecutive_errors=consecutive_errors,
            label_counts=label_counts,
            category_counts=category_counts,
            pii_counts=pii_counts,
            frame_counts=frame_counts,
            last_row_id=last_row_id,
        )
        write_json(args.status, status)
        write_json(args.report, status)
        csv_handle.close()
        print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)
    return 0 if consecutive_errors < args.max_consecutive_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
