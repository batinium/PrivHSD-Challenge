from dataclasses import dataclass

from privhsd.pipeline import PrivatizerConfig, privatize_text
from privhsd.presidio_augment import filtered_presidio_spans


@dataclass(frozen=True)
class FakeResult:
    start: int
    end: int
    entity_type: str
    score: float = 0.85


class FakeAnalyzer:
    def __init__(self, results):
        self.results = results

    def analyze(self, *, text, language):
        return self.results


def span_for(text, value, entity_type):
    start = text.index(value)
    return FakeResult(start=start, end=start + len(value), entity_type=entity_type)


def test_filtered_presidio_spans_accepts_names_and_preserves_target_terms():
    text = "i'm going to kill Amy but Muslims should leave Britain in 2020"
    spans, report = filtered_presidio_spans(
        text,
        FakeAnalyzer(
            [
                span_for(text, "Amy", "PERSON"),
                span_for(text, "Muslims", "NRP"),
                span_for(text, "Britain", "LOCATION"),
                span_for(text, "2020", "DATE_TIME"),
            ]
        ),
    )

    assert [(span.entity_type, span.text) for span in spans] == [
        ("PERSON", "Amy"),
        ("LOCATION", "Britain"),
        ("DATE", "2020"),
    ]
    assert report["accepted_span_count"] == 3
    assert report["rejected_counts_by_reason"] == {"nrp_preserved": 1}


def test_filtered_presidio_spans_rejects_common_false_positives():
    text = "women in the army ngl should not sl33p today"
    spans, report = filtered_presidio_spans(
        text,
        FakeAnalyzer(
            [
                span_for(text, "ngl", "PERSON"),
                span_for(text, "sl33p", "LOCATION"),
                span_for(text, "today", "DATE_TIME"),
            ]
        ),
    )

    assert spans == []
    assert report["rejected_counts_by_reason"] == {
        "location_shape": 1,
        "person_shape": 1,
        "transient_date": 1,
    }


def test_privatize_text_accepts_filtered_presidio_extra_spans():
    text = "i'm going to kill Amy"
    spans, _report = filtered_presidio_spans(
        text,
        FakeAnalyzer([span_for(text, "Amy", "PERSON")]),
    )

    result = privatize_text(
        text,
        PrivatizerConfig(mode="balanced"),
        extra_spans=spans,
    )

    assert result.text == "i'm going to kill [PERSON]"
    assert result.transformations[0]["source"] == "presidio:PERSON"
