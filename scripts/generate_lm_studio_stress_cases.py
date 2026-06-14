#!/usr/bin/env python3
"""Generate synthetic HSD privacy stress cases through LM Studio.

The output is intended for local coverage testing and candidate augmentation.
Generated examples are not automatically trusted training data.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import sys
import time
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contextsafe_hsd.detectors import detect_spans, target_group_spans
from contextsafe_hsd.pipeline import PrivatizerConfig, privatize_text
from contextsafe_hsd.presidio_augment import (
    PresidioAugmentError,
    filtered_presidio_spans,
    load_presidio_analyzer,
)


DEFAULT_ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
DEFAULT_MODEL = "gemma-4-e4b-uncensored-hauhaucs-aggressive"
DEFAULT_OUTPUT = Path("data/outputs/lm_studio_stress_cases.jsonl")
DEFAULT_REPORT = Path("data/outputs/lm_studio_stress_cases.report.json")
PHENOMENA = (
    "target_group_plain",
    "target_group_hashtag",
    "target_group_typo",
    "slur_variant",
    "person_name",
    "location_city",
    "location_street",
    "organization_or_school",
    "date_or_age",
    "handle_or_email",
    "sarcasm_or_emoji",
    "quoted_or_reported",
    "counterspeech",
    "public_interest_criticism",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Query an LM Studio OpenAI-compatible chat endpoint for structured "
            "synthetic privacy/HSD stress cases."
        )
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--batches", type=int, default=5)
    parser.add_argument("--cases-per-batch", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument(
        "--use-presidio",
        action="store_true",
        help="Run filtered Presidio spans while scoring generated cases.",
    )
    return parser.parse_args()


def prompt_messages(*, batch_index: int, cases_per_batch: int, seed: int) -> list[dict[str, str]]:
    rng = random.Random(seed + batch_index)
    sampled = rng.sample(PHENOMENA, k=min(len(PHENOMENA), 8))
    return [
        {
            "role": "system",
            "content": (
                "You create synthetic test rows for a privacy-preserving "
                "hate-speech-detection preprocessing system. The rows are for "
                "local safety testing, not publication. Use fictional people, "
                "handles, schools, organizations, and street names. Real city "
                "or country names are allowed. Include difficult social-media "
                "surface forms such as hashtags, typos, emoji, sarcasm, quotes, "
                "and target-group variants. Do not include instructions, threats "
                "of real-world violence, or real private personal data. Return "
                "only JSON."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "generate_structured_stress_cases",
                    "case_count": cases_per_batch,
                    "phenomena_to_cover": sampled,
                    "required_json_schema": {
                        "cases": [
                            {
                                "text": "string",
                                "phenomena": ["string"],
                                "expected_privacy_spans": [
                                    {"text": "string", "type": "PERSON|LOCATION|DATE|AGE|USER|EMAIL|ORG|ID"}
                                ],
                                "expected_target_terms": [
                                    {"text": "string", "category": "string"}
                                ],
                                "notes": "string",
                            }
                        ]
                    },
                    "constraints": {
                        "fictional_person_names": True,
                        "fictional_street_names": True,
                        "one_to_three_sentences": True,
                        "include_target_evidence": True,
                        "include_privacy_risk": True,
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]


def post_chat_completion(
    *,
    endpoint: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float,
) -> dict[str, Any]:
    payload_base = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
    }
    payloads = [
        {**payload_base, "response_format": {"type": "json_object"}},
        payload_base,
    ]
    errors: list[str] = []
    for payload in payloads:
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
            errors.append(f"HTTP {exc.code}: {detail or exc.reason}")
            if exc.code != 400:
                break
        except (OSError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
            break
    raise RuntimeError(f"LM Studio request failed: {'; '.join(errors)}")


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


def response_cases(response: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("model response did not contain message content") from exc
    value = parse_json_object(str(content))
    cases = value.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("model JSON missing cases list")
    return [case for case in cases if isinstance(case, dict) and str(case.get("text", "")).strip()]


def detected_summary(
    text: str,
    *,
    use_presidio: bool,
    presidio_analyzer: Any | None,
) -> tuple[dict[str, Any], str, str]:
    extra_spans = []
    presidio_report: dict[str, Any] = {"enabled": False}
    if use_presidio and presidio_analyzer is not None:
        try:
            extra_spans, presidio_report = filtered_presidio_spans(text, presidio_analyzer)
        except PresidioAugmentError as exc:
            presidio_report = {"enabled": False, "error": str(exc)}
    balanced = privatize_text(
        text,
        PrivatizerConfig(mode="balanced"),
        extra_spans=extra_spans,
    )
    privacy = privatize_text(
        text,
        PrivatizerConfig(mode="privacy"),
        extra_spans=extra_spans,
    )
    privacy_spans = detect_spans(text, include_context=True, include_targets=False)
    target_spans = target_group_spans(text)
    return (
        {
            "privacy_spans": [
                {
                    "text": span.text,
                    "type": span.entity_type,
                    "source": span.source,
                    "start": span.start,
                    "end": span.end,
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
            "presidio": presidio_report,
        },
        balanced.text,
        privacy.text,
    )


def expected_texts(items: Any) -> set[str]:
    if not isinstance(items, list):
        return set()
    values: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip().lower()
        if text:
            values.add(text)
    return values


def score_case(case: dict[str, Any], detected: dict[str, Any]) -> dict[str, Any]:
    expected_privacy = expected_texts(case.get("expected_privacy_spans"))
    expected_targets = expected_texts(case.get("expected_target_terms"))
    detected_privacy = {
        str(span["text"]).strip().lower()
        for span in detected["privacy_spans"]
    }
    detected_targets = {
        str(span["text"]).strip().lower()
        for span in detected["target_spans"]
    }
    return {
        "expected_privacy_count": len(expected_privacy),
        "expected_target_count": len(expected_targets),
        "missing_expected_privacy": sorted(expected_privacy - detected_privacy),
        "missing_expected_targets": sorted(expected_targets - detected_targets),
        "detected_privacy_count": len(detected_privacy),
        "detected_target_count": len(detected_targets),
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.batches < 1 or args.cases_per_batch < 1:
        raise SystemExit("--batches and --cases-per-batch must be positive")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    presidio_analyzer = load_presidio_analyzer() if args.use_presidio else None
    generated_count = 0
    status_counts: Counter[str] = Counter()
    missing_privacy_counts: Counter[str] = Counter()
    missing_target_counts: Counter[str] = Counter()
    started = time.time()

    with args.output.open("w", encoding="utf-8") as handle:
        for batch_index in range(args.batches):
            messages = prompt_messages(
                batch_index=batch_index,
                cases_per_batch=args.cases_per_batch,
                seed=args.seed,
            )
            try:
                response = post_chat_completion(
                    endpoint=args.endpoint,
                    model=args.model,
                    messages=messages,
                    timeout=args.timeout,
                )
                cases = response_cases(response)
            except Exception as exc:
                status_counts["batch_error"] += 1
                handle.write(
                    json.dumps(
                        {
                            "artifact_type": "lm_studio_stress_case_error",
                            "batch_index": batch_index,
                            "error": str(exc),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                continue

            for case_index, case in enumerate(cases):
                text = str(case.get("text", "")).strip()
                detected, balanced_text, privacy_text = detected_summary(
                    text,
                    use_presidio=args.use_presidio,
                    presidio_analyzer=presidio_analyzer,
                )
                score = score_case(case, detected)
                for value in score["missing_expected_privacy"]:
                    missing_privacy_counts[value] += 1
                for value in score["missing_expected_targets"]:
                    missing_target_counts[value] += 1
                status_counts["case_ok"] += 1
                generated_count += 1
                handle.write(
                    json.dumps(
                        {
                            "artifact_type": "lm_studio_stress_case",
                            "case_id": f"lmstress-{batch_index:04d}-{case_index:03d}",
                            "batch_index": batch_index,
                            "case_index": case_index,
                            "model": args.model,
                            "text": text,
                            "phenomena": case.get("phenomena", []),
                            "expected_privacy_spans": case.get("expected_privacy_spans", []),
                            "expected_target_terms": case.get("expected_target_terms", []),
                            "notes": case.get("notes", ""),
                            "detected": detected,
                            "balanced_text": balanced_text,
                            "privacy_text": privacy_text,
                            "score": score,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    report = {
        "artifact_type": "lm_studio_stress_case_report",
        "endpoint": args.endpoint,
        "model": args.model,
        "output": str(args.output),
        "batches": args.batches,
        "cases_per_batch": args.cases_per_batch,
        "generated_count": generated_count,
        "status_counts": dict(sorted(status_counts.items())),
        "top_missing_expected_privacy": missing_privacy_counts.most_common(25),
        "top_missing_expected_targets": missing_target_counts.most_common(25),
        "use_presidio": args.use_presidio,
        "runtime_seconds": round(time.time() - started, 4),
        "warning": (
            "Generated cases are synthetic stress tests. Do not treat them as "
            "trusted training data until deduplication, label validation, and "
            "distribution checks pass."
        ),
    }
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
