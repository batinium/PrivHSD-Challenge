"""Deterministic style scrubbing for authorship-risk reduction."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Callable

from .detectors import TARGET_GROUP_TERMS
from .metrics import UTILITY_CUES
from .resource_config import load_utility_cue_terms


PLACEHOLDER_PATTERN = re.compile(
    r"(\[[A-Z][A-Z_]*(?::[A-Za-z0-9_/-]+)?\])"
)
TOKEN_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
REPEATED_LETTER_PATTERN = re.compile(r"([A-Za-z])\1{2,}")
REPEATED_PUNCTUATION_PATTERN = re.compile(r"[!?]{2,}|\.{2,}|,{2,}")
EMOJI_PATTERN = re.compile(
    r"(?:[\U0001F300-\U0001FAFF\u2600-\u27BF]\s*)+"
)
SYMBOL_BURST_PATTERN = re.compile(r"(?<!\[)[#$%&*+=~_^|<>/\\]{3,}(?!\])")
HASHTAG_PATTERN = re.compile(r"(?<!\w)#([A-Za-z][A-Za-z0-9_]{2,})\b")
STYLE_MARKER_PATTERN = re.compile(
    r"\b(?:lol+|lmao+|rofl+|frfr|ngl|tbh|imo|imho|bruh+|yolo)\b",
    re.I,
)
SIGNATURE_PATTERNS = (
    re.compile(r"(?im)(?:^|\n)\s*(?:--+|~~+)\s*[A-Za-z0-9_ .,'-]{0,80}\s*$"),
    re.compile(
        r"(?i)(?:^|\s)(?:--+|~~+)?\s*"
        r"(?:sent from my|signature:|signed,|xoxo,)"
        r"\s+[A-Za-z0-9_ .,'-]{0,80}$"
    ),
)

NEGATION_MODALITY_TERMS = set(load_utility_cue_terms("negation_modality_terms"))

ACTION_TERMS = set(load_utility_cue_terms("action_terms"))


def protected_terms() -> tuple[set[str], set[str]]:
    phrases = {cue.lower() for cue in UTILITY_CUES}
    words: set[str] = set(NEGATION_MODALITY_TERMS | ACTION_TERMS)
    for cue in UTILITY_CUES:
        for word in TOKEN_PATTERN.findall(cue.lower()):
            words.add(word)
    for terms in TARGET_GROUP_TERMS.values():
        for term in terms:
            phrases.add(term.lower())
            for word in TOKEN_PATTERN.findall(term.lower()):
                words.add(word)
    return words, phrases


PROTECTED_WORDS, PROTECTED_PHRASES = protected_terms()


@dataclass(frozen=True)
class StyleScrubResult:
    text: str
    changed: bool
    transformations: tuple[dict[str, str | int], ...]
    metrics: dict[str, object]


def split_placeholder_parts(text: str) -> list[str]:
    return PLACEHOLDER_PATTERN.split(text)


def is_placeholder(part: str) -> bool:
    return bool(PLACEHOLDER_PATTERN.fullmatch(part))


def transform_non_placeholders(
    text: str,
    transform: Callable[[str], tuple[str, int]],
) -> tuple[str, int]:
    parts: list[str] = []
    total_count = 0
    for part in split_placeholder_parts(text):
        if is_placeholder(part):
            parts.append(part)
            continue
        updated, count = transform(part)
        parts.append(updated)
        total_count += count
    return "".join(parts), total_count


def apply_pattern(
    text: str,
    pattern: re.Pattern[str],
    replacement: str | Callable[[re.Match[str]], str],
) -> tuple[str, int]:
    return pattern.subn(replacement, text)


def normalize_signature(text: str) -> tuple[str, int]:
    count = 0
    updated = text
    for pattern in SIGNATURE_PATTERNS:
        updated, pattern_count = pattern.subn(" [SIGNATURE]", updated)
        count += pattern_count
    return updated, count


def normalize_hashtag(match: re.Match[str]) -> str:
    raw_tag = match.group(1).replace("_", " ")
    tag = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw_tag)
    lowered = tag.lower()
    if lowered in PROTECTED_PHRASES:
        return lowered
    if any(word in lowered for word in PROTECTED_WORDS):
        return lowered
    return " [TAG] "


def normalize_punctuation(match: re.Match[str]) -> str:
    value = match.group(0)
    if "?" in value and "!" in value:
        return "?!"
    if "?" in value:
        return "?"
    if "!" in value:
        return "!"
    return value[0]


def normalize_repeated_letters_in_word(match: re.Match[str]) -> str:
    word = match.group(0)
    collapsed_to_two = REPEATED_LETTER_PATTERN.sub(r"\1\1", word)
    collapsed_to_one = REPEATED_LETTER_PATTERN.sub(r"\1", word)
    if collapsed_to_one.lower() in PROTECTED_WORDS:
        return collapsed_to_one
    if collapsed_to_two.lower() in PROTECTED_WORDS:
        return collapsed_to_two
    return collapsed_to_two


def normalize_repeated_letters(text: str) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        replacement = normalize_repeated_letters_in_word(match)
        if replacement != match.group(0):
            count += 1
        return replacement

    return TOKEN_PATTERN.sub(replace, text), count


def normalize_casing(text: str) -> tuple[str, int]:
    lowered = text.lower()
    return lowered, int(lowered != text)


def normalize_whitespace(text: str) -> tuple[str, int]:
    updated = re.sub(r"\s+", " ", text).strip()
    return updated, int(updated != text)


STYLE_STEPS: tuple[
    tuple[str, Callable[[str], tuple[str, int]], bool],
    ...,
] = (
    ("signature", normalize_signature, False),
    ("emoji", lambda text: apply_pattern(text, EMOJI_PATTERN, " [EMOJI] "), False),
    ("self_tag", lambda text: apply_pattern(text, HASHTAG_PATTERN, normalize_hashtag), True),
    (
        "idiolect_marker",
        lambda text: apply_pattern(text, STYLE_MARKER_PATTERN, " [STYLE] "),
        True,
    ),
    (
        "symbol_burst",
        lambda text: apply_pattern(text, SYMBOL_BURST_PATTERN, " [SYMBOLS] "),
        False,
    ),
    (
        "repeated_punctuation",
        lambda text: apply_pattern(
            text,
            REPEATED_PUNCTUATION_PATTERN,
            normalize_punctuation,
        ),
        True,
    ),
    ("repeated_letters", normalize_repeated_letters, True),
    ("casing", normalize_casing, True),
    ("whitespace", normalize_whitespace, False),
)


def scrub_style(text: str) -> StyleScrubResult:
    original = text
    updated = text
    counts: Counter[str] = Counter()
    for step_name, transform, preserve_placeholders in STYLE_STEPS:
        if preserve_placeholders:
            updated, count = transform_non_placeholders(updated, transform)
        else:
            updated, count = transform(updated)
        if count:
            counts[step_name] += count
    transformations = tuple(
        {
            "entity_type": "STYLE",
            "category": step_name,
            "source": "style_scrubber",
            "count": count,
        }
        for step_name, count in sorted(counts.items())
    )
    return StyleScrubResult(
        text=updated,
        changed=updated != original,
        transformations=transformations,
        metrics={
            "style_scrub_enabled": True,
            "style_scrub_changed": updated != original,
            "style_transform_count": sum(counts.values()),
            "style_counts_by_type": dict(sorted(counts.items())),
        },
    )
