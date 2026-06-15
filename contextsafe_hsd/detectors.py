"""Deterministic span detectors for privacy-sensitive text.

The challenge needs a reliable baseline that runs locally and is explainable.
These detectors intentionally focus on direct identifiers and conservative
quasi-identifiers. Target-group detection is separated so it can be enabled only
when a run explicitly wants group-category generalization.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Iterable, Sequence

from .resource_config import load_target_group_terms, load_utility_cue_terms

try:  # The package ships the sensitive word list; keep raw slurs out of source.
    from better_profanity import profanity as _external_profanity
except Exception:  # pragma: no cover - optional at import time for library users.
    _external_profanity = None


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    entity_type: str
    text: str
    score: float
    source: str
    category: str | None = None
    replacement: str | None = None

    def replacement_tag(self) -> str:
        if self.replacement is not None:
            return self.replacement
        if self.entity_type == "TARGET_GROUP" and self.category:
            return f"[TARGET_GROUP:{self.category}]"
        return TAGS.get(self.entity_type, "[IDENTIFIER]")


TAGS = {
    "PERSON": "[PERSON]",
    "ALIAS": "[ALIAS]",
    "USER": "[USER]",
    "EMAIL": "[EMAIL]",
    "PHONE": "[PHONE]",
    "URL": "[URL]",
    "IP_ADDRESS": "[ID]",
    "DATE": "[DATE]",
    "LOCATION": "[LOCATION]",
    "ORGANIZATION": "[ORG]",
    "IDENTIFIER": "[ID]",
    "AGE": "[AGE]",
}

LETTER_PATTERN = r"[^\W\d_]"
NAME_WORD_PATTERN = rf"{LETTER_PATTERN}(?:[^\W\d_.'-]*{LETTER_PATTERN})?"
NAME_PHRASE_PATTERN = rf"{NAME_WORD_PATTERN}(?:\s+{NAME_WORD_PATTERN}){{0,3}}"
TARGET_ORG_WORD_PATTERN = rf"{NAME_WORD_PATTERN}(?:[-'][^\W\d_]+)*"
STREET_SUFFIX_PATTERN = (
    r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|"
    r"Lane|Ln\.?|Drive|Dr\.?|Court|Ct\.?|Way|Place|Pl\.?|"
    r"Square|Sq\.?)"
)
ORG_SUFFIX_PATTERN = (
    r"(?:University|College|Institute|Academy|School|Centre|Center|"
    r"Association|Foundation|Mosque|Synagogue|Temple|Church|Charity|"
    r"Shelter|Club|Union|Office|Community|Society|Mission|Clinic|"
    r"Hospital|Cemetery|Graveyard|House|Organization|Organisation|"
    r"Network|Collective|Coalition|Council|Federation|League|Alliance|"
    r"Service|Services|Project|Program|Programme|Restaurant|Cafe|Shop|"
    r"Day\s+School|Student\s+Union|Aid\s+Office|Community\s+"
    r"(?:Center|Centre|House)|Cultural\s+(?:Center|Centre|Club)|"
    r"Youth\s+(?:Center|Centre|Club|Shelter))"
)
TARGET_ORG_PATTERN = re.compile(
    rf"\b(?:the\s+)?{TARGET_ORG_WORD_PATTERN}"
    rf"(?:\s+{TARGET_ORG_WORD_PATTERN}){{0,5}}\s+"
    rf"{ORG_SUFFIX_PATTERN}\b",
    re.I,
)


REGEX_PATTERNS: Sequence[tuple[str, re.Pattern[str]]] = (
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("URL", re.compile(r"\b(?:https?://|hxxps?://|www\.)[^\s<>()]+", re.I)),
    ("USER", re.compile(r"(?<!\w)@[A-Za-z0-9._-]{1,64}\b")),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    (
        "PHONE",
        re.compile(
            r"(?<!\w)(?:\+?\d[\d\s().-]{6,}\d)(?:\s*(?:ext|x)\s*\d{1,6})?(?!\w)",
            re.I,
        ),
    ),
    (
        "DATE",
        re.compile(
            r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
            r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
            r"[a-z]*\s+\d{1,2},?\s+\d{2,4})\b",
            re.I,
        ),
    ),
    ("AGE", re.compile(r"\b(?:I am|I'm|aged?)\s+(\d{1,2})(?:\s+years?\s+old)?\b", re.I)),
    ("AGE", re.compile(r"\b\d{1,2}[- ]year[- ]old\b", re.I)),
    (
        "IDENTIFIER",
        re.compile(
            r"\b(?:id|case|ticket|student|user|ref)[-_:#]?"
            r"(?:[A-Z0-9]+[-_])*[A-Z0-9]*\d[A-Z0-9_-]*\b",
            re.I,
        ),
    ),
    (
        "ORGANIZATION",
        re.compile(
            r"\b[A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,5}\s+"
            rf"{ORG_SUFFIX_PATTERN}\b"
        ),
    ),
    (
        "LOCATION",
        re.compile(
            r"\b(?:[A-Z][A-Za-z0-9.'-]+\s+){0,4}[A-Z][A-Za-z0-9.'-]+\s+"
            rf"{STREET_SUFFIX_PATTERN}(?=\W|$)"
        ),
    ),
    (
        "LOCATION",
        re.compile(
            rf"\b{NAME_WORD_PATTERN}\s+"
            rf"{STREET_SUFFIX_PATTERN}(?=\W|$)",
            re.I,
        ),
    ),
)
ADJACENT_USER_PATTERN = re.compile(r"@[A-Za-z0-9._-]{1,64}\b")

OBFUSCATED_EMAIL_PATTERN = re.compile(
    r"(?<![\w@])"
    r"(?P<local>[A-Z0-9][A-Z0-9._%+-]{1,63})"
    r"\s*(?P<at_marker>\[\s*at\s*\]|\(\s*at\s*\)|_at_|\bat\b)\s*"
    r"(?P<domain>[A-Z0-9-]{2,63}(?:(?:\s+|[._-]+)[A-Z0-9-]{2,63}){0,3})"
    r"\s*(?P<dot_marker>\[\s*dot\s*\]|\(\s*dot\s*\)|_dot_|\bdot\b)\s*"
    r"(?P<tld>[A-Z]{2,24})"
    r"(?![\w@])",
    re.I,
)
OBFUSCATED_EMAIL_CONTEXT_PATTERN = re.compile(
    r"\b(?:email|e-mail|mail|reach|contact|dm|message|send\s+to|write\s+to)\b",
    re.I,
)
EXPLICIT_OBFUSCATED_EMAIL_MARKER_PATTERN = re.compile(
    r"\[\s*(?:at|dot)\s*\]|\(\s*(?:at|dot)\s*\)|_(?:at|dot)_",
    re.I,
)


PERSON_CONTEXT_PATTERNS: Sequence[tuple[re.Pattern[str], bool]] = (
    (
        re.compile(
            r"\b(?i:my name is|call me)\s+"
            rf"({NAME_PHRASE_PATTERN})\b"
        ),
        True,
    ),
    (
        re.compile(
            r"\b(?i:i am|i'm|this is)\s+"
            rf"({NAME_PHRASE_PATTERN})\b"
        ),
        False,
    ),
    (
        re.compile(
            r"\b(?i:reach|contact|message|dm|email|mail|write\s+to|send\s+to)\s+"
            rf"({NAME_PHRASE_PATTERN})\s+"
            r"(?i:at|via|on)\b"
        ),
        False,
    ),
    (
        re.compile(
            r"\b(?i:says|said|reports|reported|documented)\s+"
            rf"({NAME_PHRASE_PATTERN})\s+"
            r"(?:called|emailed|posted|quoted|replied|wrote|said)\b"
        ),
        False,
    ),
    (
        re.compile(
            r"\b(?i:(?:i|we|they|he|she|someone)\s+reported|reported)\s+"
            rf"({NAME_PHRASE_PATTERN})\s+"
            r"(?:because|for|after|when)\b"
        ),
        False,
    ),
    (
        re.compile(
            r"\b(?i:(?:i|we|they|he|she|someone)\s+"
            r"(?:met|saw|reported|called|contacted|messaged|emailed)|"
            r"met|saw|reported|call|called|contact|contacted|message|messaged|"
            r"email|emailed)\s+"
            r"(?!aged?\b|at\b|from\b|in\b|near\b|on\b|via\b|while\b|with\b)"
            rf"({NAME_PHRASE_PATTERN})\b"
        ),
        True,
    ),
    (
        re.compile(
            rf"\b({NAME_PHRASE_PATTERN})\s+"
            r"(?:said|emailed|called|posted|quoted|replied|wrote)\b"
        ),
        False,
    ),
    (
        re.compile(
            r"\b(?:said|emailed|called|posted|quoted|replied|wrote)\s+"
            rf"({NAME_PHRASE_PATTERN})\b"
        ),
        False,
    ),
    (
        re.compile(
            r"\b(?i:poor|dear|mr|mrs|ms|dr)\.?\s+"
            rf"({NAME_PHRASE_PATTERN})\b"
        ),
        False,
    ),
)


ALIAS_CONTEXT_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(
        r"\b(?i:alias|aka|a/k/a|known as|goes by)\s+"
        r"([A-Za-z][A-Za-z0-9._-]{2,64})\b"
    ),
)


LOCATION_CONTEXT_PATTERNS: Sequence[tuple[re.Pattern[str], bool]] = (
    (
        re.compile(
            r"\b(?i:from|in|near|at|works\s+at|studies\s+at|"
            r"meet\s+at|meets\s+at|met\s+at|lives\s+near|live\s+near)\s+"
            rf"({NAME_PHRASE_PATTERN})\b"
        ),
        True,
    ),
    (
        re.compile(
            r"\b(?i:leave|left|leaving|visit|visited|visiting|"
            r"move\s+to|moved\s+to|return\s+to|go\s+back\s+to|"
            r"deport\s+to|deported\s+to)\s+"
            rf"({NAME_PHRASE_PATTERN})\b"
        ),
        True,
    ),
)


KNOWN_LOCATION_TERMS: Sequence[str] = (
    "Boston",
    "Chicago",
    "London",
    "Los Angeles",
    "New York",
    "Paris",
    "San Francisco",
    "Washington",
)

PLACE_CONTEXT_SUFFIXES = {
    "academy",
    "airport",
    "avenue",
    "boulevard",
    "bridge",
    "campus",
    "center",
    "centre",
    "church",
    "clinic",
    "college",
    "court",
    "drive",
    "hospital",
    "institute",
    "lane",
    "library",
    "mosque",
    "park",
    "place",
    "road",
    "school",
    "square",
    "station",
    "street",
    "temple",
    "university",
    "way",
}
STREET_SUFFIX_WORDS = PLACE_CONTEXT_SUFFIXES | {
    "ave",
    "blvd",
    "ct",
    "dr",
    "ln",
    "rd",
    "sq",
    "st",
}
LOCATION_CONTEXT_BEFORE_PATTERN = re.compile(
    r"(?:^|\b(?:at|from|in|near|by|around|outside|inside|toward|towards|"
    r"meet(?:s|ing)?\s+at|met\s+at|live(?:s|d)?\s+(?:at|near|on)|"
    r"located\s+(?:at|near|on)|address\s+(?:is|at)|visit(?:ed|ing)?|"
    r"go(?:ing)?\s+to|walk(?:ed|ing)?\s+(?:down|on|to)|"
    r"driv(?:e|es|ing)\s+(?:down|on|to))\s+)$",
    re.I,
)

LOCATION_LEADING_REJECT_WORDS = {
    "a",
    "an",
    "at",
    "any",
    "dot",
    "every",
    "me",
    "my",
    "near",
    "on",
    "our",
    "poor",
    "that",
    "the",
    "their",
    "these",
    "this",
    "those",
    "your",
}

GENERIC_LOCATION_NOUNS = {
    "country",
    "home",
    "jail",
    "land",
    "prison",
    "world",
}

HIGH_CONFIDENCE_DIRECT_TYPES = frozenset(
    {
        "EMAIL",
        "PHONE",
        "URL",
        "USER",
        "IP_ADDRESS",
        "IDENTIFIER",
    }
)

CONTEXT_NAME_STOP_WORDS = {
    "after",
    "and",
    "are",
    "at",
    "because",
    "before",
    "belong",
    "belongs",
    "but",
    "called",
    "emailed",
    "for",
    "from",
    "in",
    "is",
    "like",
    "looks",
    "near",
    "on",
    "or",
    "posted",
    "replied",
    "said",
    "says",
    "should",
    "that",
    "to",
    "was",
    "were",
    "when",
    "who",
    "with",
    "wrote",
}

CONTEXT_PERSON_REJECT_WORDS = {
    "a",
    "age",
    "aged",
    "an",
    "any",
    "as",
    "everyone",
    "he",
    "her",
    "him",
    "i",
    "it",
    "me",
    "my",
    "our",
    "she",
    "someone",
    "that",
    "the",
    "their",
    "them",
    "these",
    "they",
    "this",
    "those",
    "us",
    "we",
    "while",
    "you",
}


@lru_cache(maxsize=1)
def action_context_terms() -> frozenset[str]:
    return frozenset(
        term.lower()
        for term in (
            set(load_utility_cue_terms("action_terms"))
            | set(load_utility_cue_terms("target_generalization_context"))
        )
    )


TARGET_GROUP_TERMS: dict[str, Sequence[str]] = load_target_group_terms()


CONTEXTUAL_TARGET_TERMS = {
    "boy",
    "boys",
    "black",
    "girl",
    "girls",
    "man",
    "men",
    "woman",
    "women",
}

TARGET_GENERALIZATION_CONTEXT_CUES = load_utility_cue_terms(
    "target_generalization_context"
)

VARIANT_TRANSLATION = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "@": "a",
        "$": "s",
    }
)
VARIANT_TOKEN_PATTERN = re.compile(r"#?[A-Za-z0-9_@$]{4,}")
SPACED_FRAGMENT_PATTERN = re.compile(r"#?[A-Za-z0-9_@$]{1,8}")
EXTERNAL_TARGET_CATEGORIES = frozenset({"slur_or_profanity"})
TARGET_GROUP_CATEGORIES = frozenset(TARGET_GROUP_TERMS) | EXTERNAL_TARGET_CATEGORIES
_EXTERNAL_PROFANITY_LOADED = False
IMPLICIT_TARGET_ORG_TERMS = {
    "mosque": "religion",
    "synagogue": "religion",
    "temple": "religion",
    "church": "religion",
}
TARGET_ORG_PRIVACY_CONTEXT_PATTERN = re.compile(
    r"(?:"
    r"\b(?:work(?:s|ed|ing)?|stud(?:y|ies|ied|ying)|"
    r"attend(?:s|ed|ing)?|teach(?:es|ing|taught)?|"
    r"employ(?:ed|ee|er|s|ing)?|staff|student|contact|reach|"
    r"email|mail|call|message|meet|met|from)\b.{0,48}"
    r"\b(?:at|from|in|near|via|on)\s*"
    r"|\b(?:at|from|in|near)\s*"
    r")$",
    re.I | re.S,
)
TARGET_ORG_LEADING_STOP_WORDS = {
    "a",
    "an",
    "against",
    "at",
    "by",
    "condemn",
    "contact",
    "documented",
    "email",
    "from",
    "hate",
    "i",
    "in",
    "mail",
    "message",
    "near",
    "on",
    "reported",
    "reach",
    "said",
    "saying",
    "the",
    "to",
    "via",
    "work",
    "works",
    "worked",
    "working",
}


@lru_cache(maxsize=8192)
def contains_external_profanity(value: str) -> bool:
    """Query the external profanity/slur lexicon without exposing its word list."""
    global _EXTERNAL_PROFANITY_LOADED
    if _external_profanity is None:
        return False
    candidate = value.strip()
    if len(compact_variant(candidate)) < 3:
        return False
    if not _EXTERNAL_PROFANITY_LOADED:
        _external_profanity.load_censor_words()
        _EXTERNAL_PROFANITY_LOADED = True
    return bool(_external_profanity.contains_profanity(candidate))


def contains_target_group_term(value: str) -> bool:
    """Return whether a candidate span is itself a protected target cue."""
    for _category, _term, pattern in target_group_term_patterns():
        if pattern.search(value):
            return True
    return False


def phrase_present(value: str, phrase: str) -> bool:
    pattern = re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])",
        re.I,
    )
    return bool(pattern.search(value))


def target_org_privacy_context(text: str, start: int) -> bool:
    before = text[max(0, start - 90) : start]
    return bool(TARGET_ORG_PRIVACY_CONTEXT_PATTERN.search(before))


def target_org_preservation_context(text: str, start: int, end: int) -> bool:
    """Return whether an org mention is likely the relevant HSD target."""
    window = text[max(0, start - 90) : min(len(text), end + 120)]
    return any(phrase_present(window, term) for term in action_context_terms())


def target_org_cue_spans(text: str, start: int, end: int) -> list[Span]:
    """Find protected-group or protected-institution cues inside an org span."""
    value = text[start:end]
    spans: list[Span] = []
    for category, _term, pattern in target_group_term_patterns():
        for match in pattern.finditer(value):
            spans.append(
                Span(
                    start=start + match.start(),
                    end=start + match.end(),
                    entity_type="TARGET_GROUP",
                    text=match.group(0),
                    score=0.71,
                    source="target_org_dictionary",
                    category=category,
                )
            )
    if spans:
        return merge_spans(spans)
    for term, category in IMPLICIT_TARGET_ORG_TERMS.items():
        pattern = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])",
            re.I,
        )
        for match in pattern.finditer(value):
            spans.append(
                Span(
                    start=start + match.start(),
                    end=start + match.end(),
                    entity_type="TARGET_GROUP",
                    text=match.group(0),
                    score=0.66,
                    source="target_org_institution",
                    category=category,
                )
            )
    return merge_spans(spans)


def target_org_replacement(
    text: str,
    start: int,
    end: int,
) -> tuple[str, str] | None:
    """Return a cue-preserving org mask such as 'Jewish [ORG]' when warranted."""
    cue_spans = target_org_cue_spans(text, start, end)
    if not cue_spans:
        return None
    if target_org_privacy_context(text, start):
        return None
    if not target_org_preservation_context(text, start, end):
        return None
    cue_text = " ".join(span.text for span in cue_spans)
    categories = sorted({span.category for span in cue_spans if span.category})
    category = "target_org:" + ",".join(categories) if categories else "target_org"
    return f"{cue_text} [ORG]", category


def target_org_candidate_range(text: str, start: int, end: int) -> tuple[int, int]:
    cue_spans = target_org_cue_spans(text, start, end)
    if not cue_spans:
        return start, end
    first_cue_start = min(span.start for span in cue_spans)
    prefix_words = list(re.finditer(NAME_WORD_PATTERN, text[start:first_cue_start]))
    included: list[re.Match[str]] = []
    for word_match in reversed(prefix_words):
        word = word_match.group(0).lower()
        if word in TARGET_ORG_LEADING_STOP_WORDS or word in action_context_terms():
            break
        included.append(word_match)
        if len(included) >= 2:
            break
    if included:
        return start + min(word.start() for word in included), end
    return first_cue_start, end


def target_org_case_insensitive_spans(text: str) -> list[Span]:
    """Case-insensitive target-organization spans for lower/mixed-case rows.

    The broad organization detector stays title-case to avoid masking ordinary
    lowercase phrases. This path only emits a span when a protected cue appears
    inside the organization and the surrounding context makes masking useful.
    """
    spans: list[Span] = []
    for match in TARGET_ORG_PATTERN.finditer(text):
        start, end = target_org_candidate_range(text, match.start(), match.end())
        value = text[start:end]
        if not target_org_cue_spans(text, start, end):
            continue
        replacement_context = target_org_replacement(
            text,
            start,
            end,
        )
        if replacement_context:
            replacement, category = replacement_context
            spans.append(
                Span(
                    start=start,
                    end=end,
                    entity_type="ORGANIZATION",
                    text=value,
                    score=0.82,
                    source="regex_target_org",
                    category=category,
                    replacement=replacement,
                )
            )
            continue
        if target_org_privacy_context(text, start):
            spans.append(
                Span(
                    start=start,
                    end=end,
                    entity_type="ORGANIZATION",
                    text=value,
                    score=0.78,
                    source="regex_target_org_privacy",
                )
            )
    return spans


def trim_context_span(
    text: str,
    start: int,
    end: int,
    *,
    require_titlecase: bool = False,
    stop_at_connector: bool = False,
) -> tuple[int, int, str]:
    """Trim connector words from context-captured names/locations."""
    value = text[start:end].strip()
    leading = len(text[start:end]) - len(text[start:end].lstrip())
    start += leading
    end = start + len(value)
    while value:
        words = list(re.finditer(NAME_WORD_PATTERN, value))
        if not words:
            return start, start, ""
        if require_titlecase:
            if words[0].start() != 0:
                return start, start, ""
            last_end = 0
            for word_match in words:
                word = value[word_match.start() : word_match.end()]
                if not word[:1].isupper():
                    break
                last_end = word_match.end()
            if not last_end:
                return start, start, ""
            value = value[:last_end].rstrip()
            end = start + len(value)
            break
        if stop_at_connector and len(words) > 1:
            for word_match in words[1:]:
                word = value[word_match.start() : word_match.end()].lower()
                if word in CONTEXT_NAME_STOP_WORDS:
                    value = value[: word_match.start()].rstrip()
                    end = start + len(value)
                    break
        last = words[-1]
        last_word = value[last.start() : last.end()].lower()
        if last_word not in CONTEXT_NAME_STOP_WORDS:
            break
        value = value[: last.start()].rstrip()
        end = start + len(value)
    return start, end, value


def trim_leading_action_word(
    text: str,
    start: int,
    end: int,
    value: str,
) -> tuple[int, int, str]:
    words = list(re.finditer(NAME_WORD_PATTERN, value))
    if len(words) < 2:
        return start, end, value
    first_word = value[words[0].start() : words[0].end()].lower()
    if first_word not in action_context_terms():
        return start, end, value
    new_start = start + words[1].start()
    new_value = value[words[1].start() :].strip()
    leading = len(value[words[1].start() :]) - len(value[words[1].start() :].lstrip())
    new_start += leading
    new_end = new_start + len(new_value)
    return new_start, new_end, new_value


@lru_cache(maxsize=8192)
def rejected_context_person_candidate(value: str) -> bool:
    """Reject words that look grammatical, hostile, or abusive rather than name-like."""
    words = [match.group(0) for match in re.finditer(NAME_WORD_PATTERN, value)]
    if not words:
        return True
    lowered = [word.lower() for word in words]
    if any(word in CONTEXT_PERSON_REJECT_WORDS for word in lowered):
        return True
    if lowered[-1] in PLACE_CONTEXT_SUFFIXES and not any(
        word[:1].isupper() for word in words
    ):
        return True
    if len(words) == 1 and lowered[0] in action_context_terms():
        return True
    return any(contains_external_profanity(word) for word in words)


def location_words(value: str) -> list[str]:
    return [match.group(0) for match in re.finditer(NAME_WORD_PATTERN, value)]


def has_location_prefix_context(text: str | None, start: int | None) -> bool:
    if text is None or start is None:
        return False
    before = text[max(0, start - 80) : start]
    return start == 0 or bool(LOCATION_CONTEXT_BEFORE_PATTERN.search(before))


def rejected_location_candidate(
    value: str,
    *,
    text: str | None = None,
    start: int | None = None,
) -> bool:
    words = location_words(value)
    if not words:
        return True
    lowered = [word.lower() for word in words]
    if len(lowered) == 1 and lowered[0] in GENERIC_LOCATION_NOUNS:
        return True
    if lowered[0] in LOCATION_LEADING_REJECT_WORDS:
        return True
    if any(word in action_context_terms() for word in lowered):
        return True
    if contains_target_group_term(value):
        return True
    if any(contains_external_profanity(word) for word in words):
        return True
    known_locations = {term.lower() for term in KNOWN_LOCATION_TERMS}
    if value.lower() in known_locations:
        return False
    suffix = lowered[-1].rstrip(".")
    if suffix in STREET_SUFFIX_WORDS:
        if len(words) < 2:
            return True
        if words[0][:1].isupper():
            return False
        return not has_location_prefix_context(text, start)
    if any(word[:1].isupper() for word in words):
        return False
    return True


def placeholder_adjacent_context(text: str, start: int, end: int) -> bool:
    """Avoid re-detecting words created by earlier placeholder insertion."""

    before = text[max(0, start - 16) : start].rstrip()
    after = text[end : min(len(text), end + 16)].lstrip()
    return before.endswith("]") or after.startswith("[")


def high_confidence_direct_identifier_spans(text: str) -> list[Span]:
    """Return only direct residual identifiers that are safe to auto-clean."""
    return merge_spans(
        [
            span
            for span in regex_spans(text)
            if span.entity_type in HIGH_CONFIDENCE_DIRECT_TYPES
        ]
    )


def adjacent_user_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for match in ADJACENT_USER_PATTERN.finditer(text):
        start = match.start()
        if start == 0:
            continue
        previous = text[start - 1]
        if previous not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-":
            continue
        previous_at = text.rfind("@", 0, start)
        if previous_at < 0:
            continue
        previous_handle = text[previous_at + 1 : start]
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", previous_handle):
            continue
        spans.append(
            Span(
                start=start,
                end=match.end(),
                entity_type="USER",
                text=match.group(0),
                score=0.85,
                source="regex",
            )
        )
    return spans


def has_obfuscated_email_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 40) : min(len(text), end + 40)]
    return bool(OBFUSCATED_EMAIL_CONTEXT_PATTERN.search(window))


def obfuscated_email_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for match in OBFUSCATED_EMAIL_PATTERN.finditer(text):
        value = match.group(0)
        if len(value) > 120:
            continue
        local = match.group("local")
        tld = match.group("tld")
        if len(re.sub(r"[^A-Za-z0-9]", "", local)) < 2 or len(tld) < 2:
            continue
        if contains_target_group_term(local) or local.lower() in action_context_terms():
            continue
        if not EXPLICIT_OBFUSCATED_EMAIL_MARKER_PATTERN.search(
            value
        ) and not has_obfuscated_email_context(text, match.start(), match.end()):
            continue
        spans.append(
            Span(
                start=match.start(),
                end=match.end(),
                entity_type="EMAIL",
                text=value,
                score=0.86,
                source="regex_obfuscated_email",
            )
        )
    return spans


def regex_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for entity_type, pattern in REGEX_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if entity_type == "LOCATION":
                if rejected_location_candidate(
                    value,
                    text=text,
                    start=match.start(),
                ):
                    continue
            category = None
            replacement = None
            source = "regex"
            if entity_type == "ORGANIZATION":
                target_org = target_org_replacement(text, match.start(), match.end())
                if target_org:
                    replacement, category = target_org
                    source = "regex_target_org"
            spans.append(
                Span(
                    start=match.start(),
                    end=match.end(),
                    entity_type=entity_type,
                    text=value,
                    score=0.85,
                    source=source,
                    category=category,
                    replacement=replacement,
                )
            )
    spans.extend(obfuscated_email_spans(text))
    spans.extend(adjacent_user_spans(text))
    spans.extend(target_org_case_insensitive_spans(text))
    return spans


def known_location_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for term in KNOWN_LOCATION_TERMS:
        pattern = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
        )
        for match in pattern.finditer(text):
            spans.append(
                Span(
                    start=match.start(),
                    end=match.end(),
                    entity_type="LOCATION",
                    text=match.group(0),
                    score=0.62,
                    source="known_location",
                )
            )
    return spans


def context_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for pattern, allow_lowercase in PERSON_CONTEXT_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(1)
            start, end, value = trim_context_span(
                text,
                start,
                end,
                require_titlecase=not allow_lowercase,
                stop_at_connector=allow_lowercase,
            )
            if not value:
                continue
            start, end, value = trim_leading_action_word(text, start, end, value)
            if not value:
                continue
            if contains_target_group_term(value):
                continue
            if rejected_context_person_candidate(value):
                continue
            if placeholder_adjacent_context(text, start, end):
                continue
            spans.append(
                Span(start, end, "PERSON", value, 0.72, "context_person")
            )
    for pattern in ALIAS_CONTEXT_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(1)
            spans.append(
                Span(start, end, "ALIAS", text[start:end], 0.7, "context_alias")
            )
    for pattern, allow_lowercase in LOCATION_CONTEXT_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(1)
            start, end, value = trim_context_span(
                text,
                start,
                end,
                require_titlecase=not allow_lowercase,
                stop_at_connector=allow_lowercase,
            )
            if not value:
                continue
            if rejected_location_candidate(value, text=text, start=start):
                continue
            if placeholder_adjacent_context(text, start, end):
                continue
            spans.append(
                Span(start, end, "LOCATION", value, 0.65, "context_location")
            )
    return spans


def external_profanity_candidate_spans(text: str) -> list[tuple[int, int, str, str]]:
    candidates: list[tuple[int, int, str, str]] = []
    for match in VARIANT_TOKEN_PATTERN.finditer(text):
        raw_value = match.group(0)
        normalized_value = compact_variant(raw_value.lstrip("#"))
        if contains_external_profanity(raw_value) or contains_external_profanity(
            normalized_value
        ):
            candidates.append((match.start(), match.end(), raw_value, normalized_value))
    for start, end, raw_value, normalized_value in spaced_fragment_windows(text):
        if contains_external_profanity(normalized_value):
            candidates.append((start, end, raw_value, normalized_value))
    return candidates


def has_explicit_target_generalization_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 80) : min(len(text), end + 80)].lower()
    for cue in TARGET_GENERALIZATION_CONTEXT_CUES:
        pattern = r"(?<![a-z0-9])" + re.escape(cue) + r"(?![a-z0-9])"
        if re.search(pattern, window):
            return True
        normalized_cue = compact_variant(cue)
        if len(normalized_cue) >= 4:
            for _start, _end, _raw, normalized_value in spaced_fragment_windows(window):
                if normalized_value == normalized_cue:
                    return True
    return False


def has_predicative_external_abuse_context(text: str, start: int, end: int) -> bool:
    window_start = max(0, start - 80)
    window = text[window_start : min(len(text), end + 80)]
    local_start = start - window_start
    local_end = end - window_start
    for profane_start, profane_end, _raw, _normalized in external_profanity_candidate_spans(
        window
    ):
        if profane_start >= local_start and profane_end <= local_end:
            continue
        between_start = min(local_end, profane_end)
        between_end = max(local_start, profane_start)
        between = window[between_start:between_end].lower()
        if re.search(r"\b(?:are|is|was|were|be|being|seem|seems|look|looks)\b", between):
            return True
    return False


def has_target_generalization_context(text: str, start: int, end: int) -> bool:
    return has_explicit_target_generalization_context(
        text,
        start,
        end,
    ) or has_predicative_external_abuse_context(text, start, end)


def compact_variant(value: str) -> str:
    normalized = value.lower().translate(VARIANT_TRANSLATION)
    compact = re.sub(r"[^a-z0-9]", "", normalized)
    if not compact:
        return ""
    collapsed: list[str] = []
    for character in compact:
        if len(collapsed) >= 2 and collapsed[-1] == character and collapsed[-2] == character:
            continue
        collapsed.append(character)
    return "".join(collapsed)


def spaced_fragment_windows(
    text: str,
    *,
    max_fragments: int = 8,
) -> list[tuple[int, int, str, str]]:
    fragments = list(SPACED_FRAGMENT_PATTERN.finditer(text))
    windows: list[tuple[int, int, str, str]] = []
    for start_index, start_match in enumerate(fragments):
        for end_index in range(
            start_index + 1,
            min(len(fragments), start_index + max_fragments) + 1,
        ):
            if end_index == start_index:
                continue
            end_match = fragments[end_index - 1]
            if end_match.start() == start_match.start():
                continue
            if end_index - start_index < 2:
                continue
            raw_value = text[start_match.start() : end_match.end()]
            if not re.search(r"[\s._*|-]", raw_value):
                continue
            normalized_value = compact_variant(raw_value.lstrip("#"))
            windows.append(
                (start_match.start(), end_match.end(), raw_value, normalized_value)
            )
    return windows


def edit_distance_at_most_one(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        mismatches = sum(1 for a, b in zip(left, right) if a != b)
        return mismatches <= 1
    if len(left) > len(right):
        left, right = right, left
    i = 0
    j = 0
    edits = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        j += 1
    return True


def hashtag_target_group_spans(text: str) -> list[Span]:
    """Detect target terms embedded in simple hashtags such as StarvingAfricans."""
    spans: list[Span] = []
    for hashtag_match in re.finditer(r"#[A-Za-z0-9_]{3,}", text):
        body = hashtag_match.group(0)[1:]
        lowered_body = body.lower()
        for category, terms in TARGET_GROUP_TERMS.items():
            for term in terms:
                compact_term = re.sub(r"[^a-z0-9]", "", term.lower())
                if len(compact_term) < 4:
                    continue
                start_in_body = lowered_body.find(compact_term)
                if start_in_body < 0:
                    continue
                matched_start = hashtag_match.start() + 1 + start_in_body
                matched_end = matched_start + len(compact_term)
                if (
                    term.lower() in CONTEXTUAL_TARGET_TERMS
                    and not has_target_generalization_context(
                        text,
                        matched_start,
                        matched_end,
                    )
                ):
                    continue
                spans.append(
                    Span(
                        start=hashtag_match.start(),
                        end=hashtag_match.end(),
                        entity_type="TARGET_GROUP",
                        text=hashtag_match.group(0),
                        score=0.62,
                        source="target_hashtag",
                        category=category,
                    )
                )
    return spans


def variant_target_group_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for match in VARIANT_TOKEN_PATTERN.finditer(text):
        raw_value = match.group(0)
        normalized_value = compact_variant(raw_value.lstrip("#"))
        if len(normalized_value) < 5:
            continue
        for category, terms in TARGET_GROUP_TERMS.items():
            for term in terms:
                normalized_term = compact_variant(term)
                if len(normalized_term) < 5:
                    continue
                if not edit_distance_at_most_one(normalized_value, normalized_term):
                    continue
                if (
                    term.lower() in CONTEXTUAL_TARGET_TERMS
                    and not has_target_generalization_context(
                        text,
                        match.start(),
                        match.end(),
                    )
                ):
                    continue
                if not has_target_generalization_context(text, match.start(), match.end()):
                    continue
                spans.append(
                    Span(
                        start=match.start(),
                        end=match.end(),
                        entity_type="TARGET_GROUP",
                        text=raw_value,
                        score=0.58,
                        source="target_variant",
                        category=category,
                    )
                )
    return spans


def spaced_variant_target_group_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for start, end, raw_value, normalized_value in spaced_fragment_windows(text):
        if len(normalized_value) < 5:
            continue
        for category, terms in TARGET_GROUP_TERMS.items():
            for term in terms:
                normalized_term = compact_variant(term)
                if len(normalized_term) < 5:
                    continue
                if not edit_distance_at_most_one(normalized_value, normalized_term):
                    continue
                if (
                    term.lower() in CONTEXTUAL_TARGET_TERMS
                    and not has_target_generalization_context(
                        text,
                        start,
                        end,
                    )
                ):
                    continue
                if not has_target_generalization_context(text, start, end):
                    continue
                spans.append(
                    Span(
                        start=start,
                        end=end,
                        entity_type="TARGET_GROUP",
                        text=raw_value,
                        score=0.57,
                        source="target_spaced_variant",
                        category=category,
                    )
                )
    return spans


def external_profane_target_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for start, end, raw_value, normalized_value in external_profanity_candidate_spans(text):
        if len(normalized_value) < 4:
            continue
        if not (
            has_explicit_target_generalization_context(text, start, end)
            or has_predicative_external_abuse_context(text, start, end)
        ):
            continue
        spans.append(
            Span(
                start=start,
                end=end,
                entity_type="TARGET_GROUP",
                text=raw_value,
                score=0.54,
                source="external_profanity_lexicon",
                category="slur_or_profanity",
            )
        )
    return spans


@lru_cache(maxsize=1)
def target_group_term_patterns() -> tuple[tuple[str, str, re.Pattern[str]], ...]:
    patterns: list[tuple[str, str, re.Pattern[str]]] = []
    for category, terms in TARGET_GROUP_TERMS.items():
        for term in terms:
            patterns.append(
                (
                    category,
                    term,
                    re.compile(
                        r"(?<![A-Za-z0-9])"
                        + re.escape(term)
                        + r"(?![A-Za-z0-9])",
                        re.I,
                    ),
                )
            )
    return tuple(patterns)


def target_group_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for category, term, pattern in target_group_term_patterns():
        for match in pattern.finditer(text):
            if (
                term.lower() in CONTEXTUAL_TARGET_TERMS
                and not has_target_generalization_context(
                    text,
                    match.start(),
                    match.end(),
                )
            ):
                continue
            spans.append(
                Span(
                    start=match.start(),
                    end=match.end(),
                    entity_type="TARGET_GROUP",
                    text=match.group(0),
                    score=0.7,
                    source="target_dictionary",
                    category=category,
                )
            )
    spans.extend(hashtag_target_group_spans(text))
    spans.extend(variant_target_group_spans(text))
    spans.extend(spaced_variant_target_group_spans(text))
    spans.extend(external_profane_target_spans(text))
    return merge_spans(spans)


def span_priority(span: Span) -> tuple[int, float, int]:
    source_priority = {
        "regex": 3,
        "regex_target_org": 3,
        "regex_target_org_privacy": 3,
        "regex_obfuscated_email": 3,
        "context_person": 2,
        "context_alias": 2,
        "context_location": 1,
        "known_location": 1,
        "target_dictionary": 0,
        "target_hashtag": 0,
        "target_variant": 0,
        "target_spaced_variant": 0,
        "external_profanity_lexicon": 0,
    }.get(span.source, 0)
    return (span.end - span.start, span.score, source_priority)


def merge_spans(spans: Iterable[Span]) -> list[Span]:
    chosen: list[Span] = []
    for span in sorted(spans, key=span_priority, reverse=True):
        overlaps = [
            existing
            for existing in chosen
            if span.start < existing.end and span.end > existing.start
        ]
        if not overlaps:
            chosen.append(span)
            continue
        for existing in overlaps:
            if (
                span.start == existing.start
                and span.end == existing.end
                and span.entity_type == existing.entity_type
            ):
                break
    return sorted(chosen, key=lambda item: (item.start, item.end))


def detect_spans(
    text: str,
    *,
    include_context: bool = True,
    include_targets: bool = False,
) -> list[Span]:
    spans: list[Span] = []
    spans.extend(regex_spans(text))
    if include_context:
        spans.extend(context_spans(text))
        spans.extend(known_location_spans(text))
    if include_targets:
        spans.extend(target_group_spans(text))
    return merge_spans(spans)
