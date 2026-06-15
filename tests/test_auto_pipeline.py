import csv
from dataclasses import dataclass

from contextsafe_hsd.auto import AutoPipelineConfig, AutoPipelineContext, AutoPipelineEngine
from contextsafe_hsd.auto.engine import (
    AutoCandidate,
    choose_auto_candidate,
    cleanup_direct_residuals,
    cleanup_strict_residuals,
)
from contextsafe_hsd.detectors import Span
from contextsafe_hsd.simple_pipeline import build_final_pipeline_rows
from contextsafe_hsd.span_providers.base import (
    PRIVACY_CLASS_DIRECT,
    UTILITY_CLASS_NONE,
    SpanCandidate,
    SpanProviderOutput,
)


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_default_auto_config_uses_cpu_and_no_sidecar_model():
    config = AutoPipelineConfig()
    context = AutoPipelineContext.create(config)

    assert config.hsd_classification_backend == "none"
    assert config.local_llm_enabled is False
    assert config.device == "cpu"
    assert set(context.provider_status) == {"deterministic", "presidio", "scrubadub"}
    assert set(context.model_status) == {"local_llm"}
    assert context.model_status["local_llm"]["status"] == "disabled"


def test_local_llm_backend_enables_lazy_local_model_status():
    context = AutoPipelineContext.create(
        AutoPipelineConfig(
            hsd_classification_backend="local-llm",
            official_mode=False,
        )
    )

    assert context.config.hsd_classification_backend == "local_llm"
    assert context.model_status["local_llm"]["status"] == "available"
    assert context.model_load_counts["local_llm"] == 0


def test_build_final_pipeline_rows_preserves_schema_and_stage_names():
    rows = [
        {
            "source": "unit",
            "author_id": "a1",
            "text": "@mara emailed mara@example.test that Muslims should leave.",
            "is_hate_speech": "1",
        },
        {
            "source": "unit",
            "author_id": "a2",
            "text": "Everyone deserves respect.",
            "is_hate_speech": "0",
        },
    ]
    fieldnames = ["source", "author_id", "text", "is_hate_speech"]

    result = build_final_pipeline_rows(
        rows,
        fieldnames,
        text_col="text",
        disabled_providers=["presidio", "scrubadub"],
        llm_review="off",
    )

    output_rows = result["rows"]
    assert result["fieldnames"] == fieldnames
    assert output_rows[0]["source"] == "unit"
    assert output_rows[0]["is_hate_speech"] == "1"
    assert "[USER]" in output_rows[0]["text"]
    assert "[EMAIL]" in output_rows[0]["text"]
    assert "Muslims should leave" in output_rows[0]["text"]
    assert set(result["stages"]) == {
        "privacy_detection",
        "meaning_protection",
        "verification",
    }
    privacy = result["stages"]["privacy_detection"]
    assert privacy["pii_assist"]["components"] == {
        "presidio": "disabled",
        "scrubadub": "disabled",
    }
    assert "hsd_advisory" not in result["stages"]["verification"]


def test_auto_mode_can_mask_repeated_author_group_residuals(monkeypatch):
    rows = [
        {
            "ID": "r1",
            "author": "7",
            "text": "sharedtrail should stay private and Muslims should leave.",
            "hs": "1",
        },
        {
            "ID": "r2",
            "author": "7",
            "text": "sharedtrail shows up again without changing target cues.",
            "hs": "0",
        },
        {
            "ID": "r3",
            "author": "8",
            "text": "sharedtrail is not repeated for this author.",
            "hs": "0",
        },
    ]

    def fake_candidate_spans(text):
        start = text.find("sharedtrail")
        if start < 0:
            return []
        return [
            Span(
                start=start,
                end=start + len("sharedtrail"),
                entity_type="LOCATION",
                text="sharedtrail",
                score=0.91,
                source="unit_author_group",
            )
        ]

    monkeypatch.setattr(
        "contextsafe_hsd.author_group_masking.candidate_spans",
        fake_candidate_spans,
    )

    result = build_final_pipeline_rows(
        rows,
        ["ID", "author", "text", "hs"],
        text_col="text",
        id_col="ID",
        disabled_providers=["presidio", "scrubadub"],
        llm_review="off",
        author_group_masking=True,
        author_group_col="author",
    )

    output_rows = result["rows"]
    assert output_rows[0]["text"].startswith("[LOCATION] should stay private")
    assert output_rows[1]["text"].startswith("[LOCATION] shows up again")
    assert output_rows[2]["text"] == rows[2]["text"]
    assert "Muslims should leave" in output_rows[0]["text"]
    group_summary = result["stages"]["verification"]["author_group_masking"]
    assert group_summary["status"] == "ok"
    assert group_summary["author_col"] == "author"
    assert group_summary["changed_rows"] == 2
    assert group_summary["counts_by_entity_type"] == {"LOCATION": 2}


def test_auto_mode_degrades_to_deterministic_when_optional_dependencies_missing(
    monkeypatch,
):
    monkeypatch.setattr("contextsafe_hsd.auto.context.has_module", lambda _name: False)
    rows = [
        {
            "id": "1",
            "text": "@mara emailed mara@example.test that Muslims should leave.",
        }
    ]

    result = build_final_pipeline_rows(
        rows,
        ["id", "text"],
        text_col="text",
        id_col="id",
        llm_review="off",
    )

    assert result["providers"]["presidio"]["status"] == "missing_dependency"
    assert result["providers"]["scrubadub"]["status"] == "missing_dependency"
    assert "[EMAIL]" in result["rows"][0]["text"]


@dataclass
class CountingProvider:
    propose_calls: list[str]
    name: str = "fake_provider"

    def propose(self, text):
        self.propose_calls.append(text)
        if "Amy" not in text:
            return SpanProviderOutput(provider=self.name, spans=(), audit={})
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
                    utility_class=UTILITY_CLASS_NONE,
                    provider=self.name,
                    score=0.95,
                    explanation_code="unit_person",
                    metadata={"source": "fake_provider:person"},
                ),
            ),
            audit={"accepted_span_count": 1},
        )


class BatchedCountingProvider:
    name = "batched_provider"

    def __init__(self, batch_calls):
        self.batch_calls = batch_calls

    def propose_many(self, texts, *, batch_size):
        self.batch_calls.append({"count": len(texts), "batch_size": batch_size})
        outputs = []
        for text in texts:
            if "Amy" not in text:
                outputs.append(
                    SpanProviderOutput(provider=self.name, spans=(), audit={})
                )
                continue
            start = text.index("Amy")
            outputs.append(
                SpanProviderOutput(
                    provider=self.name,
                    spans=(
                        SpanCandidate(
                            start=start,
                            end=start + len("Amy"),
                            text="Amy",
                            entity_type="PERSON",
                            privacy_class=PRIVACY_CLASS_DIRECT,
                            utility_class=UTILITY_CLASS_NONE,
                            provider=self.name,
                            score=0.95,
                            explanation_code="unit_person",
                            metadata={"source": "batched_provider:person"},
                        ),
                    ),
                    audit={"accepted_span_count": 1},
                )
            )
        return outputs


def test_auto_engine_uses_provider_batch_api_once_per_provider():
    batch_calls = []
    context = AutoPipelineContext.create(
        AutoPipelineConfig(
            max_model_batch_size=7,
            disabled_providers=frozenset({"presidio", "scrubadub"}),
            audit_level="row",
        ),
        provider_factories={
            "batched_provider": lambda _context: BatchedCountingProvider(batch_calls)
        },
    )
    rows = [
        {"id": "1", "text": "kill Amy"},
        {"id": "2", "text": "threaten Amy"},
        {"id": "3", "text": "No identifiers here"},
    ]

    result = AutoPipelineEngine(context).process_rows(
        rows,
        ["id", "text"],
        text_col="text",
        id_col="id",
        output_col="text",
        replace_text=True,
    )

    assert batch_calls == [{"count": 2, "batch_size": 7}]
    assert result.summary["providers"]["items"]["batched_provider"]["status"] == "ready"
    assert context.provider_load_counts["batched_provider"] == 1
    assert result.audit_rows[0]["accepted_provider_spans_by_provider"] == {
        "batched_provider": 1
    }
    assert result.audit_rows[1]["accepted_provider_spans_by_provider"] == {
        "batched_provider": 1
    }
    assert result.summary["stages"]["privacy_detection"]["candidate_counts_by_name"][
        "provider_fusion_augmented"
    ] == 2
    assert result.rows[2]["text"] == "No identifiers here"


def test_auto_candidate_rejects_target_and_utility_cue_loss():
    original = "Muslims should leave now."
    baseline = AutoCandidate("balanced", original, "deterministic")
    rewrite = AutoCandidate("rewrite", "People are mentioned.", "unit")

    chosen, scored, reason = choose_auto_candidate(
        original,
        [baseline, rewrite],
        baseline_metrics={
            "direct_identifier_count_after": 0,
            "quasi_identifier_count_after": 0,
        },
    )

    assert chosen.name == "balanced"
    assert reason == "selected_least_destructive_candidate"
    assert "target_cue_loss" in scored[1]["hard_reject_reasons"]
    assert "utility_cue_loss" in scored[1]["hard_reject_reasons"]


def test_strict_and_direct_residual_cleanup_are_conservative():
    text = "Call me Alex Vale at mara@example.test; Muslims should leave."

    strict_text, strict_transformations = cleanup_strict_residuals(text)
    direct_text, direct_transformations = cleanup_direct_residuals(text)

    assert "[EMAIL]" in strict_text
    assert "[EMAIL]" in direct_text
    assert "Muslims should leave" in strict_text
    assert "Muslims should leave" in direct_text
    assert all(item["entity_type"] == "EMAIL" for item in direct_transformations)
    assert len(strict_transformations) >= len(direct_transformations)
