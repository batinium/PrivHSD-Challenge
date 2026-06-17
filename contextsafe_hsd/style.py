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

CONTRACTION_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bi['’]m\b", re.I), "I am"),
    (re.compile(r"\byou['’]re\b", re.I), "you are"),
    (re.compile(r"\bwe['’]re\b", re.I), "we are"),
    (re.compile(r"\bthey['’]re\b", re.I), "they are"),
    (re.compile(r"\bhe['’]s\b", re.I), "he is"),
    (re.compile(r"\bshe['’]s\b", re.I), "she is"),
    (re.compile(r"\bit['’]s\b", re.I), "it is"),
    (re.compile(r"\bthat['’]s\b", re.I), "that is"),
    (re.compile(r"\bwhat['’]s\b", re.I), "what is"),
    (re.compile(r"\bthere['’]s\b", re.I), "there is"),
    (re.compile(r"\bi['’]ve\b", re.I), "I have"),
    (re.compile(r"\byou['’]ve\b", re.I), "you have"),
    (re.compile(r"\bwe['’]ve\b", re.I), "we have"),
    (re.compile(r"\bthey['’]ve\b", re.I), "they have"),
    (re.compile(r"\bi['’]ll\b", re.I), "I will"),
    (re.compile(r"\byou['’]ll\b", re.I), "you will"),
    (re.compile(r"\bwe['’]ll\b", re.I), "we will"),
    (re.compile(r"\bthey['’]ll\b", re.I), "they will"),
    (re.compile(r"\bcan['’]t\b", re.I), "cannot"),
    (re.compile(r"\bwon['’]t\b", re.I), "will not"),
    (re.compile(r"\bdon['’]t\b", re.I), "do not"),
    (re.compile(r"\bdoesn['’]t\b", re.I), "does not"),
    (re.compile(r"\bdidn['’]t\b", re.I), "did not"),
    (re.compile(r"\bisn['’]t\b", re.I), "is not"),
    (re.compile(r"\baren['’]t\b", re.I), "are not"),
    (re.compile(r"\bwasn['’]t\b", re.I), "was not"),
    (re.compile(r"\bweren['’]t\b", re.I), "were not"),
    (re.compile(r"\bshouldn['’]t\b", re.I), "should not"),
    (re.compile(r"\bcouldn['’]t\b", re.I), "could not"),
    (re.compile(r"\bwouldn['’]t\b", re.I), "would not"),
    (re.compile(r"\bhaven['’]t\b", re.I), "have not"),
    (re.compile(r"\bhasn['’]t\b", re.I), "has not"),
    (re.compile(r"\bhadn['’]t\b", re.I), "had not"),
    (re.compile(r"\by['’]all\b", re.I), "you all"),
    (re.compile(r"\bgonna\b", re.I), "going to"),
    (re.compile(r"\bwanna\b", re.I), "want to"),
    (re.compile(r"\bgotta\b", re.I), "got to"),
)

PLAIN_CONTRACTION_REPLACEMENTS = {
    "arent": "are not",
    "cant": "cannot",
    "couldnt": "could not",
    "didnt": "did not",
    "doesnt": "does not",
    "dont": "do not",
    "hadnt": "had not",
    "hasnt": "has not",
    "havent": "have not",
    "isnt": "is not",
    "shouldnt": "should not",
    "wasnt": "was not",
    "werent": "were not",
    "wont": "will not",
    "wouldnt": "would not",
}

AMERICAN_ENGLISH_REPLACEMENTS = {
    "apologise": "apologize",
    "apologised": "apologized",
    "apologising": "apologizing",
    "behaviour": "behavior",
    "behaviours": "behaviors",
    "cancelled": "canceled",
    "cancelling": "canceling",
    "centre": "center",
    "centres": "centers",
    "colour": "color",
    "coloured": "colored",
    "colourful": "colorful",
    "colours": "colors",
    "defence": "defense",
    "favour": "favor",
    "favoured": "favored",
    "favourite": "favorite",
    "favourites": "favorites",
    "honour": "honor",
    "honoured": "honored",
    "labour": "labor",
    "licence": "license",
    "litre": "liter",
    "litres": "liters",
    "metre": "meter",
    "metres": "meters",
    "neighbour": "neighbor",
    "neighbours": "neighbors",
    "offence": "offense",
    "organise": "organize",
    "organised": "organized",
    "organising": "organizing",
    "organisation": "organization",
    "organisations": "organizations",
    "realise": "realize",
    "realised": "realized",
    "realising": "realizing",
    "recognise": "recognize",
    "recognised": "recognized",
    "recognising": "recognizing",
    "rumour": "rumor",
    "rumours": "rumors",
    "theatre": "theater",
    "theatres": "theaters",
    "travelling": "traveling",
    "utilise": "utilize",
    "utilised": "utilized",
    "utilising": "utilizing",
}

TYPO_REPLACEMENTS = {
    "becuase": "because",
    "definately": "definitely",
    "definitelyy": "definitely",
    "goverment": "government",
    "happend": "happened",
    "occured": "occurred",
    "recieve": "receive",
    "recieved": "received",
    "seperate": "separate",
    "shoudl": "should",
    "taht": "that",
    "teh": "the",
    "thier": "their",
    "untill": "until",
    "wierd": "weird",
}

SIMPLE_LANGUAGE_REPLACEMENTS = {
    "additional": "more",
    "approximately": "about",
    "assistance": "help",
    "commence": "start",
    "commenced": "started",
    "commencing": "starting",
    "demonstrate": "show",
    "demonstrated": "showed",
    "demonstrates": "shows",
    "facilitate": "help",
    "facilitated": "helped",
    "however": "but",
    "individuals": "people",
    "numerous": "many",
    "obtain": "get",
    "obtained": "got",
    "purchase": "buy",
    "purchased": "bought",
    "regarding": "about",
    "require": "need",
    "required": "needed",
    "reside": "live",
    "resides": "lives",
    "residing": "living",
    "subsequently": "later",
    "sufficient": "enough",
    "therefore": "so",
    "utilize": "use",
    "utilized": "used",
    "utilizing": "using",
}

SIMPLE_PHRASE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bdue to the fact that\b", re.I), "because"),
    (re.compile(r"\bin order to\b", re.I), "to"),
    (re.compile(r"\bprior to\b", re.I), "before"),
    (re.compile(r"\bwith regard to\b", re.I), "about"),
    (re.compile(r"\bat this point in time\b", re.I), "now"),
    (re.compile(r"\ba number of\b", re.I), "many"),
)


def word_replacement_pattern(replacements: dict[str, str]) -> re.Pattern[str]:
    words = sorted(replacements, key=lambda value: (-len(value), value))
    return re.compile(r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\b", re.I)


CONTRACTION_RISK_PATTERN = re.compile(
    "|".join(
        [pattern.pattern for pattern, _replacement in CONTRACTION_REPLACEMENTS]
        + [
            r"\b(?:"
            + "|".join(
                re.escape(word)
                for word in sorted(
                    PLAIN_CONTRACTION_REPLACEMENTS,
                    key=lambda value: (-len(value), value),
                )
            )
            + r")\b"
        ]
    ),
    re.I,
)
AMERICAN_ENGLISH_PATTERN = word_replacement_pattern(AMERICAN_ENGLISH_REPLACEMENTS)
TYPO_PATTERN = word_replacement_pattern(TYPO_REPLACEMENTS)
SIMPLE_LANGUAGE_WORD_PATTERN = word_replacement_pattern(SIMPLE_LANGUAGE_REPLACEMENTS)
SIMPLE_LANGUAGE_PHRASE_PATTERN = re.compile(
    "|".join(pattern.pattern for pattern, _replacement in SIMPLE_PHRASE_REPLACEMENTS),
    re.I,
)


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


def normalize_contractions(text: str) -> tuple[str, int]:
    updated = text
    count = 0
    for pattern, replacement in CONTRACTION_REPLACEMENTS:
        updated, pattern_count = pattern.subn(replacement, updated)
        count += pattern_count
    updated, plain_count = normalize_word_replacements(
        updated,
        PLAIN_CONTRACTION_REPLACEMENTS,
        skip_protected=False,
    )
    return updated, count + plain_count


def normalize_word_replacements(
    text: str,
    replacements: dict[str, str],
    *,
    skip_protected: bool = True,
) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        word = match.group(0)
        lowered = word.lower()
        replacement = replacements.get(lowered)
        if replacement is None:
            return word
        if skip_protected and lowered in PROTECTED_WORDS:
            return word
        count += 1
        return replacement

    return TOKEN_PATTERN.sub(replace, text), count


def normalize_phrase_replacements(
    text: str,
    replacements: tuple[tuple[re.Pattern[str], str], ...],
) -> tuple[str, int]:
    updated = text
    count = 0
    for pattern, replacement in replacements:
        updated, pattern_count = pattern.subn(replacement, updated)
        count += pattern_count
    return updated, count


def normalize_american_english(text: str) -> tuple[str, int]:
    return normalize_word_replacements(
        text,
        AMERICAN_ENGLISH_REPLACEMENTS,
        skip_protected=False,
    )


def normalize_typos(text: str) -> tuple[str, int]:
    return normalize_word_replacements(text, TYPO_REPLACEMENTS, skip_protected=False)


def normalize_simple_language(text: str) -> tuple[str, int]:
    updated, phrase_count = normalize_phrase_replacements(
        text,
        SIMPLE_PHRASE_REPLACEMENTS,
    )
    updated, word_count = normalize_word_replacements(
        updated,
        SIMPLE_LANGUAGE_REPLACEMENTS,
    )
    return updated, phrase_count + word_count


def normalize_casing(text: str) -> tuple[str, int]:
    lowered = text.lower()
    updated = re.sub(r"\bi\b", "I", lowered)
    return updated, int(updated != text)


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
    ("contraction", normalize_contractions, True),
    ("american_english", normalize_american_english, True),
    ("typo", normalize_typos, True),
    ("simple_language", normalize_simple_language, True),
    ("casing", normalize_casing, True),
    ("whitespace", normalize_whitespace, False),
)


def scrub_style(
    text: str,
    *,
    simplify_language: bool = True,
) -> StyleScrubResult:
    original = text
    updated = text
    counts: Counter[str] = Counter()
    for step_name, transform, preserve_placeholders in STYLE_STEPS:
        if step_name == "simple_language" and not simplify_language:
            continue
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


STYLE_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("contraction", CONTRACTION_RISK_PATTERN),
    ("emoji", EMOJI_PATTERN),
    ("hashtag", HASHTAG_PATTERN),
    ("style_marker", STYLE_MARKER_PATTERN),
    ("symbol_burst", SYMBOL_BURST_PATTERN),
    ("repeated_punctuation", REPEATED_PUNCTUATION_PATTERN),
    ("repeated_letters", REPEATED_LETTER_PATTERN),
    ("american_english", AMERICAN_ENGLISH_PATTERN),
    ("typo", TYPO_PATTERN),
    ("simple_language", SIMPLE_LANGUAGE_WORD_PATTERN),
    ("simple_language", SIMPLE_LANGUAGE_PHRASE_PATTERN),
)


def style_risk_counts(text: str) -> dict[str, int]:
    counts = Counter(
        name
        for name, pattern in STYLE_RISK_PATTERNS
        for _match in pattern.finditer(text)
    )
    signature_count = 0
    for pattern in SIGNATURE_PATTERNS:
        signature_count += len(pattern.findall(text))
    if signature_count:
        counts["signature"] += signature_count
    return dict(sorted(counts.items()))


def style_risk_count(text: str) -> int:
    return sum(style_risk_counts(text).values())


def length_drift(original: str, candidate: str) -> float:
    denominator = max(len(original), 1)
    return abs(len(candidate) - len(original)) / denominator
