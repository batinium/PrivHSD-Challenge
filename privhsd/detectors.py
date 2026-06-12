"""Deterministic span detectors for privacy-sensitive text.

The challenge needs a reliable baseline that runs locally and is explainable.
These detectors intentionally focus on direct identifiers and conservative
quasi-identifiers. Target-group detection is separated so it can be enabled only
when a run explicitly wants group-category generalization.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    entity_type: str
    text: str
    score: float
    source: str
    category: str | None = None

    def replacement_tag(self) -> str:
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


REGEX_PATTERNS: Sequence[tuple[str, re.Pattern[str]]] = (
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("URL", re.compile(r"\b(?:https?://|www\.)[^\s<>()]+", re.I)),
    ("USER", re.compile(r"(?<!\w)@[A-Za-z0-9._-]{2,64}\b")),
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
            r"(?:University|College|Institute|Academy|School|Centre|Center)\b"
        ),
    ),
    (
        "LOCATION",
        re.compile(
            r"\b(?:[A-Z][A-Za-z0-9.'-]+\s+){0,4}[A-Z][A-Za-z0-9.'-]+\s+"
            r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|"
            r"Lane|Ln\.?|Drive|Dr\.?|Court|Ct\.?|Way|Place|Pl\.?|"
            r"Square|Sq\.?)\b"
        ),
    ),
)


PERSON_CONTEXT_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(
        r"\b(?i:my name is|i am|i'm|this is|call me)\s+"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b"
    ),
    re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s+"
        r"(?:said|emailed|called|posted|replied|wrote)\b"
    ),
    re.compile(
        r"\b(?:said|emailed|called|posted|replied|wrote)\s+"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b"
    ),
)


ALIAS_CONTEXT_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(
        r"\b(?i:alias|aka|a/k/a|known as|goes by)\s+"
        r"([A-Za-z][A-Za-z0-9._-]{2,64})\b"
    ),
)


LOCATION_CONTEXT_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(
        r"\b(?i:from|in|near|at)\s+"
        r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,3})\b"
    ),
    re.compile(
        r"\b(?i:leave|left|leaving|visit|visited|visiting|"
        r"move\s+to|moved\s+to|return\s+to|go\s+back\s+to|"
        r"deport\s+to|deported\s+to)\s+"
        r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,3})\b"
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


TARGET_GROUP_TERMS: dict[str, Sequence[str]] = {
    "nationality_or_origin": (
        "immigrant",
        "immigrants",
        "migrant",
        "migrants",
        "refugee",
        "refugees",
        "foreigner",
        "foreigners",
        "foreign national",
        "foreign nationals",
        "asylum seeker",
        "asylum seekers",
        "arab",
        "arabs",
        "chinese people",
        "chinese",
        "indian",
        "indians",
        "french",
        "romanian",
        "romanians",
    ),
    "religion": (
        "muslim",
        "muslims",
        "muslim people",
        "muslim community",
        "muslim communities",
        "jew",
        "jews",
        "jewish",
        "jewish people",
        "jewish community",
        "jewish communities",
        "heeb",
        "heebs",
        "kike",
        "kikes",
        "christian",
        "christians",
        "hindu",
        "hindus",
        "sikh",
        "sikhs",
    ),
    "gender": (
        "woman",
        "women",
        "man",
        "men",
        "girl",
        "girls",
        "boy",
        "boys",
        "trans woman",
        "trans women",
        "trans man",
        "trans men",
        "trans person",
        "trans people",
        "nonbinary people",
        "non-binary people",
    ),
    "sexual_orientation": (
        "gay",
        "gays",
        "gay people",
        "lesbian",
        "lesbians",
        "lesbian people",
        "bisexual",
        "bisexuals",
        "bisexual people",
        "homosexual",
        "homosexuals",
        "lgbt",
        "lgbt people",
        "lgbtq",
        "lgbtq people",
        "lgbtqi",
        "lgbtqia",
        "same-sex couples",
        "queer",
        "queers",
        "fag",
        "fags",
        "poof",
        "poofs",
    ),
    "disability": (
        "disabled",
        "disabled people",
        "disabled persons",
        "disabled students",
        "people with disabilities",
        "autistic",
        "autistic people",
        "deaf",
        "deaf people",
        "blind",
        "blind people",
        "retard",
        "retards",
        "tard",
        "tards",
        "mong",
        "mongs",
        "mongo",
        "mongos",
    ),
    "race_or_ethnicity": (
        "african",
        "africans",
        "african people",
        "black people",
        "black community",
        "black communities",
        "asian people",
        "asian",
        "asians",
        "roma",
        "roma people",
        "romani",
        "sinti",
        "gypsy",
        "gypsies",
        "traveller",
        "travellers",
        "people of color",
        "people of colour",
        "latino people",
        "hispanic people",
        "dalit",
        "dalits",
        "chink",
        "chinks",
        "nigga",
        "niggas",
        "nigger",
        "niggers",
    ),
    "historical_victim_group": (
        "holocaust survivors",
        "shoah survivors",
        "genocide survivors",
        "concentration camp survivors",
        "auschwitz survivors",
        "mauthausen survivors",
    ),
}


CONTEXTUAL_TARGET_TERMS = {
    "boy",
    "boys",
    "girl",
    "girls",
    "man",
    "men",
    "woman",
    "women",
}

TARGET_GENERALIZATION_CONTEXT_CUES = (
    "attack",
    "ban",
    "deport",
    "deported",
    "do not belong",
    "destroy",
    "eliminate",
    "eradicate",
    "exterminate",
    "exclude",
    "excluded",
    "hate",
    "inferior",
    "kill",
    "killed",
    "killing",
    "kills",
    "not belong",
    "scum",
    "should leave",
    "threat",
    "violent",
    "violence",
    "vermin",
    "worthless",
)


def contains_target_group_term(value: str) -> bool:
    """Return whether a candidate span is itself a protected target cue."""
    lowered = value.lower()
    for terms in TARGET_GROUP_TERMS.values():
        for term in terms:
            pattern = r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])"
            if re.search(pattern, lowered):
                return True
    return False


def regex_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for entity_type, pattern in REGEX_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if entity_type == "LOCATION" and contains_target_group_term(value):
                continue
            spans.append(
                Span(
                    start=match.start(),
                    end=match.end(),
                    entity_type=entity_type,
                    text=value,
                    score=0.85,
                    source="regex",
                )
            )
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
    for pattern in PERSON_CONTEXT_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(1)
            value = text[start:end]
            if contains_target_group_term(value):
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
    for pattern in LOCATION_CONTEXT_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(1)
            value = text[start:end]
            if value.lower() in {"the", "a", "an"} or contains_target_group_term(value):
                continue
            spans.append(
                Span(start, end, "LOCATION", value, 0.65, "context_location")
            )
    return spans


def has_target_generalization_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 80) : min(len(text), end + 80)].lower()
    for cue in TARGET_GENERALIZATION_CONTEXT_CUES:
        pattern = r"(?<![a-z0-9])" + re.escape(cue) + r"(?![a-z0-9])"
        if re.search(pattern, window):
            return True
    return False


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


def target_group_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for category, terms in TARGET_GROUP_TERMS.items():
        for term in terms:
            pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)
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
    return merge_spans(spans)


def span_priority(span: Span) -> tuple[int, float, int]:
    source_priority = {
        "regex": 3,
        "context_person": 2,
        "context_alias": 2,
        "context_location": 1,
        "known_location": 1,
        "target_dictionary": 0,
        "target_hashtag": 0,
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
