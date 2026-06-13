"""Optional role-aware token policy experiments.

The token policy model is advisory. It predicts token actions that can feed
review routing or candidate reranking, while deterministic privacy/cue checks
remain the final authority.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import ast
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys
import time
from typing import Any, Iterable

from .csv_pipeline import read_csv, write_csv, write_json
from .detectors import Span, detect_spans, target_group_spans
from .metrics import DIRECT_IDENTIFIER_TYPES, QUASI_IDENTIFIER_TYPES, UTILITY_CUES, row_metric
from .rationale_checks import parse_rationale_spans
from .resource_config import load_expected_source_labels
from .style import ACTION_TERMS, NEGATION_MODALITY_TERMS, scrub_style
from .token_actions import (
    ACTION_GENERALIZE,
    ACTION_KEEP,
    ACTION_MASK,
    ACTION_NORMALIZE,
    ACTION_PROTECT_HSD,
    ACTION_PROTECT_TARGET,
    TOKEN_PATTERN,
    phrase_spans,
    style_like,
)


ACTION_REVIEW = "REVIEW"
TOKEN_POLICY_ACTIONS = [
    ACTION_KEEP,
    ACTION_MASK,
    ACTION_GENERALIZE,
    ACTION_PROTECT_TARGET,
    ACTION_PROTECT_HSD,
    ACTION_NORMALIZE,
    ACTION_REVIEW,
]
TOKEN_POLICY_LABEL_TO_ID = {
    label: index for index, label in enumerate(TOKEN_POLICY_ACTIONS)
}
TOKEN_POLICY_ID_TO_LABEL = {
    index: label for label, index in TOKEN_POLICY_LABEL_TO_ID.items()
}
IGNORE_INDEX = -100
DEFAULT_MODEL_NAME = "FacebookAI/roberta-base"
DEFAULT_OUTPUT_DIR = Path("data/outputs/token_policy_roberta_base")
DEFAULT_TRAIN_REPORT = Path("data/outputs/token_policy_roberta_base.train.json")
DEFAULT_EVALUATE_REPORT = Path("data/outputs/token_policy_roberta_base.evaluate.json")
DEFAULT_PREDICTIONS = Path("data/outputs/token_policy_roberta_base.predictions.json")
DEFAULT_ENSEMBLE_EVALUATE_REPORT = Path(
    "data/outputs/token_policy_ensemble.evaluate.json"
)
DEFAULT_ENSEMBLE_PREDICTIONS = Path(
    "data/outputs/token_policy_ensemble.predictions.json"
)
DEFAULT_LABEL_FEATURE_REPORT = Path("data/outputs/recommended_merged.label_feature_report.json")
DEFAULT_SAMPLE_SIZE = 30000
DEFAULT_PREDICT_SAMPLE_SIZE = 1000
DEFAULT_MAX_LENGTH = 192
DEFAULT_BATCH_SIZE = 8
DEFAULT_EPOCHS = 1.0
DEFAULT_TEST_SIZE = 0.15
DEFAULT_SAMPLE_STRATEGY = "source_label_round_robin"
DEFAULT_SPLIT_STRATEGY = "grouped_text"
DEFAULT_CLASS_WEIGHTING = "capped_inverse_sqrt"
DEFAULT_MAX_CLASS_WEIGHT = 6.0
SAMPLE_STRATEGIES = {
    "first_n",
    "source_label_round_robin",
    "action_source_balanced",
}
SPLIT_STRATEGIES = {"random", "grouped_text"}
CLASS_WEIGHTING_MODES = {"none", "capped_inverse_sqrt"}
ENSEMBLE_MODES = {"mean_prob", "priority_vote"}
TOKEN_POLICY_METADATA = "token_policy_metadata.json"
TOKEN_POLICY_WARNING = (
    "This is a weakly supervised token-action policy experiment. It is not a "
    "legal hate-speech classifier, not a generative anonymizer, and not a "
    "replacement for deterministic validation/reranking."
)

EXPECTED_SOURCE_LABELS = load_expected_source_labels()
ADJACENT_REVIEW_LABELS = {
    "abuse",
    "ambiguous",
    "ambiguous_abuse",
    "not_abuse",
    "not_abusive",
    "offensive",
    "toxic",
}
CONTROL_TARGET_TERMS = {
    "all",
    "blank",
    "gender",
    "none",
    "notgiven",
    "null",
    "other",
    "race",
    "religion",
    "sexuality",
    "target",
    "unknown",
}
GENERIC_TARGET_PARTS = {
    "age",
    "disability",
    "gender",
    "identity",
    "origin",
    "race",
    "religion",
    "sexuality",
    "specific",
}
CONTEXT_REVIEW_TERMS = {
    "according",
    "allegedly",
    "quote",
    "quoted",
    "reported",
    "said",
    "says",
}
ACTION_PRIORITY = {
    ACTION_KEEP: 0,
    ACTION_NORMALIZE: 1,
    ACTION_GENERALIZE: 2,
    ACTION_PROTECT_HSD: 3,
    ACTION_PROTECT_TARGET: 4,
    ACTION_REVIEW: 5,
    ACTION_MASK: 6,
}
POLICY_BY_ACTION = {
    ACTION_KEEP: "neutral",
    ACTION_MASK: "mask_if_identifier",
    ACTION_GENERALIZE: "generalize",
    ACTION_PROTECT_TARGET: "protect",
    ACTION_PROTECT_HSD: "protect",
    ACTION_NORMALIZE: "normalize",
    ACTION_REVIEW: "review",
}


class TokenPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class ActionSpan:
    start: int
    end: int
    action: str
    reason: str
    score: float = 1.0


@dataclass(frozen=True)
class TokenPolicyExample:
    row_index: int
    row_id: str
    token_index: int
    token: str
    start: int
    end: int
    action: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RowProfile:
    index: int
    row_id: str
    source: str
    label: str
    text_key: str
    token_count: int
    action_counts: Counter[str]
    reason_counts: Counter[str]


def rounded(value: float) -> float:
    return round(float(value), 4)


def validate_columns(
    input_path: Path,
    fieldnames: list[str],
    *,
    text_col: str,
    id_col: str | None = None,
    source_col: str | None = None,
    label_col: str | None = None,
    target_col: str | None = None,
    target_categories_col: str | None = None,
    rationale_col: str | None = None,
) -> None:
    requested = [
        text_col,
        id_col,
        source_col,
        label_col,
        target_col,
        target_categories_col,
        rationale_col,
    ]
    missing = [column for column in requested if column and column not in fieldnames]
    if missing:
        raise TokenPolicyError(
            f"{input_path}: missing required column(s): {', '.join(missing)}"
        )


def validate_source_labels(
    rows: list[dict[str, str]],
    *,
    source_col: str | None,
    label_col: str | None,
    max_samples: int = 20,
) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    source_label_counts: dict[str, Counter[str]] = defaultdict(Counter)
    anomalies: list[dict[str, Any]] = []
    if not source_col or not label_col:
        return {
            "checked": False,
            "reason": "source_col_or_label_col_not_supplied",
            "source_counts": {},
            "label_counts": {},
            "source_label_counts": {},
            "anomaly_count": 0,
            "anomaly_samples": [],
        }
    for row_index, row in enumerate(rows, start=1):
        source = str(row.get(source_col, "") or "").strip()
        label = str(row.get(label_col, "") or "").strip()
        source_counts[source] += 1
        label_counts[label] += 1
        source_label_counts[source][label] += 1
        expected = EXPECTED_SOURCE_LABELS.get(source)
        if not source or not label or expected is None or label not in expected:
            if len(anomalies) < max_samples:
                anomalies.append(
                    {
                        "row_index": row_index,
                        "row_id": row.get("id", row_index),
                        "source": source,
                        "label": label,
                        "reason": (
                            "missing_source_or_label"
                            if not source or not label
                            else "unexpected_source_label_pair"
                        ),
                    }
                )
    return {
        "checked": True,
        "source_counts": dict(sorted(source_counts.items())),
        "label_counts": dict(sorted(label_counts.items())),
        "source_label_counts": {
            source: dict(sorted(counter.items()))
            for source, counter in sorted(source_label_counts.items())
        },
        "anomaly_count": sum(
            1
            for source, counter in source_label_counts.items()
            for label, count in counter.items()
            if source not in EXPECTED_SOURCE_LABELS
            or label not in EXPECTED_SOURCE_LABELS[source]
            for _ in range(count)
        ),
        "anomaly_samples": anomalies,
    }


def parse_list_like(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    parsed: Any | None = None
    if text[:1] in "[{\"'":
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(text)
                break
            except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
                continue
    values: list[str] = []
    if parsed is None:
        values = re.split(r"[;,|]", text)
    elif isinstance(parsed, dict):
        values = list(parsed.values())
    elif isinstance(parsed, (list, tuple, set)):
        values = [str(item) for item in parsed]
    else:
        values = [str(parsed)]
    cleaned: list[str] = []
    for value_item in values:
        item = str(value_item or "").strip().strip("\"'")
        if item:
            cleaned.append(item)
    return cleaned


def target_metadata_terms(*values: str) -> set[str]:
    terms: set[str] = set()
    for value in values:
        for item in parse_list_like(value):
            normalized = re.sub(r"\s+", " ", item.strip())
            lowered = normalized.lower()
            if not lowered or lowered in CONTROL_TARGET_TERMS:
                continue
            if "_" in lowered:
                parts = [
                    part
                    for part in re.split(r"[_\s]+", lowered)
                    if part and part not in GENERIC_TARGET_PARTS
                ]
                for part in parts:
                    if len(part) >= 3 and part not in CONTROL_TARGET_TERMS:
                        terms.add(part)
                continue
            if len(lowered) >= 3:
                terms.add(normalized)
    return terms


def literal_spans(text: str, terms: Iterable[str], *, action: str, reason: str) -> list[ActionSpan]:
    spans: list[ActionSpan] = []
    for term in sorted({term for term in terms if term}, key=len, reverse=True):
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)
        for match in pattern.finditer(text):
            spans.append(ActionSpan(match.start(), match.end(), action, reason))
    return spans


def hsd_phrase_spans(text: str) -> list[ActionSpan]:
    hsd_phrases = (
        {cue.lower() for cue in UTILITY_CUES}
        | {term.lower() for term in ACTION_TERMS}
        | {term.lower() for term in NEGATION_MODALITY_TERMS}
        | CONTEXT_REVIEW_TERMS
    )
    return [
        ActionSpan(start, end, ACTION_PROTECT_HSD, "hsd_or_context_cue")
        for start, end in phrase_spans(text, hsd_phrases)
    ]


def self_disclosure_target_spans(text: str, spans: list[Span]) -> list[ActionSpan]:
    review_spans: list[ActionSpan] = []
    for span in spans:
        prefix = text[max(0, span.start - 35) : span.start].lower()
        if re.search(r"(?:^|\b)(?:i am|i'm|im|as a|as an|we are|we're|my identity is)\s+(?:a|an)?\s*$", prefix):
            review_spans.append(
                ActionSpan(
                    span.start,
                    span.end,
                    ACTION_REVIEW,
                    "author_self_disclosure_target",
                )
            )
    return review_spans


def weak_action_spans_for_row(
    row: dict[str, str],
    *,
    text_col: str,
    source_col: str | None = None,
    target_col: str | None = None,
    target_categories_col: str | None = None,
    rationale_col: str | None = None,
) -> list[ActionSpan]:
    text = str(row.get(text_col, "") or "")
    spans: list[ActionSpan] = []
    identifier_spans = detect_spans(text, include_context=True, include_targets=False)
    for span in identifier_spans:
        if span.entity_type in DIRECT_IDENTIFIER_TYPES:
            spans.append(ActionSpan(span.start, span.end, ACTION_MASK, "direct_identifier"))
        elif span.entity_type in QUASI_IDENTIFIER_TYPES:
            spans.append(
                ActionSpan(span.start, span.end, ACTION_GENERALIZE, "quasi_identifier")
            )
        else:
            spans.append(ActionSpan(span.start, span.end, ACTION_MASK, "identifier"))

    target_spans = target_group_spans(text)
    for span in target_spans:
        spans.append(ActionSpan(span.start, span.end, ACTION_PROTECT_TARGET, "target_dictionary"))
    spans.extend(self_disclosure_target_spans(text, target_spans))

    metadata_terms = target_metadata_terms(
        row.get(target_col, "") if target_col else "",
        row.get(target_categories_col, "") if target_categories_col else "",
    )
    spans.extend(
        literal_spans(
            text,
            metadata_terms,
            action=ACTION_PROTECT_TARGET,
            reason="target_metadata",
        )
    )
    spans.extend(hsd_phrase_spans(text))

    if rationale_col and source_col:
        rationale_spans = parse_rationale_spans(
            source=str(row.get(source_col, "") or ""),
            raw_value=str(row.get(rationale_col, "") or ""),
            text=text,
        )
        for span in rationale_spans:
            spans.append(ActionSpan(span.start, span.end, ACTION_PROTECT_HSD, "rationale_span"))

    for match in TOKEN_PATTERN.finditer(text):
        if style_like(match.group(0)):
            spans.append(
                ActionSpan(
                    match.start(),
                    match.end(),
                    ACTION_NORMALIZE,
                    "style_marker",
                )
            )
    return [
        span
        for span in spans
        if 0 <= span.start < span.end <= len(text) and span.action in TOKEN_POLICY_LABEL_TO_ID
    ]


def strongest_action(spans: list[ActionSpan]) -> str:
    if not spans:
        return ACTION_KEEP
    return max(spans, key=lambda span: ACTION_PRIORITY[span.action]).action


def strongest_reasons(spans: list[ActionSpan], action: str) -> tuple[str, ...]:
    return tuple(sorted({span.reason for span in spans if span.action == action}))


def overlaps(start: int, end: int, span_start: int, span_end: int) -> bool:
    return start < span_end and end > span_start


def token_examples_for_row(
    row: dict[str, str],
    *,
    row_index: int,
    text_col: str,
    id_col: str | None = None,
    source_col: str | None = None,
    target_col: str | None = None,
    target_categories_col: str | None = None,
    rationale_col: str | None = None,
) -> list[TokenPolicyExample]:
    text = str(row.get(text_col, "") or "")
    row_id = str(row.get(id_col, "") or row_index) if id_col else str(row_index)
    spans = weak_action_spans_for_row(
        row,
        text_col=text_col,
        source_col=source_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    examples: list[TokenPolicyExample] = []
    for token_index, match in enumerate(TOKEN_PATTERN.finditer(text), start=1):
        token_spans = [
            span
            for span in spans
            if overlaps(match.start(), match.end(), span.start, span.end)
        ]
        action = strongest_action(token_spans)
        examples.append(
            TokenPolicyExample(
                row_index=row_index,
                row_id=row_id,
                token_index=token_index,
                token=match.group(0),
                start=match.start(),
                end=match.end(),
                action=action,
                reasons=strongest_reasons(token_spans, action),
            )
        )
    return examples


def metadata_prefix_for_row(
    row: dict[str, str],
    *,
    source_col: str | None,
    label_col: str | None,
    target_col: str | None,
) -> str:
    parts: list[str] = []
    if source_col:
        source = str(row.get(source_col, "") or "").strip()
        if source:
            parts.append(f"<source={source}>")
    if label_col:
        label = str(row.get(label_col, "") or "").strip()
        if label:
            parts.append(f"<label={label}>")
    if target_col:
        target = str(row.get(target_col, "") or "").strip()
        if target:
            safe_target = re.sub(r"\s+", "_", target)[:80]
            parts.append(f"<target={safe_target}>")
    if not parts:
        return ""
    return " ".join(parts) + " "


def model_input_for_row(
    row: dict[str, str],
    *,
    text_col: str,
    source_col: str | None,
    label_col: str | None,
    target_col: str | None,
    metadata_prefix: bool,
) -> tuple[str, int]:
    text = str(row.get(text_col, "") or "")
    prefix = (
        metadata_prefix_for_row(
            row,
            source_col=source_col,
            label_col=label_col,
            target_col=target_col,
        )
        if metadata_prefix
        else ""
    )
    return prefix + text, len(prefix)


def label_for_offset(
    start: int,
    end: int,
    *,
    text_start: int,
    action_spans: list[ActionSpan],
) -> int:
    if start == end:
        return IGNORE_INDEX
    if end <= text_start:
        return IGNORE_INDEX
    original_start = max(0, start - text_start)
    original_end = max(0, end - text_start)
    overlapping = [
        span
        for span in action_spans
        if overlaps(original_start, original_end, span.start, span.end)
    ]
    action = strongest_action(overlapping)
    return TOKEN_POLICY_LABEL_TO_ID[action]


def align_labels_to_offsets(
    offsets: list[tuple[int, int]],
    *,
    text_start: int,
    action_spans: list[ActionSpan],
) -> list[int]:
    return [
        label_for_offset(start, end, text_start=text_start, action_spans=action_spans)
        for start, end in offsets
    ]


def normalized_text_key(text: str) -> str:
    normalized = " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))
    if not normalized:
        normalized = "<blank>"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def row_profile(
    rows: list[dict[str, str]],
    index: int,
    *,
    text_col: str,
    id_col: str | None,
    source_col: str | None,
    label_col: str | None,
    target_col: str | None,
    target_categories_col: str | None,
    rationale_col: str | None,
) -> RowProfile:
    row = rows[index]
    examples = token_examples_for_row(
        row,
        row_index=index + 1,
        text_col=text_col,
        id_col=id_col,
        source_col=source_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    action_counts = Counter(example.action for example in examples)
    reason_counts: Counter[str] = Counter()
    for example in examples:
        reason_counts.update(example.reasons)
    return RowProfile(
        index=index,
        row_id=str(row.get(id_col, "") or index + 1) if id_col else str(index + 1),
        source=str(row.get(source_col, "") or "") if source_col else "",
        label=str(row.get(label_col, "") or "") if label_col else "",
        text_key=normalized_text_key(str(row.get(text_col, "") or "")),
        token_count=len(examples),
        action_counts=action_counts,
        reason_counts=reason_counts,
    )


def row_priority_actions(profile: RowProfile) -> list[str]:
    priority = [
        ACTION_REVIEW,
        ACTION_GENERALIZE,
        ACTION_MASK,
        ACTION_PROTECT_TARGET,
        ACTION_PROTECT_HSD,
        ACTION_NORMALIZE,
    ]
    actions = [action for action in priority if profile.action_counts.get(action, 0)]
    return actions or [ACTION_KEEP]


def action_source_balanced_indices(
    rows: list[dict[str, str]],
    *,
    sample_size: int,
    text_col: str,
    id_col: str | None,
    source_col: str | None,
    label_col: str | None,
    target_col: str | None,
    target_categories_col: str | None,
    rationale_col: str | None,
) -> tuple[list[int], dict[str, Any]]:
    profiles: list[RowProfile] = []
    for index in range(len(rows)):
        profile = row_profile(
            rows,
            index,
            text_col=text_col,
            id_col=id_col,
            source_col=source_col,
            label_col=label_col,
            target_col=target_col,
            target_categories_col=target_categories_col,
            rationale_col=rationale_col,
        )
        profiles.append(profile)

    buckets: dict[tuple[str, str], list[RowProfile]] = defaultdict(list)
    for profile in profiles:
        for action in row_priority_actions(profile):
            buckets[(action, f"{profile.source}\t{profile.label}")].append(profile)

    selected: list[int] = []
    selected_set: set[int] = set()
    selected_action_rows: Counter[str] = Counter()
    selected_action_tokens: Counter[str] = Counter()
    selected_reason_rows: Counter[str] = Counter()
    action_order = [
        ACTION_REVIEW,
        ACTION_GENERALIZE,
        ACTION_MASK,
        ACTION_PROTECT_TARGET,
        ACTION_PROTECT_HSD,
        ACTION_NORMALIZE,
        ACTION_KEEP,
    ]
    source_label_keys = sorted(
        {
            f"{profile.source}\t{profile.label}"
            for profile in profiles
        }
    )
    rounds_without_add = 0
    while len(selected) < sample_size and rounds_without_add < len(action_order) * max(1, len(source_label_keys)):
        added_this_round = False
        for action in action_order:
            for source_label in source_label_keys:
                bucket = buckets.get((action, source_label), [])
                while bucket and bucket[0].index in selected_set:
                    bucket.pop(0)
                if not bucket:
                    continue
                profile = bucket.pop(0)
                if profile.index in selected_set:
                    continue
                selected.append(profile.index)
                selected_set.add(profile.index)
                added_this_round = True
                for row_action, count in profile.action_counts.items():
                    if count:
                        selected_action_rows[row_action] += 1
                        selected_action_tokens[row_action] += count
                selected_reason_rows.update(profile.reason_counts)
                if len(selected) >= sample_size:
                    break
            if len(selected) >= sample_size:
                break
        if added_this_round:
            rounds_without_add = 0
        else:
            rounds_without_add += 1

    if len(selected) < sample_size:
        for profile in profiles:
            if profile.index in selected_set:
                continue
            selected.append(profile.index)
            selected_set.add(profile.index)
            for row_action, count in profile.action_counts.items():
                if count:
                    selected_action_rows[row_action] += 1
                    selected_action_tokens[row_action] += count
            selected_reason_rows.update(profile.reason_counts)
            if len(selected) >= sample_size:
                break

    full_action_rows: Counter[str] = Counter()
    full_action_tokens: Counter[str] = Counter()
    source_label_counts: Counter[str] = Counter()
    duplicate_text_groups: Counter[str] = Counter()
    for profile in profiles:
        source_label_counts[f"{profile.source}\t{profile.label}"] += 1
        duplicate_text_groups[profile.text_key] += 1
        for action, count in profile.action_counts.items():
            if count:
                full_action_rows[action] += 1
                full_action_tokens[action] += count

    selected_source_label_counts = Counter(
        f"{profiles[index].source}\t{profiles[index].label}" for index in selected
    )
    report = {
        "strategy": "action_source_balanced",
        "profiled_rows": len(profiles),
        "selected_rows": len(selected),
        "full_action_row_counts": dict(sorted(full_action_rows.items())),
        "full_action_token_counts": dict(sorted(full_action_tokens.items())),
        "selected_action_row_counts": dict(sorted(selected_action_rows.items())),
        "selected_action_token_counts": dict(sorted(selected_action_tokens.items())),
        "selected_reason_row_counts": dict(sorted(selected_reason_rows.items())),
        "full_source_label_counts": dict(sorted(source_label_counts.items())),
        "selected_source_label_counts": dict(sorted(selected_source_label_counts.items())),
        "duplicate_normalized_text_groups": sum(
            1 for count in duplicate_text_groups.values() if count > 1
        ),
    }
    return selected[:sample_size], report


def source_label_counts(
    rows: list[dict[str, str]],
    indices: list[int],
    *,
    source_col: str | None,
    label_col: str | None,
) -> dict[str, int]:
    if not source_col or not label_col:
        return {}
    counts = Counter(
        f"{rows[index].get(source_col, '')}\t{rows[index].get(label_col, '')}"
        for index in indices
    )
    return dict(sorted(counts.items()))


def sample_row_indices_with_report(
    rows: list[dict[str, str]],
    *,
    sample_size: int,
    strategy: str,
    text_col: str,
    id_col: str | None = None,
    source_col: str | None,
    label_col: str | None,
    target_col: str | None = None,
    target_categories_col: str | None = None,
    rationale_col: str | None = None,
) -> tuple[list[int], dict[str, Any]]:
    if sample_size < 0:
        raise TokenPolicyError("--sample-size must be non-negative")
    if strategy not in SAMPLE_STRATEGIES:
        raise TokenPolicyError(
            f"unknown sample strategy {strategy!r}; expected one of {sorted(SAMPLE_STRATEGIES)}"
        )
    if sample_size == 0 or sample_size >= len(rows):
        indices = list(range(len(rows)))
        return indices, {
            "strategy": strategy,
            "selected_rows": len(indices),
            "source_label_counts": source_label_counts(
                rows,
                indices,
                source_col=source_col,
                label_col=label_col,
            ),
        }
    if strategy == "action_source_balanced":
        return action_source_balanced_indices(
            rows,
            sample_size=sample_size,
            text_col=text_col,
            id_col=id_col,
            source_col=source_col,
            label_col=label_col,
            target_col=target_col,
            target_categories_col=target_categories_col,
            rationale_col=rationale_col,
        )
    if strategy == "first_n" or not source_col or not label_col:
        indices = list(range(sample_size))
        return indices, {
            "strategy": strategy,
            "selected_rows": len(indices),
            "source_label_counts": source_label_counts(
                rows,
                indices,
                source_col=source_col,
                label_col=label_col,
            ),
        }

    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[
            (
                str(row.get(source_col, "") or ""),
                str(row.get(label_col, "") or ""),
            )
        ].append(index)
    keys = sorted(groups)
    selected: list[int] = []
    position = 0
    while len(selected) < sample_size and keys:
        key = keys[position % len(keys)]
        group = groups[key]
        if group:
            selected.append(group.pop(0))
        if not group:
            keys.remove(key)
            if not keys:
                break
            position %= len(keys)
            continue
        position += 1
    return selected[:sample_size], {
        "strategy": strategy,
        "selected_rows": len(selected[:sample_size]),
        "source_label_counts": source_label_counts(
            rows,
            selected[:sample_size],
            source_col=source_col,
            label_col=label_col,
        ),
    }


def sample_row_indices(
    rows: list[dict[str, str]],
    *,
    sample_size: int,
    strategy: str,
    source_col: str | None,
    label_col: str | None,
    text_col: str = "text",
    id_col: str | None = None,
    target_col: str | None = None,
    target_categories_col: str | None = None,
    rationale_col: str | None = None,
) -> list[int]:
    indices, _report = sample_row_indices_with_report(
        rows,
        sample_size=sample_size,
        strategy=strategy,
        text_col=text_col,
        id_col=id_col,
        source_col=source_col,
        label_col=label_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    return indices


def split_indices(indices: list[int], *, test_size: float, random_state: int) -> tuple[list[int], list[int]]:
    if not 0 < test_size < 1:
        raise TokenPolicyError("--test-size must be greater than 0 and less than 1")
    if len(indices) < 2:
        raise TokenPolicyError("token-policy training requires at least two sampled rows")
    shuffled = list(indices)
    random.Random(random_state).shuffle(shuffled)
    dev_count = max(1, math.ceil(len(shuffled) * test_size))
    train_count = len(shuffled) - dev_count
    if train_count < 1:
        raise TokenPolicyError("--test-size creates an empty train split")
    return shuffled[dev_count:], shuffled[:dev_count]


def split_indices_with_report(
    rows: list[dict[str, str]],
    indices: list[int],
    *,
    text_col: str,
    test_size: float,
    random_state: int,
    strategy: str,
) -> tuple[list[int], list[int], dict[str, Any]]:
    if strategy not in SPLIT_STRATEGIES:
        raise TokenPolicyError(
            f"unknown split strategy {strategy!r}; expected one of {sorted(SPLIT_STRATEGIES)}"
        )
    if strategy == "random":
        train_indices, dev_indices = split_indices(
            indices,
            test_size=test_size,
            random_state=random_state,
        )
        return train_indices, dev_indices, {
            "strategy": strategy,
            "duplicate_group_overlap_count": None,
        }
    if not 0 < test_size < 1:
        raise TokenPolicyError("--test-size must be greater than 0 and less than 1")
    if len(indices) < 2:
        raise TokenPolicyError("token-policy training requires at least two sampled rows")

    groups: dict[str, list[int]] = defaultdict(list)
    for index in indices:
        groups[normalized_text_key(str(rows[index].get(text_col, "") or ""))].append(index)
    group_items = list(groups.items())
    random.Random(random_state).shuffle(group_items)
    target_dev_count = max(1, math.ceil(len(indices) * test_size))
    dev_indices: list[int] = []
    train_indices: list[int] = []
    for _text_key, group_indices in group_items:
        if len(dev_indices) < target_dev_count:
            dev_indices.extend(group_indices)
        else:
            train_indices.extend(group_indices)
    if not train_indices:
        train_indices, dev_indices = split_indices(
            indices,
            test_size=test_size,
            random_state=random_state,
        )
        return train_indices, dev_indices, {
            "strategy": "random_fallback",
            "duplicate_group_overlap_count": None,
        }
    train_keys = {
        normalized_text_key(str(rows[index].get(text_col, "") or ""))
        for index in train_indices
    }
    dev_keys = {
        normalized_text_key(str(rows[index].get(text_col, "") or ""))
        for index in dev_indices
    }
    duplicate_groups = sum(1 for group_indices in groups.values() if len(group_indices) > 1)
    return train_indices, dev_indices, {
        "strategy": strategy,
        "group_count": len(groups),
        "duplicate_group_count": duplicate_groups,
        "duplicate_group_overlap_count": len(train_keys & dev_keys),
    }


def grouped_kfold_indices_with_report(
    rows: list[dict[str, str]],
    indices: list[int],
    *,
    text_col: str,
    fold_count: int,
    fold_index: int,
    random_state: int,
    source_col: str | None = None,
    label_col: str | None = None,
) -> tuple[list[int], list[int], dict[str, Any]]:
    if fold_count < 2:
        raise TokenPolicyError("--fold-count must be at least 2")
    if fold_index < 0 or fold_index >= fold_count:
        raise TokenPolicyError("--fold-index must be in [0, fold-count)")
    if len(indices) < fold_count:
        raise TokenPolicyError("--fold-count cannot exceed sampled row count")

    groups: dict[str, list[int]] = defaultdict(list)
    for index in indices:
        groups[normalized_text_key(str(rows[index].get(text_col, "") or ""))].append(index)
    if len(groups) < fold_count:
        raise TokenPolicyError(
            "--fold-count cannot exceed distinct normalized text group count"
        )

    group_items = list(groups.items())
    rng = random.Random(random_state)
    rng.shuffle(group_items)
    group_items.sort(key=lambda item: len(item[1]), reverse=True)

    folds: list[list[int]] = [[] for _ in range(fold_count)]
    fold_keys: list[set[str]] = [set() for _ in range(fold_count)]
    for text_key, group_indices in group_items:
        target_fold = min(range(fold_count), key=lambda index: (len(folds[index]), index))
        folds[target_fold].extend(group_indices)
        fold_keys[target_fold].add(text_key)

    dev_indices = list(folds[fold_index])
    train_indices = [
        row_index
        for current_fold, fold_indices in enumerate(folds)
        if current_fold != fold_index
        for row_index in fold_indices
    ]
    if not train_indices or not dev_indices:
        raise TokenPolicyError("--fold-count produced an empty train or dev split")

    train_keys = set().union(
        *[fold_keys[index] for index in range(fold_count) if index != fold_index]
    )
    dev_keys = fold_keys[fold_index]
    duplicate_groups = sum(1 for group_indices in groups.values() if len(group_indices) > 1)
    return train_indices, dev_indices, {
        "strategy": "grouped_text_kfold",
        "group_count": len(groups),
        "duplicate_group_count": duplicate_groups,
        "duplicate_group_overlap_count": len(train_keys & dev_keys),
        "fold_count": fold_count,
        "fold_index": fold_index,
        "fold_sizes": [len(fold_indices) for fold_indices in folds],
        "fold_group_counts": [len(keys) for keys in fold_keys],
        "train_folds": [
            index for index in range(fold_count) if index != fold_index
        ],
        "dev_fold": fold_index,
        "fold_source_label_counts": [
            source_label_counts(
                rows,
                fold_indices,
                source_col=source_col,
                label_col=label_col,
            )
            for fold_indices in folds
        ],
    }


def load_transformer_stack() -> dict[str, Any]:
    try:
        import torch
        from torch.utils.data import DataLoader
        from transformers import AutoConfig, AutoModelForTokenClassification, AutoTokenizer
    except ModuleNotFoundError as exc:
        if exc.name in {"torch", "transformers"}:
            raise TokenPolicyError(
                "Install optional token-policy dependencies with: "
                "python -m pip install '.[token-policy]'"
            ) from exc
        raise
    return {
        "torch": torch,
        "DataLoader": DataLoader,
        "AutoConfig": AutoConfig,
        "AutoModelForTokenClassification": AutoModelForTokenClassification,
        "AutoTokenizer": AutoTokenizer,
    }


def build_class_weights(
    torch: Any,
    action_counts: Counter[str],
    *,
    mode: str,
    max_class_weight: float,
    device: str,
) -> Any | None:
    if mode not in CLASS_WEIGHTING_MODES:
        raise TokenPolicyError(
            f"unknown class weighting mode {mode!r}; expected one of {sorted(CLASS_WEIGHTING_MODES)}"
        )
    if mode == "none":
        return None
    if max_class_weight < 1:
        raise TokenPolicyError("--max-class-weight must be at least 1")
    nonzero_counts = [count for count in action_counts.values() if count > 0]
    if not nonzero_counts:
        return None
    max_count = max(nonzero_counts)
    weights: list[float] = []
    for action in TOKEN_POLICY_ACTIONS:
        count = action_counts.get(action, 0)
        if count <= 0:
            weights.append(0.0)
            continue
        weights.append(min(max_class_weight, math.sqrt(max_count / count)))
    return torch.tensor(weights, dtype=torch.float, device=device)


def class_weight_report(class_weights: Any | None) -> dict[str, float] | None:
    if class_weights is None:
        return None
    values = class_weights.detach().cpu().tolist()
    return {
        action: rounded(values[index])
        for index, action in enumerate(TOKEN_POLICY_ACTIONS)
    }


def token_loss(
    torch: Any,
    logits: Any,
    labels: Any,
    class_weights: Any | None,
) -> Any:
    loss_fn = torch.nn.CrossEntropyLoss(
        weight=class_weights,
        ignore_index=IGNORE_INDEX,
    )
    return loss_fn(logits.view(-1, logits.shape[-1]), labels.view(-1))


def encode_row(
    row: dict[str, str],
    *,
    tokenizer: Any,
    text_col: str,
    source_col: str | None,
    label_col: str | None,
    target_col: str | None,
    target_categories_col: str | None,
    rationale_col: str | None,
    max_length: int,
    metadata_prefix: bool,
) -> tuple[dict[str, list[int]], Counter[str], Counter[str]]:
    input_text, text_start = model_input_for_row(
        row,
        text_col=text_col,
        source_col=source_col,
        label_col=label_col,
        target_col=target_col,
        metadata_prefix=metadata_prefix,
    )
    action_spans = weak_action_spans_for_row(
        row,
        text_col=text_col,
        source_col=source_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    encoded = tokenizer(
        input_text,
        truncation=True,
        padding="max_length",
        max_length=max_length,
        return_offsets_mapping=True,
    )
    offsets = [tuple(offset) for offset in encoded.pop("offset_mapping")]
    labels = align_labels_to_offsets(
        offsets,
        text_start=text_start,
        action_spans=action_spans,
    )
    encoded["labels"] = labels
    action_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for label_id in labels:
        if label_id == IGNORE_INDEX:
            continue
        action_counts[TOKEN_POLICY_ID_TO_LABEL[label_id]] += 1
    for span in action_spans:
        reason_counts[span.reason] += 1
    return encoded, action_counts, reason_counts


def collate_batch(torch: Any, batch: list[dict[str, list[int]]]) -> dict[str, Any]:
    keys = ["input_ids", "attention_mask", "labels"]
    return {
        key: torch.tensor([item[key] for item in batch], dtype=torch.long)
        for key in keys
        if key in batch[0]
    }


def prediction_metrics(
    true_labels: list[int],
    predicted_labels: list[int],
) -> dict[str, Any]:
    classes = list(range(len(TOKEN_POLICY_ACTIONS)))
    matrix = [[0 for _ in classes] for _ in classes]
    for true_label, predicted_label in zip(true_labels, predicted_labels):
        matrix[true_label][predicted_label] += 1
    per_action: dict[str, Any] = {}
    f1_values: list[float] = []
    correct = 0
    for class_id in classes:
        label = TOKEN_POLICY_ID_TO_LABEL[class_id]
        tp = matrix[class_id][class_id]
        fp = sum(matrix[row][class_id] for row in classes if row != class_id)
        fn = sum(matrix[class_id][col] for col in classes if col != class_id)
        support = sum(matrix[class_id])
        correct += tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1_values.append(f1)
        per_action[label] = {
            "precision": rounded(precision),
            "recall": rounded(recall),
            "f1": rounded(f1),
            "support": support,
        }
    total = len(true_labels)
    return {
        "token_count": total,
        "accuracy": rounded(correct / total) if total else 0.0,
        "macro_f1": rounded(sum(f1_values) / len(f1_values)) if f1_values else 0.0,
        "per_action": per_action,
        "confusion_matrix": {
            "labels": TOKEN_POLICY_ACTIONS,
            "matrix": matrix,
        },
        "label_counts": {
            TOKEN_POLICY_ID_TO_LABEL[label_id]: true_labels.count(label_id)
            for label_id in classes
        },
        "prediction_counts": {
            TOKEN_POLICY_ID_TO_LABEL[label_id]: predicted_labels.count(label_id)
            for label_id in classes
        },
    }


def evaluate_token_model(
    *,
    torch: Any,
    data_loader: Any,
    model: Any,
    device: str,
) -> dict[str, Any]:
    model.eval()
    true_labels: list[int] = []
    predicted_labels: list[int] = []
    losses: list[float] = []
    with torch.no_grad():
        for batch in data_loader:
            batch = {key: value.to(device) for key, value in batch.items()}
            outputs = model(**batch)
            losses.append(float(outputs.loss.detach().cpu()))
            predictions = outputs.logits.argmax(dim=-1).detach().cpu().tolist()
            labels = batch["labels"].detach().cpu().tolist()
            for row_labels, row_predictions in zip(labels, predictions):
                for label_id, prediction_id in zip(row_labels, row_predictions):
                    if label_id == IGNORE_INDEX:
                        continue
                    true_labels.append(int(label_id))
                    predicted_labels.append(int(prediction_id))
    metrics = prediction_metrics(true_labels, predicted_labels)
    metrics["loss"] = rounded(sum(losses) / len(losses)) if losses else 0.0
    return metrics


def train_token_policy(
    input_path: Path,
    *,
    text_col: str,
    id_col: str | None = None,
    source_col: str | None = "source",
    label_col: str | None = "label",
    target_col: str | None = "target",
    target_categories_col: str | None = "target_categories",
    rationale_col: str | None = "rationale_spans",
    model_name: str = DEFAULT_MODEL_NAME,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    report_path: Path | None = DEFAULT_TRAIN_REPORT,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    sample_strategy: str = DEFAULT_SAMPLE_STRATEGY,
    max_length: int = DEFAULT_MAX_LENGTH,
    epochs: float = DEFAULT_EPOCHS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    learning_rate: float = 5e-5,
    weight_decay: float = 0.01,
    test_size: float = DEFAULT_TEST_SIZE,
    random_state: int = 13,
    split_strategy: str = DEFAULT_SPLIT_STRATEGY,
    fold_count: int = 0,
    fold_index: int | None = None,
    class_weighting: str = DEFAULT_CLASS_WEIGHTING,
    max_class_weight: float = DEFAULT_MAX_CLASS_WEIGHT,
    device: str = "auto",
    metadata_prefix: bool = True,
    log_steps: int = 25,
    max_train_steps: int | None = None,
) -> dict[str, Any]:
    if max_length < 8:
        raise TokenPolicyError("--max-length must be at least 8")
    if batch_size < 1:
        raise TokenPolicyError("--batch-size must be at least 1")
    if epochs <= 0:
        raise TokenPolicyError("--epochs must be positive")
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        source_col=source_col,
        label_col=label_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    label_integrity = validate_source_labels(
        rows,
        source_col=source_col,
        label_col=label_col,
    )
    if label_integrity["anomaly_count"]:
        raise TokenPolicyError(
            "unexpected source/label pairs; inspect anomaly_samples in a profile "
            "or use source-aware normalization before training"
        )

    selected_indices, sample_report = sample_row_indices_with_report(
        rows,
        sample_size=sample_size,
        strategy=sample_strategy,
        text_col=text_col,
        id_col=id_col,
        source_col=source_col,
        label_col=label_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    effective_split_strategy = split_strategy
    if fold_count:
        if split_strategy != "grouped_text":
            raise TokenPolicyError(
                "--fold-count uses grouped_text splits; set --split-strategy grouped_text"
            )
        if fold_index is None:
            fold_index = 0
        train_indices, dev_indices, split_report = grouped_kfold_indices_with_report(
            rows,
            selected_indices,
            text_col=text_col,
            fold_count=fold_count,
            fold_index=fold_index,
            random_state=random_state,
            source_col=source_col,
            label_col=label_col,
        )
        effective_split_strategy = "grouped_text_kfold"
    else:
        train_indices, dev_indices, split_report = split_indices_with_report(
            rows,
            selected_indices,
            text_col=text_col,
            test_size=test_size,
            random_state=random_state,
            strategy=split_strategy,
        )
    stack = load_transformer_stack()
    torch = stack["torch"]
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = stack["AutoTokenizer"].from_pretrained(model_name, use_fast=True)
    if not getattr(tokenizer, "is_fast", False):
        raise TokenPolicyError(
            f"{model_name}: fast tokenizer is required for offset alignment"
        )
    config = stack["AutoConfig"].from_pretrained(
        model_name,
        num_labels=len(TOKEN_POLICY_ACTIONS),
        id2label=TOKEN_POLICY_ID_TO_LABEL,
        label2id=TOKEN_POLICY_LABEL_TO_ID,
    )
    model = stack["AutoModelForTokenClassification"].from_pretrained(
        model_name,
        config=config,
        ignore_mismatched_sizes=True,
    )
    model.to(device)

    def encode_indices(indices: list[int]) -> tuple[list[dict[str, list[int]]], Counter[str], Counter[str]]:
        encoded_rows: list[dict[str, list[int]]] = []
        action_counts: Counter[str] = Counter()
        reason_counts: Counter[str] = Counter()
        for index in indices:
            encoded, row_actions, row_reasons = encode_row(
                rows[index],
                tokenizer=tokenizer,
                text_col=text_col,
                source_col=source_col,
                label_col=label_col,
                target_col=target_col,
                target_categories_col=target_categories_col,
                rationale_col=rationale_col,
                max_length=max_length,
                metadata_prefix=metadata_prefix,
            )
            encoded_rows.append(encoded)
            action_counts.update(row_actions)
            reason_counts.update(row_reasons)
        return encoded_rows, action_counts, reason_counts

    train_encoded, train_action_counts, train_reason_counts = encode_indices(train_indices)
    dev_encoded, dev_action_counts, dev_reason_counts = encode_indices(dev_indices)
    class_weights = build_class_weights(
        torch,
        train_action_counts,
        mode=class_weighting,
        max_class_weight=max_class_weight,
        device=device,
    )
    collate = lambda batch: collate_batch(torch, batch)
    train_loader = stack["DataLoader"](
        train_encoded,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate,
    )
    dev_loader = stack["DataLoader"](
        dev_encoded,
        batch_size=batch_size,
        shuffle=False,
        collate_fn=collate,
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay,
    )
    started = time.time()
    step = 0
    train_losses: list[float] = []
    target_steps = max(1, math.ceil(len(train_loader) * epochs))
    if max_train_steps:
        target_steps = min(target_steps, max_train_steps)
    model.train()
    while step < target_steps:
        for batch in train_loader:
            model.train()
            batch = {key: value.to(device) for key, value in batch.items()}
            labels = batch.pop("labels")
            outputs = model(**batch)
            loss = token_loss(torch, outputs.logits, labels, class_weights)
            loss.backward()
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            step += 1
            train_losses.append(float(loss.detach().cpu()))
            if log_steps and step % log_steps == 0:
                print(
                    f"token-policy train step={step} loss={train_losses[-1]:.4f}",
                    file=sys.stderr,
                    flush=True,
                )
            if step >= target_steps:
                break

    dev_metrics = evaluate_token_model(
        torch=torch,
        data_loader=dev_loader,
        model=model,
        device=device,
    )
    train_loss = rounded(sum(train_losses) / len(train_losses)) if train_losses else 0.0
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    revision = getattr(config, "_commit_hash", None)
    metadata = {
        "format_version": 1,
        "model_type": "transformers_token_classification",
        "model_name": model_name,
        "revision": revision,
        "actions": TOKEN_POLICY_ACTIONS,
        "label_to_id": TOKEN_POLICY_LABEL_TO_ID,
        "id_to_label": {str(key): value for key, value in TOKEN_POLICY_ID_TO_LABEL.items()},
        "columns": {
            "text_col": text_col,
            "id_col": id_col,
            "source_col": source_col,
            "label_col": label_col,
            "target_col": target_col,
            "target_categories_col": target_categories_col,
            "rationale_col": rationale_col,
        },
        "metadata_prefix": metadata_prefix,
        "max_length": max_length,
        "split_strategy": effective_split_strategy,
        "class_weighting": class_weighting,
        "class_weights": class_weight_report(class_weights),
        "warning": TOKEN_POLICY_WARNING,
        "weak_label_policy": {
            "direct_identifiers": ACTION_MASK,
            "quasi_identifiers": ACTION_GENERALIZE,
            "targets": ACTION_PROTECT_TARGET,
            "utility_action_negation_cues": ACTION_PROTECT_HSD,
            "rationale_spans": ACTION_PROTECT_HSD,
            "style_markers": ACTION_NORMALIZE,
            "author_self_disclosure_targets": ACTION_REVIEW,
        },
    }
    write_json(output_dir / TOKEN_POLICY_METADATA, metadata)
    result = {
        "training_type": "role_aware_token_policy",
        "input": str(input_path),
        "output_dir": str(output_dir),
        "report": str(report_path) if report_path else None,
        "warning": TOKEN_POLICY_WARNING,
        "model": {
            "name": model_name,
            "revision": revision,
            "device": device,
            "saved": True,
        },
        "columns": metadata["columns"],
        "data_validation": label_integrity,
        "sample": {
            "strategy": sample_strategy,
            "requested_sample_size": sample_size,
            "row_count": len(selected_indices),
            "source_row_count": len(rows),
            "selection_report": sample_report,
        },
        "split": {
            "random_state": random_state,
            "test_size": test_size,
            "strategy": effective_split_strategy,
            "train_rows": len(train_indices),
            "dev_rows": len(dev_indices),
            "report": split_report,
        },
        "training_args": {
            "max_length": max_length,
            "epochs": epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "weight_decay": weight_decay,
            "class_weighting": class_weighting,
            "max_class_weight": max_class_weight,
            "class_weights": class_weight_report(class_weights),
            "metadata_prefix": metadata_prefix,
            "max_train_steps": max_train_steps,
            "fold_count": fold_count,
            "fold_index": fold_index,
        },
        "train": {
            "steps": step,
            "loss": train_loss,
            "action_counts": dict(sorted(train_action_counts.items())),
            "reason_counts": dict(sorted(train_reason_counts.items())),
        },
        "dev": {
            "action_counts": dict(sorted(dev_action_counts.items())),
            "reason_counts": dict(sorted(dev_reason_counts.items())),
            "metrics": dev_metrics,
        },
        "runtime_seconds": rounded(time.time() - started),
        "limitations": [
            "Weak labels are generated from deterministic detectors and cue rules.",
            "The model predicts advisory token actions only.",
            "Final text must still pass cue, privacy, source regression, and exact-format validation.",
        ],
    }
    if report_path:
        write_json(report_path, result)
    return result


def load_token_policy_model(model_dir: Path) -> tuple[dict[str, Any], Any, Any, Any, str]:
    stack = load_transformer_stack()
    torch = stack["torch"]
    metadata_path = model_dir / TOKEN_POLICY_METADATA
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TokenPolicyError(f"missing token policy metadata: {metadata_path}") from exc
    tokenizer = stack["AutoTokenizer"].from_pretrained(model_dir, use_fast=True)
    if not getattr(tokenizer, "is_fast", False):
        raise TokenPolicyError(f"{model_dir}: fast tokenizer is required")
    model = stack["AutoModelForTokenClassification"].from_pretrained(model_dir)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()
    return metadata, tokenizer, model, torch, device


def load_token_policy_ensemble(model_dirs: list[Path]) -> list[dict[str, Any]]:
    if not model_dirs:
        raise TokenPolicyError("at least one --model-dir is required")
    members: list[dict[str, Any]] = []
    for model_dir in model_dirs:
        metadata, tokenizer, model, torch, device = load_token_policy_model(model_dir)
        actions = list(metadata.get("actions", []))
        if actions and actions != TOKEN_POLICY_ACTIONS:
            raise TokenPolicyError(
                f"{model_dir}: incompatible token actions {actions}; "
                f"expected {TOKEN_POLICY_ACTIONS}"
            )
        members.append(
            {
                "model_dir": model_dir,
                "metadata": metadata,
                "tokenizer": tokenizer,
                "model": model,
                "torch": torch,
                "device": device,
            }
        )
    return members


def normalize_model_weights(weights: list[float] | None, member_count: int) -> list[float]:
    if weights is None or not weights:
        return [1.0] * member_count
    if len(weights) != member_count:
        raise TokenPolicyError("--model-weight must be supplied once per --model-dir")
    if any(weight <= 0 for weight in weights):
        raise TokenPolicyError("--model-weight values must be positive")
    return [float(weight) for weight in weights]


def token_spans_for_text(text: str) -> list[tuple[str, int, int]]:
    return [
        (match.group(0), match.start(), match.end())
        for match in TOKEN_PATTERN.finditer(text)
    ]


def token_distributions_for_row(
    row: dict[str, str],
    *,
    token_spans: list[tuple[str, int, int]],
    member: dict[str, Any],
) -> list[tuple[list[float], bool]]:
    metadata = member["metadata"]
    tokenizer = member["tokenizer"]
    model = member["model"]
    torch = member["torch"]
    device = member["device"]
    columns = metadata["columns"]
    input_text, text_start = model_input_for_row(
        row,
        text_col=columns["text_col"],
        source_col=columns.get("source_col"),
        label_col=columns.get("label_col"),
        target_col=columns.get("target_col"),
        metadata_prefix=bool(metadata.get("metadata_prefix", True)),
    )
    encoded = tokenizer(
        input_text,
        truncation=True,
        padding="max_length",
        max_length=int(metadata.get("max_length", DEFAULT_MAX_LENGTH)),
        return_offsets_mapping=True,
        return_tensors="pt",
    )
    offsets = [tuple(offset) for offset in encoded.pop("offset_mapping")[0].tolist()]
    with torch.no_grad():
        batch = {key: value.to(device) for key, value in encoded.items()}
        logits = model(**batch).logits[0]
        probabilities = torch.softmax(logits, dim=-1).detach().cpu().tolist()

    model_pieces: list[tuple[int, int, list[float]]] = []
    for token_index, (start, end) in enumerate(offsets):
        if start == end or end <= text_start:
            continue
        original_start = max(0, int(start) - text_start)
        original_end = max(0, int(end) - text_start)
        model_pieces.append((original_start, original_end, probabilities[token_index]))

    distributions: list[tuple[list[float], bool]] = []
    for _token, token_start, token_end in token_spans:
        covered = [
            piece_probabilities
            for piece_start, piece_end, piece_probabilities in model_pieces
            if overlaps(token_start, token_end, piece_start, piece_end)
        ]
        if not covered:
            distributions.append(([0.0] * len(TOKEN_POLICY_ACTIONS), False))
            continue
        averaged = [
            sum(probabilities[label_index] for probabilities in covered) / len(covered)
            for label_index in range(len(TOKEN_POLICY_ACTIONS))
        ]
        distributions.append((averaged, True))
    return distributions


def choose_ensemble_action(
    member_distributions: list[tuple[list[float], bool]],
    *,
    model_weights: list[float],
    mode: str,
) -> tuple[str, float, int]:
    if mode not in ENSEMBLE_MODES:
        raise TokenPolicyError(
            f"unknown ensemble mode {mode!r}; expected one of {sorted(ENSEMBLE_MODES)}"
        )
    covered = [
        (distribution, model_weights[index])
        for index, (distribution, is_covered) in enumerate(member_distributions)
        if is_covered
    ]
    if not covered:
        return ACTION_KEEP, 1.0, 0

    if mode == "priority_vote":
        votes: Counter[str] = Counter()
        for distribution, weight in covered:
            label_id = max(
                range(len(distribution)),
                key=lambda index: (
                    distribution[index],
                    ACTION_PRIORITY[TOKEN_POLICY_ID_TO_LABEL[index]],
                ),
            )
            votes[TOKEN_POLICY_ID_TO_LABEL[label_id]] += weight
        action = max(
            TOKEN_POLICY_ACTIONS,
            key=lambda item: (votes[item], ACTION_PRIORITY[item]),
        )
        confidence = votes[action] / sum(weight for _distribution, weight in covered)
        return action, rounded(confidence), len(covered)

    total_weight = sum(weight for _distribution, weight in covered)
    scores = [0.0] * len(TOKEN_POLICY_ACTIONS)
    for distribution, weight in covered:
        for label_index, probability in enumerate(distribution):
            scores[label_index] += probability * weight
    scores = [score / total_weight for score in scores]
    label_id = max(
        range(len(scores)),
        key=lambda index: (
            scores[index],
            ACTION_PRIORITY[TOKEN_POLICY_ID_TO_LABEL[index]],
        ),
    )
    return TOKEN_POLICY_ID_TO_LABEL[label_id], rounded(scores[label_id]), len(covered)


def ensemble_predictions_for_row(
    row: dict[str, str],
    *,
    members: list[dict[str, Any]],
    model_weights: list[float],
    mode: str,
    text_col: str = "text",
    token_spans: list[tuple[str, int, int]] | None = None,
) -> tuple[
    list[dict[str, Any]],
    Counter[str],
    int,
    list[list[tuple[str, bool]]],
    list[tuple[str, bool, float]],
]:
    text = str(row.get(text_col, "") or "")
    spans = token_spans if token_spans is not None else token_spans_for_text(text)
    distributions_by_member = [
        token_distributions_for_row(row, token_spans=spans, member=member)
        for member in members
    ]
    prediction_spans: list[dict[str, Any]] = []
    action_counts: Counter[str] = Counter()
    skipped_tokens = 0
    member_actions: list[list[tuple[str, bool]]] = [[] for _member in members]
    ensemble_actions: list[tuple[str, bool, float]] = []
    for token_index, (_token, token_start, token_end) in enumerate(spans):
        token_member_distributions = [
            distributions[token_index]
            for distributions in distributions_by_member
        ]
        for member_index, (distribution, covered) in enumerate(token_member_distributions):
            if covered:
                label_id = max(
                    range(len(distribution)),
                    key=lambda index: (
                        distribution[index],
                        ACTION_PRIORITY[TOKEN_POLICY_ID_TO_LABEL[index]],
                    ),
                )
                member_actions[member_index].append((TOKEN_POLICY_ID_TO_LABEL[label_id], True))
            else:
                member_actions[member_index].append((ACTION_KEEP, False))
        action, confidence, covered_count = choose_ensemble_action(
            token_member_distributions,
            model_weights=model_weights,
            mode=mode,
        )
        if covered_count == 0:
            skipped_tokens += 1
            ensemble_actions.append((ACTION_KEEP, False, confidence))
            continue
        ensemble_actions.append((action, True, confidence))
        action_counts[action] += 1
        if action == ACTION_KEEP:
            continue
        prediction_spans.append(
            {
                "start": token_start,
                "end": token_end,
                "action": action,
                "confidence": confidence,
                "model_count": covered_count,
            }
        )
    return (
        merge_prediction_spans(prediction_spans),
        action_counts,
        skipped_tokens,
        member_actions,
        ensemble_actions,
    )


def evaluate_token_policy(
    input_path: Path,
    *,
    model_dir: Path = DEFAULT_OUTPUT_DIR,
    text_col: str,
    id_col: str | None = None,
    source_col: str | None = "source",
    label_col: str | None = "label",
    target_col: str | None = "target",
    target_categories_col: str | None = "target_categories",
    rationale_col: str | None = "rationale_spans",
    sample_size: int = 0,
    sample_strategy: str = DEFAULT_SAMPLE_STRATEGY,
    batch_size: int = DEFAULT_BATCH_SIZE,
    output_path: Path | None = DEFAULT_EVALUATE_REPORT,
) -> dict[str, Any]:
    if batch_size < 1:
        raise TokenPolicyError("--batch-size must be at least 1")
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        source_col=source_col,
        label_col=label_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    label_integrity = validate_source_labels(
        rows,
        source_col=source_col,
        label_col=label_col,
    )
    if label_integrity["anomaly_count"]:
        raise TokenPolicyError(
            "unexpected source/label pairs; inspect anomaly_samples in a profile "
            "or use source-aware normalization before evaluation"
        )
    selected_indices, sample_report = sample_row_indices_with_report(
        rows,
        sample_size=sample_size,
        strategy=sample_strategy,
        text_col=text_col,
        id_col=id_col,
        source_col=source_col,
        label_col=label_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    metadata, tokenizer, model, torch, device = load_token_policy_model(model_dir)
    max_length = int(metadata.get("max_length", DEFAULT_MAX_LENGTH))
    metadata_prefix = bool(metadata.get("metadata_prefix", True))
    encoded_rows: list[dict[str, list[int]]] = []
    action_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    started = time.time()
    for index in selected_indices:
        encoded, row_actions, row_reasons = encode_row(
            rows[index],
            tokenizer=tokenizer,
            text_col=text_col,
            source_col=source_col,
            label_col=label_col,
            target_col=target_col,
            target_categories_col=target_categories_col,
            rationale_col=rationale_col,
            max_length=max_length,
            metadata_prefix=metadata_prefix,
        )
        encoded_rows.append(encoded)
        action_counts.update(row_actions)
        reason_counts.update(row_reasons)
    stack = load_transformer_stack()
    data_loader = stack["DataLoader"](
        encoded_rows,
        batch_size=batch_size,
        shuffle=False,
        collate_fn=lambda batch: collate_batch(torch, batch),
    )
    metrics = evaluate_token_model(
        torch=torch,
        data_loader=data_loader,
        model=model,
        device=device,
    )
    result = {
        "artifact_type": "token_policy_evaluation",
        "input": str(input_path),
        "model_dir": str(model_dir),
        "output": str(output_path) if output_path else None,
        "warning": TOKEN_POLICY_WARNING,
        "columns": {
            "text_col": text_col,
            "id_col": id_col,
            "source_col": source_col,
            "label_col": label_col,
            "target_col": target_col,
            "target_categories_col": target_categories_col,
            "rationale_col": rationale_col,
        },
        "data_validation": label_integrity,
        "sample": {
            "strategy": sample_strategy,
            "requested_sample_size": sample_size,
            "row_count": len(selected_indices),
            "source_row_count": len(rows),
            "selection_report": sample_report,
        },
        "model": {
            "device": device,
            "max_length": max_length,
            "metadata_prefix": metadata_prefix,
        },
        "action_counts": dict(sorted(action_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "metrics": metrics,
        "runtime_seconds": rounded(time.time() - started),
    }
    if output_path:
        write_json(output_path, result)
    return result


def ensemble_member_report(
    members: list[dict[str, Any]],
    model_weights: list[float],
) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for index, member in enumerate(members):
        metadata = member["metadata"]
        report.append(
            {
                "index": index,
                "model_dir": str(member["model_dir"]),
                "name": metadata.get("model_name"),
                "revision": metadata.get("revision"),
                "device": member["device"],
                "weight": model_weights[index],
                "max_length": int(metadata.get("max_length", DEFAULT_MAX_LENGTH)),
                "metadata_prefix": bool(metadata.get("metadata_prefix", True)),
            }
        )
    return report


def evaluate_token_policy_ensemble(
    input_path: Path,
    *,
    model_dirs: list[Path],
    model_weights: list[float] | None = None,
    mode: str = "mean_prob",
    text_col: str,
    id_col: str | None = None,
    source_col: str | None = "source",
    label_col: str | None = "label",
    target_col: str | None = "target",
    target_categories_col: str | None = "target_categories",
    rationale_col: str | None = "rationale_spans",
    sample_size: int = 0,
    sample_strategy: str = DEFAULT_SAMPLE_STRATEGY,
    output_path: Path | None = DEFAULT_ENSEMBLE_EVALUATE_REPORT,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        source_col=source_col,
        label_col=label_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    label_integrity = validate_source_labels(
        rows,
        source_col=source_col,
        label_col=label_col,
    )
    if label_integrity["anomaly_count"]:
        raise TokenPolicyError(
            "unexpected source/label pairs; inspect anomaly_samples in a profile "
            "or use source-aware normalization before ensemble evaluation"
        )
    selected_indices, sample_report = sample_row_indices_with_report(
        rows,
        sample_size=sample_size,
        strategy=sample_strategy,
        text_col=text_col,
        id_col=id_col,
        source_col=source_col,
        label_col=label_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    members = load_token_policy_ensemble(model_dirs)
    weights = normalize_model_weights(model_weights, len(members))
    started = time.time()

    true_labels: list[int] = []
    predicted_labels: list[int] = []
    member_true_labels: list[list[int]] = [[] for _member in members]
    member_predicted_labels: list[list[int]] = [[] for _member in members]
    action_counts: Counter[str] = Counter()
    prediction_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    skipped_tokens = 0
    aggregate_member_prediction_counts: list[Counter[str]] = [
        Counter() for _member in members
    ]

    for index in selected_indices:
        row = rows[index]
        examples = token_examples_for_row(
            row,
            row_index=index + 1,
            text_col=text_col,
            id_col=id_col,
            source_col=source_col,
            target_col=target_col,
            target_categories_col=target_categories_col,
            rationale_col=rationale_col,
        )
        token_spans = [
            (example.token, example.start, example.end)
            for example in examples
        ]
        (
            _spans,
            _row_prediction_counts,
            row_skipped_tokens,
            member_actions,
            ensemble_actions,
        ) = ensemble_predictions_for_row(
            row,
            members=members,
            model_weights=weights,
            mode=mode,
            text_col=text_col,
            token_spans=token_spans,
        )
        skipped_tokens += row_skipped_tokens
        for token_index, example in enumerate(examples):
            true_label = TOKEN_POLICY_LABEL_TO_ID[example.action]
            action_counts[example.action] += 1
            reason_counts.update(example.reasons)
            ensemble_action, covered, _confidence = ensemble_actions[token_index]
            if covered:
                true_labels.append(true_label)
                predicted_label = TOKEN_POLICY_LABEL_TO_ID[ensemble_action]
                predicted_labels.append(predicted_label)
                prediction_counts[ensemble_action] += 1
            for member_index, actions in enumerate(member_actions):
                member_action, member_covered = actions[token_index]
                if not member_covered:
                    continue
                member_true_labels[member_index].append(true_label)
                member_predicted_labels[member_index].append(
                    TOKEN_POLICY_LABEL_TO_ID[member_action]
                )
                aggregate_member_prediction_counts[member_index][member_action] += 1

    result = {
        "artifact_type": "token_policy_ensemble_evaluation",
        "input": str(input_path),
        "output": str(output_path) if output_path else None,
        "warning": TOKEN_POLICY_WARNING,
        "mode": mode,
        "columns": {
            "text_col": text_col,
            "id_col": id_col,
            "source_col": source_col,
            "label_col": label_col,
            "target_col": target_col,
            "target_categories_col": target_categories_col,
            "rationale_col": rationale_col,
        },
        "data_validation": label_integrity,
        "sample": {
            "strategy": sample_strategy,
            "requested_sample_size": sample_size,
            "row_count": len(selected_indices),
            "source_row_count": len(rows),
            "selection_report": sample_report,
        },
        "members": ensemble_member_report(members, weights),
        "action_counts": dict(sorted(action_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "prediction_counts": dict(sorted(prediction_counts.items())),
        "skipped_token_count": skipped_tokens,
        "metrics": prediction_metrics(true_labels, predicted_labels),
        "member_metrics": [
            {
                "index": member_index,
                "model_dir": str(members[member_index]["model_dir"]),
                "prediction_counts": dict(
                    sorted(aggregate_member_prediction_counts[member_index].items())
                ),
                "metrics": prediction_metrics(
                    member_true_labels[member_index],
                    member_predicted_labels[member_index],
                ),
            }
            for member_index in range(len(members))
        ],
        "runtime_seconds": rounded(time.time() - started),
    }
    if output_path:
        write_json(output_path, result)
    return result


def predict_token_policy_ensemble(
    input_path: Path,
    *,
    model_dirs: list[Path],
    model_weights: list[float] | None = None,
    mode: str = "mean_prob",
    text_col: str,
    id_col: str | None = None,
    source_col: str | None = "source",
    label_col: str | None = "label",
    target_col: str | None = "target",
    target_categories_col: str | None = "target_categories",
    rationale_col: str | None = "rationale_spans",
    sample_size: int = DEFAULT_PREDICT_SAMPLE_SIZE,
    sample_strategy: str = DEFAULT_SAMPLE_STRATEGY,
    output_path: Path = DEFAULT_ENSEMBLE_PREDICTIONS,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        source_col=source_col,
        label_col=label_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    indices = sample_row_indices(
        rows,
        sample_size=sample_size,
        strategy=sample_strategy,
        source_col=source_col,
        label_col=label_col,
        text_col=text_col,
        id_col=id_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    members = load_token_policy_ensemble(model_dirs)
    weights = normalize_model_weights(model_weights, len(members))
    aggregate_counts: Counter[str] = Counter()
    skipped_tokens = 0
    prediction_rows: list[dict[str, Any]] = []
    started = time.time()
    for index in indices:
        row = rows[index]
        text = str(row.get(text_col, "") or "")
        token_spans = token_spans_for_text(text)
        spans, action_counts, row_skipped_tokens, _member_actions, _ensemble_actions = (
            ensemble_predictions_for_row(
                row,
                members=members,
                model_weights=weights,
                mode=mode,
                text_col=text_col,
                token_spans=token_spans,
            )
        )
        aggregate_counts.update(action_counts)
        skipped_tokens += row_skipped_tokens
        prediction_rows.append(
            {
                "row_index": index + 1,
                "row_id": str(row.get(id_col, "") or index + 1) if id_col else str(index + 1),
                "source": str(row.get(source_col, "") or "") if source_col else None,
                "label": str(row.get(label_col, "") or "") if label_col else None,
                "action_counts": dict(sorted(action_counts.items())),
                "skipped_token_count": row_skipped_tokens,
                "spans": spans,
            }
        )
    result = {
        "artifact_type": "token_policy_ensemble_predictions",
        "input": str(input_path),
        "output": str(output_path),
        "warning": TOKEN_POLICY_WARNING,
        "mode": mode,
        "sample": {
            "strategy": sample_strategy,
            "requested_sample_size": sample_size,
            "row_count": len(indices),
            "source_row_count": len(rows),
        },
        "members": ensemble_member_report(members, weights),
        "aggregate_action_counts": dict(sorted(aggregate_counts.items())),
        "skipped_token_count": skipped_tokens,
        "rows": prediction_rows,
        "runtime_seconds": rounded(time.time() - started),
    }
    write_json(output_path, result)
    return result


def prediction_spans_for_row(
    row: dict[str, str],
    *,
    metadata: dict[str, Any],
    tokenizer: Any,
    model: Any,
    torch: Any,
    device: str,
) -> dict[str, Any]:
    columns = metadata["columns"]
    input_text, text_start = model_input_for_row(
        row,
        text_col=columns["text_col"],
        source_col=columns.get("source_col"),
        label_col=columns.get("label_col"),
        target_col=columns.get("target_col"),
        metadata_prefix=bool(metadata.get("metadata_prefix", True)),
    )
    encoded = tokenizer(
        input_text,
        truncation=True,
        padding="max_length",
        max_length=int(metadata.get("max_length", DEFAULT_MAX_LENGTH)),
        return_offsets_mapping=True,
        return_tensors="pt",
    )
    offsets = [tuple(offset) for offset in encoded.pop("offset_mapping")[0].tolist()]
    with torch.no_grad():
        batch = {key: value.to(device) for key, value in encoded.items()}
        logits = model(**batch).logits[0]
        probabilities = torch.softmax(logits, dim=-1).detach().cpu().tolist()
    spans: list[dict[str, Any]] = []
    action_counts: Counter[str] = Counter()
    for token_index, (start, end) in enumerate(offsets):
        if start == end or end <= text_start:
            continue
        row_probabilities = probabilities[token_index]
        label_id = max(range(len(row_probabilities)), key=row_probabilities.__getitem__)
        action = TOKEN_POLICY_ID_TO_LABEL[int(label_id)]
        confidence = float(row_probabilities[label_id])
        action_counts[action] += 1
        if action == ACTION_KEEP:
            continue
        spans.append(
            {
                "start": max(0, int(start) - text_start),
                "end": max(0, int(end) - text_start),
                "action": action,
                "confidence": rounded(confidence),
            }
        )
    return {
        "action_counts": dict(sorted(action_counts.items())),
        "spans": merge_prediction_spans(spans),
    }


def merge_prediction_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not spans:
        return []
    ordered = sorted(spans, key=lambda item: (item["start"], item["end"], item["action"]))
    merged: list[dict[str, Any]] = []
    for span in ordered:
        if not merged:
            merged.append(dict(span))
            continue
        previous = merged[-1]
        if span["action"] == previous["action"] and span["start"] <= previous["end"] + 1:
            previous["end"] = max(previous["end"], span["end"])
            previous["confidence"] = rounded(
                min(float(previous["confidence"]), float(span["confidence"]))
            )
        else:
            merged.append(dict(span))
    return merged


def predict_token_policy(
    input_path: Path,
    *,
    model_dir: Path,
    text_col: str,
    id_col: str | None = None,
    source_col: str | None = "source",
    label_col: str | None = "label",
    target_col: str | None = "target",
    target_categories_col: str | None = "target_categories",
    rationale_col: str | None = "rationale_spans",
    sample_size: int = DEFAULT_PREDICT_SAMPLE_SIZE,
    sample_strategy: str = DEFAULT_SAMPLE_STRATEGY,
    output_path: Path = DEFAULT_PREDICTIONS,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        source_col=source_col,
        label_col=label_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    metadata, tokenizer, model, torch, device = load_token_policy_model(model_dir)
    indices = sample_row_indices(
        rows,
        sample_size=sample_size,
        strategy=sample_strategy,
        source_col=source_col,
        label_col=label_col,
        text_col=text_col,
        id_col=id_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    aggregate_counts: Counter[str] = Counter()
    prediction_rows: list[dict[str, Any]] = []
    started = time.time()
    for index in indices:
        row = rows[index]
        row_prediction = prediction_spans_for_row(
            row,
            metadata=metadata,
            tokenizer=tokenizer,
            model=model,
            torch=torch,
            device=device,
        )
        aggregate_counts.update(row_prediction["action_counts"])
        prediction_rows.append(
            {
                "row_index": index + 1,
                "row_id": str(row.get(id_col, "") or index + 1) if id_col else str(index + 1),
                "source": str(row.get(source_col, "") or "") if source_col else None,
                "label": str(row.get(label_col, "") or "") if label_col else None,
                "action_counts": row_prediction["action_counts"],
                "spans": row_prediction["spans"],
            }
        )
    result = {
        "artifact_type": "token_policy_predictions",
        "input": str(input_path),
        "model_dir": str(model_dir),
        "output": str(output_path),
        "warning": TOKEN_POLICY_WARNING,
        "sample": {
            "strategy": sample_strategy,
            "requested_sample_size": sample_size,
            "row_count": len(indices),
            "source_row_count": len(rows),
        },
        "model": {
            "name": metadata.get("model_name"),
            "revision": metadata.get("revision"),
            "device": device,
        },
        "aggregate_action_counts": dict(sorted(aggregate_counts.items())),
        "rows": prediction_rows,
        "runtime_seconds": rounded(time.time() - started),
    }
    write_json(output_path, result)
    return result


def protected_spans_for_text(text: str) -> list[tuple[int, int, str]]:
    protected: list[tuple[int, int, str]] = []
    for span in target_group_spans(text):
        protected.append((span.start, span.end, ACTION_PROTECT_TARGET))
    for start, end in phrase_spans(
        text,
        {cue.lower() for cue in UTILITY_CUES}
        | {term.lower() for term in ACTION_TERMS}
        | {term.lower() for term in NEGATION_MODALITY_TERMS},
    ):
        protected.append((start, end, ACTION_PROTECT_HSD))
    return protected


def overlaps_any(start: int, end: int, spans: Iterable[tuple[int, int, str]]) -> bool:
    return any(overlaps(start, end, span_start, span_end) for span_start, span_end, _ in spans)


def apply_replacements(text: str, replacements: list[tuple[int, int, str]]) -> str:
    if not replacements:
        return text
    selected: list[tuple[int, int, str]] = []
    for start, end, replacement in sorted(
        replacements,
        key=lambda item: (item[1] - item[0], item[0]),
        reverse=True,
    ):
        if any(overlaps(start, end, chosen_start, chosen_end) for chosen_start, chosen_end, _ in selected):
            continue
        selected.append((start, end, replacement))
    updated = text
    for start, end, replacement in sorted(selected, key=lambda item: item[0], reverse=True):
        updated = updated[:start] + replacement + updated[end:]
    return updated


def apply_policy_to_text(
    text: str,
    prediction_spans: list[dict[str, Any]],
    *,
    min_confidence: float = 0.5,
) -> tuple[str, dict[str, Any]]:
    protected = protected_spans_for_text(text)
    replacements: list[tuple[int, int, str]] = []
    skipped: Counter[str] = Counter()
    deterministic_spans = detect_spans(text, include_context=True, include_targets=False)
    for span in deterministic_spans:
        if span.entity_type in DIRECT_IDENTIFIER_TYPES:
            replacements.append((span.start, span.end, span.replacement_tag()))
        elif span.entity_type in QUASI_IDENTIFIER_TYPES and not overlaps_any(
            span.start, span.end, protected
        ):
            replacements.append((span.start, span.end, span.replacement_tag()))

    normalize_style = False
    for span in prediction_spans:
        try:
            start = int(span["start"])
            end = int(span["end"])
            confidence = float(span.get("confidence", 1.0))
        except (KeyError, TypeError, ValueError):
            skipped["invalid_prediction_span"] += 1
            continue
        action = str(span.get("action", ""))
        if confidence < min_confidence:
            skipped["low_confidence"] += 1
            continue
        if action in {ACTION_PROTECT_TARGET, ACTION_PROTECT_HSD, ACTION_REVIEW, ACTION_KEEP}:
            continue
        if start < 0 or end <= start or end > len(text):
            skipped["out_of_bounds"] += 1
            continue
        if overlaps_any(start, end, protected):
            skipped["protected_overlap"] += 1
            continue
        if action == ACTION_MASK:
            replacements.append((start, end, "[ID]"))
        elif action == ACTION_GENERALIZE:
            replacements.append((start, end, "[CONTEXT]"))
        elif action == ACTION_NORMALIZE:
            normalize_style = True

    candidate = apply_replacements(text, replacements)
    style_changed = False
    if normalize_style:
        style_result = scrub_style(candidate)
        candidate = style_result.text
        style_changed = style_result.changed
    metrics = row_metric(text, candidate)
    accepted = (
        float(metrics.get("target_cue_retention", 1.0)) >= 1.0
        and float(metrics.get("utility_cue_retention", 1.0)) >= 1.0
    )
    if not accepted:
        skipped["candidate_failed_cue_guardrail"] += 1
        candidate = text
    audit = {
        "accepted": accepted,
        "replacement_count": len(replacements),
        "style_changed": style_changed,
        "skipped_counts": dict(sorted(skipped.items())),
        "metrics": metrics,
    }
    return candidate, audit


def load_predictions_by_row_id(path: Path) -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    predictions: dict[str, list[dict[str, Any]]] = {}
    for row in payload.get("rows", []):
        predictions[str(row.get("row_id", ""))] = list(row.get("spans", []))
    return predictions


def apply_token_policy_candidates(
    input_path: Path,
    output_path: Path,
    *,
    text_col: str,
    id_col: str | None,
    policy_predictions: Path,
    candidate_col: str = "token_policy_candidate",
    audit_path: Path | None = None,
    min_confidence: float = 0.5,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    validate_columns(input_path, fieldnames, text_col=text_col, id_col=id_col)
    predictions = load_predictions_by_row_id(policy_predictions)
    output_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    accepted = 0
    changed = 0
    for row_index, row in enumerate(rows, start=1):
        row_id = str(row.get(id_col, "") or row_index) if id_col else str(row_index)
        text = str(row.get(text_col, "") or "")
        row_predictions = predictions.get(row_id)
        if row_predictions is None:
            candidate = text
            audit = {
                "accepted": True,
                "replacement_count": 0,
                "style_changed": False,
                "skipped_counts": {"no_policy_prediction": 1},
                "metrics": {"not_evaluated": "no_policy_prediction"},
            }
        else:
            candidate, audit = apply_policy_to_text(
                text,
                row_predictions,
                min_confidence=min_confidence,
            )
        if audit["accepted"]:
            accepted += 1
        if candidate != text:
            changed += 1
        output_row = dict(row)
        output_row[candidate_col] = candidate
        output_rows.append(output_row)
        audit_rows.append(
            {
                "row_index": row_index,
                "row_id": row_id,
                "prediction_span_count": len(row_predictions or []),
                **audit,
            }
        )
    output_fieldnames = list(fieldnames)
    if candidate_col not in output_fieldnames:
        output_fieldnames.append(candidate_col)
    write_csv(output_path, output_rows, output_fieldnames)
    result = {
        "artifact_type": "token_policy_candidates",
        "input": str(input_path),
        "output": str(output_path),
        "policy_predictions": str(policy_predictions),
        "candidate_col": candidate_col,
        "warning": TOKEN_POLICY_WARNING,
        "row_count": len(rows),
        "accepted_candidate_rows": accepted,
        "changed_candidate_rows": changed,
    }
    if audit_path:
        write_json(audit_path, {"summary": result, "rows": audit_rows})
    return result


def feature_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def token_feature_type(token: str, action: str) -> str:
    if action == ACTION_PROTECT_TARGET:
        return "target_span"
    if action == ACTION_PROTECT_HSD:
        lowered = token.lower()
        if lowered in NEGATION_MODALITY_TERMS:
            return "negation"
        if lowered in ACTION_TERMS:
            return "action_span"
        return "utility_cue"
    if action in {ACTION_MASK, ACTION_GENERALIZE}:
        return "identifier"
    if action == ACTION_NORMALIZE:
        return "style_marker"
    if len(token.split()) > 1:
        return "bigram"
    return "unigram"


def label_feature_report(
    input_path: Path,
    *,
    text_col: str,
    id_col: str | None = None,
    source_col: str | None = "source",
    label_col: str | None = "label",
    target_col: str | None = "target",
    target_categories_col: str | None = "target_categories",
    rationale_col: str | None = "rationale_spans",
    output_path: Path = DEFAULT_LABEL_FEATURE_REPORT,
    sample_size: int = 5000,
    sample_strategy: str = DEFAULT_SAMPLE_STRATEGY,
    top_features: int = 500,
) -> dict[str, Any]:
    rows, fieldnames = read_csv(input_path)
    validate_columns(
        input_path,
        fieldnames,
        text_col=text_col,
        id_col=id_col,
        source_col=source_col,
        label_col=label_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    indices = sample_row_indices(
        rows,
        sample_size=sample_size,
        strategy=sample_strategy,
        source_col=source_col,
        label_col=label_col,
        text_col=text_col,
        id_col=id_col,
        target_col=target_col,
        target_categories_col=target_categories_col,
        rationale_col=rationale_col,
    )
    aggregate: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    action_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for index in indices:
        row = rows[index]
        examples = token_examples_for_row(
            row,
            row_index=index + 1,
            text_col=text_col,
            id_col=id_col,
            source_col=source_col,
            target_col=target_col,
            target_categories_col=target_categories_col,
            rationale_col=rationale_col,
        )
        source = str(row.get(source_col, "") or "") if source_col else ""
        label = str(row.get(label_col, "") or "") if label_col else ""
        seen_in_row: set[tuple[str, str, str, str, str]] = set()
        for example in examples:
            normalized = example.token.lower()
            digest = feature_hash(normalized)
            feature_type = token_feature_type(example.token, example.action)
            key = (digest, feature_type, source, label, example.action)
            if key not in aggregate:
                aggregate[key] = {
                    "feature_hash": digest,
                    "feature_type": feature_type,
                    "source": source,
                    "label_or_label_set": label,
                    "total_occurrences": 0,
                    "row_count_with_feature": 0,
                    "mean_span_length_total": 0,
                    "suggested_policy": POLICY_BY_ACTION[example.action],
                    "reason_codes": Counter(),
                    "action": example.action,
                }
            aggregate[key]["total_occurrences"] += 1
            aggregate[key]["mean_span_length_total"] += example.end - example.start
            aggregate[key]["reason_codes"].update(example.reasons or ("no_rule",))
            if key not in seen_in_row:
                aggregate[key]["row_count_with_feature"] += 1
                seen_in_row.add(key)
            action_counts[example.action] += 1
            reason_counts.update(example.reasons or ("no_rule",))
    features: list[dict[str, Any]] = []
    for value in aggregate.values():
        occurrences = int(value["total_occurrences"])
        features.append(
            {
                "feature_hash": value["feature_hash"],
                "feature_type": value["feature_type"],
                "source": value["source"],
                "label_or_label_set": value["label_or_label_set"],
                "row_count_with_feature": int(value["row_count_with_feature"]),
                "total_occurrences": occurrences,
                "mean_span_length": rounded(value["mean_span_length_total"] / occurrences)
                if occurrences
                else 0.0,
                "suggested_policy": value["suggested_policy"],
                "reason_codes": dict(sorted(value["reason_codes"].items())),
                "action": value["action"],
            }
        )
    features.sort(
        key=lambda item: (
            item["total_occurrences"],
            item["row_count_with_feature"],
            item["feature_hash"],
        ),
        reverse=True,
    )
    result = {
        "artifact_type": "label_feature_report",
        "input": str(input_path),
        "output": str(output_path),
        "warning": TOKEN_POLICY_WARNING,
        "sample": {
            "strategy": sample_strategy,
            "requested_sample_size": sample_size,
            "row_count": len(indices),
            "source_row_count": len(rows),
        },
        "action_counts": dict(sorted(action_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "top_features": features[:top_features],
        "top_features_truncated": max(0, len(features) - top_features),
        "notes": [
            "Feature values are hashed; raw text examples are intentionally omitted.",
            "Labels are source-aware context, not one collapsed hate-speech ontology.",
        ],
    }
    write_json(output_path, result)
    return result
