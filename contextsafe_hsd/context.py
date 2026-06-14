"""Deterministic row-context tags for HSD preservation audits.

The tags are advisory audit features, not legal conclusions. They help reports
and candidate scorers identify rows where target/action/negation context should
be protected with extra care.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .detectors import TARGET_GROUP_TERMS, target_group_spans
from .style import ACTION_TERMS


CONTEXT_TAGS = (
    "protected_target",
    "historical_victim_group",
    "hostile_action",
    "threat",
    "dehumanization",
    "exclusion",
    "negated_hate",
    "counterspeech",
    "quoted_or_reported",
    "public_interest_or_institutional_criticism",
    "offensive_only_risk",
    "missing_context",
)

THREAT_TERMS = {
    "attack",
    "attacks",
    "attacked",
    "attacking",
    "kill",
    "kills",
    "killed",
    "killing",
    "murder",
    "murdered",
    "murdering",
    "shoot",
    "shooting",
    "threat",
    "threaten",
    "threatened",
    "threatening",
    "violence",
    "violent",
}

DEHUMANIZATION_TERMS = {
    "burden",
    "filthy",
    "inbred",
    "inferior",
    "scum",
    "subhuman",
    "vermin",
    "worthless",
}

EXCLUSION_TERMS = {
    "ban",
    "banned",
    "deport",
    "deported",
    "deporting",
    "exclude",
    "excluded",
    "leave",
    "remove",
    "removed",
    "segregate",
}

EXCLUSION_PHRASES = (
    "do not belong",
    "don't belong",
    "go back",
    "not belong",
    "should leave",
)

NEGATION_PATTERNS = (
    r"\bdo\s+not\s+\w+",
    r"\bdon't\s+\w+",
    r"\bnever\s+\w+",
    r"\bno\s+one\s+should\s+\w+",
    r"\bshould\s+not\s+\w+",
    r"\bshouldn't\s+\w+",
    r"\bnot\s+(?:hate|attack|threaten|kill|deport|exclude)\b",
)

COUNTERSPEECH_PATTERNS = (
    r"\b(?:stop|oppose|reject|fight|condemn|call\s+out)\s+"
    r"(?:hate|racism|antisemitism|islamophobia|homophobia|transphobia)\b",
    r"\b(?:racism|antisemitism|islamophobia|homophobia|transphobia)\s+"
    r"(?:is|are)\s+(?:wrong|unacceptable|bad)\b",
    r"\bstand\s+with\b",
    r"\bsupport\s+(?:refugees|immigrants|muslims|jews|women|disabled|"
    r"trans|gay|lgbt)\b",
    r"\bdo\s+not\s+(?:attack|threaten|hate|deport|exclude)\b",
)

QUOTE_REPORT_PATTERNS = (
    r'["\'].+?["\']',
    r"\b(?:said|says|called|reported|reports|quoted|quotes|documented|"
    r"documenting|wrote|posted)\b",
)

PUBLIC_INTEREST_TERMS = {
    "court",
    "government",
    "institution",
    "minister",
    "official",
    "parliament",
    "police",
    "policy",
    "president",
    "prime minister",
    "state",
}

PUBLIC_CRITICISM_TERMS = {
    "abuse",
    "corrupt",
    "corruption",
    "criticize",
    "criticised",
    "criticized",
    "failed",
    "incompetent",
    "protest",
    "resign",
}

OFFENSIVE_ONLY_TERMS = {
    "asshole",
    "bastard",
    "crap",
    "dumb",
    "fool",
    "idiot",
    "jerk",
    "moron",
    "stupid",
    "trash",
}

BLANK_TARGET_VALUES = {
    "",
    "none",
    "notgiven",
    "not_given",
    "nan",
    "null",
    "[]",
    "['none']",
}


def phrase_count(text: str, phrase: str) -> int:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"
    return len(re.findall(pattern, text.lower()))


def has_any_term(text: str, terms: set[str]) -> bool:
    return any(phrase_count(text, term) for term in terms)


def has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.I | re.S) for pattern in patterns)


def metadata_has_target(metadata: Mapping[str, Any] | None) -> bool:
    if not metadata:
        return False
    for key in ("target", "target_categories"):
        value = str(metadata.get(key, "") or "").strip().lower()
        if value and value not in BLANK_TARGET_VALUES:
            return True
    return False


def historical_victim_group_detected(
    text: str,
    spans: list[Any] | None = None,
) -> bool:
    spans = spans if spans is not None else target_group_spans(text)
    if any(span.category == "historical_victim_group" for span in spans):
        return True
    lowered = text.lower()
    return any(
        phrase_count(lowered, term)
        for term in TARGET_GROUP_TERMS.get("historical_victim_group", ())
    )


def analyze_context(
    text: str,
    metadata: Mapping[str, Any] | None = None,
    protected_target: bool | None = None,
    historical_victim_group: bool | None = None,
) -> dict[str, Any]:
    """Return deterministic context tags and reason counts without raw text."""
    value = text or ""
    lowered = value.lower()
    tags: set[str] = set()
    reasons: set[str] = set()

    if protected_target is None:
        target_spans = target_group_spans(value)
        target_present = bool(target_spans) or metadata_has_target(metadata)
    else:
        target_spans = []
        target_present = protected_target or metadata_has_target(metadata)
    if historical_victim_group is None:
        historical_victim_group = historical_victim_group_detected(value, target_spans)
    hostile_action = has_any_term(lowered, set(ACTION_TERMS))
    threat = has_any_term(lowered, THREAT_TERMS)
    dehumanization = has_any_term(lowered, DEHUMANIZATION_TERMS)
    exclusion = has_any_term(lowered, EXCLUSION_TERMS) or any(
        phrase_count(lowered, phrase) for phrase in EXCLUSION_PHRASES
    )
    negated = has_any_pattern(lowered, NEGATION_PATTERNS)
    counterspeech = has_any_pattern(lowered, COUNTERSPEECH_PATTERNS)
    quoted_or_reported = has_any_pattern(value, QUOTE_REPORT_PATTERNS)
    public_interest = (
        has_any_term(lowered, PUBLIC_INTEREST_TERMS)
        and has_any_term(lowered, PUBLIC_CRITICISM_TERMS)
        and not target_present
    )
    offensive_only = (
        has_any_term(lowered, OFFENSIVE_ONLY_TERMS)
        and not target_present
        and not threat
        and not exclusion
        and not dehumanization
    )

    if target_present:
        tags.add("protected_target")
        reasons.add("target_marker_present")
    if historical_victim_group:
        tags.add("historical_victim_group")
        reasons.add("historical_victim_marker_present")
    if hostile_action:
        tags.add("hostile_action")
        reasons.add("action_marker_present")
    if threat:
        tags.add("threat")
        reasons.add("threat_marker_present")
    if dehumanization:
        tags.add("dehumanization")
        reasons.add("dehumanization_marker_present")
    if exclusion:
        tags.add("exclusion")
        reasons.add("exclusion_marker_present")
    if negated:
        tags.add("negated_hate")
        reasons.add("negation_marker_present")
    if counterspeech:
        tags.add("counterspeech")
        reasons.add("counterspeech_marker_present")
    if quoted_or_reported:
        tags.add("quoted_or_reported")
        reasons.add("quote_or_reporting_marker_present")
    if public_interest:
        tags.add("public_interest_or_institutional_criticism")
        reasons.add("public_interest_criticism_marker_present")
    if offensive_only:
        tags.add("offensive_only_risk")
        reasons.add("offensive_without_protected_target")
    if (
        (target_present or hostile_action or offensive_only)
        and not counterspeech
        and not quoted_or_reported
        and not public_interest
    ):
        tags.add("missing_context")
        reasons.add("speaker_audience_context_missing")

    ordered_tags = [tag for tag in CONTEXT_TAGS if tag in tags]
    return {
        "context_tags": ordered_tags,
        "reason_codes": sorted(reasons),
        "counts": {
            "target_spans": len(target_spans) if target_spans else int(target_present),
            "action_markers": int(hostile_action),
            "threat_markers": int(threat),
            "dehumanization_markers": int(dehumanization),
            "exclusion_markers": int(exclusion),
            "negation_markers": int(negated),
        },
    }
