from dataclasses import dataclass

from privhsd.pipeline import PrivatizerConfig, privatize_text
from privhsd.span_providers.base import (
    PRIVACY_CLASS_DIRECT,
    SpanCandidate,
    SpanProviderOutput,
)
from privhsd.span_providers.deterministic import DeterministicSpanProvider
from privhsd.span_providers.fusion import fuse_span_candidates
from privhsd.span_providers.gliner import GlinerSpanProvider
from privhsd.span_providers.presidio import PresidioSpanProvider


@dataclass(frozen=True)
class FakeResult:
    start: int
    end: int
    entity_type: str
    score: float = 0.86


class FakeAnalyzer:
    def __init__(self, results):
        self.results = results

    def analyze(self, *, text, language):
        return self.results


def fake_span(text, value, entity_type):
    start = text.index(value)
    return FakeResult(start, start + len(value), entity_type)


def test_deterministic_provider_emits_normalized_schema():
    text = "@mara emailed mara@example.test and Muslims should leave."

    output = DeterministicSpanProvider().propose(text)
    records = [candidate.audit_record() for candidate in output.spans]

    assert output.provider == "deterministic"
    assert output.audit["counts_by_entity_type"]["USER"] == 1
    assert any(record["entity_type"] == "EMAIL" for record in records)
    assert all("text" not in record for record in records)


def test_fusion_rejects_model_person_overlap_with_protected_target():
    text = "Muslims should leave."
    candidate = SpanCandidate(
        start=0,
        end=7,
        text="Muslims",
        entity_type="PERSON",
        privacy_class=PRIVACY_CLASS_DIRECT,
        utility_class="none",
        provider="gliner",
        score=0.99,
        explanation_code="person",
    )

    result = fuse_span_candidates(text, [candidate])

    assert result.spans == []
    assert result.audit["rejected_counts_by_reason"] == {"protected_cue_overlap": 1}


def test_presidio_provider_matches_compatibility_span_behavior():
    text = "i'm going to kill Amy but Muslims should leave Britain in 2020"
    provider = PresidioSpanProvider(
        analyzer=FakeAnalyzer(
            [
                fake_span(text, "Amy", "PERSON"),
                fake_span(text, "Muslims", "NRP"),
                fake_span(text, "Britain", "LOCATION"),
                fake_span(text, "2020", "DATE_TIME"),
            ]
        )
    )

    output = provider.propose(text)

    assert [(span.entity_type, span.text) for span in output.spans] == [
        ("PERSON", "Amy"),
        ("LOCATION", "Britain"),
        ("DATE", "2020"),
    ]
    assert output.audit["rejected_counts_by_reason"] == {"nrp_preserved": 1}


class FakeGlinerModel:
    name_or_path = "fake-gliner"

    def __init__(self, outputs):
        self.outputs = outputs
        self.batch_calls = []

    def batch_predict_entities(self, texts, labels, batch_size):
        self.batch_calls.append(
            {"texts": list(texts), "labels": list(labels), "batch_size": batch_size}
        )
        return self.outputs


def test_gliner_pii_profile_maps_normalized_labels_in_batch():
    text = "Contact @mara or mara@example.test."
    handle_start = text.index("@mara")
    email_start = text.index("mara@example.test")
    model = FakeGlinerModel(
        [
            [
                {
                    "start": handle_start,
                    "end": handle_start + len("@mara"),
                    "text": "@mara",
                    "label": "username",
                    "score": 0.92,
                },
                {
                    "start": email_start,
                    "end": email_start + len("mara@example.test"),
                    "text": "mara@example.test",
                    "label": "email_address",
                    "score": 0.91,
                },
                {
                    "start": 0,
                    "end": 7,
                    "text": "Contact",
                    "label": "favorite color",
                    "score": 0.99,
                },
            ]
        ]
    )
    provider = GlinerSpanProvider(model=model, profile="pii")

    outputs = provider.propose_many([text], batch_size=4)

    assert model.batch_calls[0]["batch_size"] == 4
    assert model.batch_calls[0]["labels"][0:3] == ["person", "full name", "username"]
    assert [(span.entity_type, span.text) for span in outputs[0].spans] == [
        ("USER", "@mara"),
        ("EMAIL", "mara@example.test"),
    ]
    assert outputs[0].audit["profile"] == "pii"
    assert outputs[0].audit["rejected_counts_by_reason"] == {"unsupported_label": 1}


def test_privatize_text_accepts_provider_candidates_and_audits_fusion():
    text = "i'm going to kill Amy"
    start = text.index("Amy")
    candidate = SpanCandidate(
        start=start,
        end=start + len("Amy"),
        text="Amy",
        entity_type="PERSON",
        privacy_class=PRIVACY_CLASS_DIRECT,
        utility_class="none",
        provider="unit",
        score=0.91,
        explanation_code="person",
        metadata={"source": "unit:person"},
    )

    result = privatize_text(
        text,
        PrivatizerConfig(mode="balanced"),
        provider_candidates=[candidate],
    )

    assert result.text == "i'm going to kill [PERSON]"
    assert result.transformations[0]["source"] == "unit:person"
    assert result.provider_audit["fusion"]["accepted_counts_by_provider"]["unit"] == 1


class StaticProvider:
    name = "unit"

    def propose(self, text):
        start = text.index("Amy")
        return SpanProviderOutput(
            provider=self.name,
            spans=(
                SpanCandidate(
                    start=start,
                    end=start + len("Amy"),
                    text="Amy",
                    entity_type="PERSON",
                    privacy_class=PRIVACY_CLASS_DIRECT,
                    utility_class="none",
                    provider=self.name,
                    score=0.91,
                    explanation_code="person",
                    metadata={"source": "unit:person"},
                ),
            ),
            audit={"enabled": True, "accepted_span_count": 1},
        )


def test_rerank_can_generate_provider_augmented_candidate():
    from privhsd.rerank import generate_candidates

    candidates = generate_candidates(
        "i'm going to kill Amy",
        span_providers=[StaticProvider()],
    )

    unit = [candidate for candidate in candidates if candidate.name == "unit_augmented"]
    assert len(unit) == 1
    assert unit[0].text == "i'm going to kill [PERSON]"
