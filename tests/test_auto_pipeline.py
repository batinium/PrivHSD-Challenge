import csv
from dataclasses import dataclass
from pathlib import Path

from contextsafe_hsd.auto import AutoPipelineConfig, AutoPipelineContext, AutoPipelineEngine
from contextsafe_hsd.auto.engine import (
    AutoCandidate,
    choose_auto_candidate,
    cleanup_direct_residuals,
    cleanup_strict_residuals,
)
from contextsafe_hsd.span_providers.base import (
    PRIVACY_CLASS_DIRECT,
    UTILITY_CLASS_NONE,
    SpanCandidate,
    SpanProviderOutput,
)
from contextsafe_hsd.submission import create_submission


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_default_auto_config_uses_ml_hsd_backend():
    config = AutoPipelineConfig()

    assert config.hsd_classification_backend == "ml"
    assert config.local_llm_enabled is False
    assert config.device == "cpu"


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


def write_four_col(path):
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
            "text": "Muslims should leave.",
            "is_hate_speech": "1",
        },
        {
            "source": "unit",
            "author_id": "a3",
            "text": "No identifiers here, just rude words.",
            "is_hate_speech": "0",
        },
        {
            "source": "unit",
            "author_id": "a4",
            "text": "lol!!! #MyTag signed, alex",
            "is_hate_speech": "0",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source", "author_id", "text", "is_hate_speech"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return rows


def test_create_submission_auto_preserves_exact_four_column_shape(tmp_path):
    source = tmp_path / "four_col.csv"
    output = tmp_path / "four_col.out.csv"
    manifest_path = tmp_path / "four_col.manifest.json"
    original_rows = write_four_col(source)

    manifest = create_submission(
        source,
        output,
        text_cols=["text"],
        id_col=None,
        manifest_path=manifest_path,
        replace_text=True,
        mode="auto",
        disabled_providers=["presidio", "scrubadub", "gliner"],
        disabled_models=["token_policy_ensemble", "semantic", "hsd_advisory"],
    )

    rows = read_rows(output)
    assert list(rows[0]) == ["source", "author_id", "text", "is_hate_speech"]
    assert len(rows) == len(original_rows)
    assert [row["source"] for row in rows] == [row["source"] for row in original_rows]
    assert [row["author_id"] for row in rows] == [
        row["author_id"] for row in original_rows
    ]
    assert [row["is_hate_speech"] for row in rows] == [
        row["is_hate_speech"] for row in original_rows
    ]
    assert "[USER]" in rows[0]["text"]
    assert "[EMAIL]" in rows[0]["text"]
    assert "Muslims should leave" in rows[0]["text"]
    assert rows[1]["text"] == "Muslims should leave."
    assert manifest["mode"] == "auto"
    assert manifest["metric_depth"] == "fast"
    assert manifest["validation"]["valid"] is True
    assert manifest["metrics"]["metric_depth_counts"] == {"fast": 4}
    summary = manifest["text_column_summaries"]["text"]
    assert set(summary["stages"]) == {
        "privacy_detection",
        "meaning_protection",
        "verification",
    }
    privacy_detection = summary["stages"]["privacy_detection"]
    assert privacy_detection["baseline"] == "deterministic_balanced"
    assert privacy_detection["pii_assist"]["label"] == "PII Assist"
    assert privacy_detection["pii_assist"]["components"] == {
        "presidio": "disabled",
        "scrubadub": "disabled",
    }
    verification = summary["stages"]["verification"]
    assert verification["hsd_advisory_status"] == "skipped"
    assert verification["hsd_advisory"]["skipped_reason"] == "disabled"
    assert verification["author_risk"] == {
        "author_or_user_column_exists": True,
        "author_columns": ["author_id"],
        "author_metadata_rows": 4,
        "repeated_author_data_available": False,
        "author_risk_evaluation_ran": False,
        "skipped_reason": "not_run_manifest_hook_only",
    }


def test_auto_mode_degrades_to_deterministic_when_optional_dependencies_missing(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("contextsafe_hsd.auto.context.has_module", lambda _name: False)
    monkeypatch.setattr("contextsafe_hsd.auto.model_registry.module_available", lambda _name: False)
    source = tmp_path / "rows.csv"
    output = tmp_path / "out.csv"
    write_four_col(source)

    manifest = create_submission(
        source,
        output,
        text_cols=["text"],
        replace_text=True,
        mode="auto",
    )

    assert manifest["validation"]["valid"] is True
    assert manifest["providers"]["presidio"]["status"] == "missing_dependency"
    assert manifest["providers"]["scrubadub"]["status"] == "missing_dependency"
    assert manifest["providers"]["gliner"]["status"] == "disabled"
    assert manifest["models"]["token_policy_ensemble"]["status"] == "disabled"
    assert (
        manifest["stages"]["meaning_protection"].get(
            "rows_considered_for_token_policy_internal"
        )
        is None
    )
    assert "[EMAIL]" in read_rows(output)[0]["text"]


@dataclass
class CountingProvider:
    loads: list[str]
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


class MismatchedBatchedProvider:
    name = "mismatched_provider"

    def propose_many(self, texts, *, batch_size):
        return []


class CountingModel:
    def __init__(self, batch_calls):
        self.batch_calls = batch_calls

    def status_metadata(self):
        return {"device": "cpu", "member_count": 0}

    def propose_many(self, rows, *, text_col, batch_size):
        self.batch_calls.append(len(rows))
        return [
            SpanProviderOutput(
                provider="token_policy_ensemble",
                spans=(),
                audit={"accepted_span_count": 0},
            )
            for _row in rows
        ]


class CountingHsdAdvisory:
    def __init__(self, batch_calls):
        self.batch_calls = batch_calls

    def status_metadata(self):
        return {
            "model_id": "facebook/roberta-hate-speech-dynabench-r4-target",
            "device": "cpu",
        }

    def score_texts(self, texts, *, batch_size):
        self.batch_calls.append({"count": len(texts), "batch_size": batch_size})
        return [0.1 if "[STYLE]" in text or "[TAG]" in text else 0.9 for text in texts]

    def compare(self, original_score, candidate_score):
        drop = max(0.0, original_score - candidate_score)
        abs_drift = abs(candidate_score - original_score)
        original_positive = original_score >= 0.5
        candidate_positive = candidate_score >= 0.5
        return {
            "model_id": "facebook/roberta-hate-speech-dynabench-r4-target",
            "original_score": round(original_score, 4),
            "candidate_score": round(candidate_score, 4),
            "score_drop": round(drop, 4),
            "abs_drift": round(abs_drift, 4),
            "decision_changed": original_positive != candidate_positive,
            "large_drop": original_positive and drop >= 0.25,
            "large_abs_drift": abs_drift >= 0.35,
        }


def test_auto_context_loads_fake_provider_and_model_once_per_run():
    provider_loads = []
    provider_calls = []
    model_loads = []
    batch_calls = []

    def provider_factory(_context):
        provider_loads.append("load")
        return CountingProvider(provider_loads, provider_calls)

    def model_factory(_context):
        model_loads.append("load")
        return CountingModel(batch_calls)

    context = AutoPipelineContext.create(
        AutoPipelineConfig(
            enable_token_policy=True,
            disabled_providers=frozenset({"presidio", "scrubadub", "gliner"}),
            disabled_models=frozenset({"semantic", "hsd_advisory"}),
        ),
        provider_factories={"fake_provider": provider_factory},
        model_factories={"token_policy_ensemble": model_factory},
    )
    rows = [
        {"id": "1", "text": "kill Amy"},
        {"id": "2", "text": "reported Amy"},
        {"id": "3", "text": "emailed Amy"},
        {"id": "4", "text": "lol!!! #tag"},
        {"id": "5", "text": "lol??? #tag"},
    ]

    result = AutoPipelineEngine(context).process_rows(
        rows,
        ["id", "text"],
        text_col="text",
        id_col="id",
        replace_text=True,
    )

    assert provider_loads == ["load"]
    assert model_loads == ["load"]
    assert context.provider_load_counts["fake_provider"] == 1
    assert context.model_load_counts["token_policy_ensemble"] == 1
    assert len(provider_calls) == 3
    assert batch_calls == [2]
    assert sum("[PERSON]" in row["text"] for row in result.rows[:3]) >= 2


def test_auto_engine_uses_provider_batch_api_once_per_provider():
    batch_calls = []

    context = AutoPipelineContext.create(
        AutoPipelineConfig(
            max_model_batch_size=7,
            disabled_providers=frozenset({"presidio", "scrubadub", "gliner"}),
            disabled_models=frozenset(
                {"token_policy_ensemble", "semantic", "hsd_advisory"}
            ),
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
        replace_text=True,
    )

    assert batch_calls == [{"count": 2, "batch_size": 7}]
    assert context.provider_load_counts["batched_provider"] == 1
    assert result.audit_rows[0]["accepted_provider_spans_by_provider"] == {
        "batched_provider": 1
    }
    assert result.audit_rows[0]["chosen_candidate"]
    assert result.audit_rows[0]["why_chosen"]
    assert result.audit_rows[0]["privacy_gain"] is not None
    assert "meaning_protection_rejections" in result.audit_rows[0]
    assert "residual_review_required" in result.audit_rows[0]
    assert result.audit_rows[1]["accepted_provider_spans_by_provider"] == {
        "batched_provider": 1
    }
    assert result.rows[2]["text"] == "No identifiers here"


def test_auto_engine_rejects_mismatched_provider_batch_count():
    context = AutoPipelineContext.create(
        AutoPipelineConfig(
            disabled_providers=frozenset({"presidio", "scrubadub", "gliner"}),
            disabled_models=frozenset(
                {"token_policy_ensemble", "semantic", "hsd_advisory"}
            ),
            audit_level="row",
        ),
        provider_factories={
            "mismatched_provider": lambda _context: MismatchedBatchedProvider()
        },
    )

    result = AutoPipelineEngine(context).process_rows(
        [{"id": "1", "text": "kill Amy"}],
        ["id", "text"],
        text_col="text",
        id_col="id",
        replace_text=True,
    )

    assert result.rows[0]["text"] == "kill Amy"
    assert result.audit_rows[0]["provider_errors"] == [
        {
            "provider": "mismatched_provider",
            "error_class": "UnexpectedOutputCount",
        }
    ]
    assert (
        context.audit_counters[
            "provider_runtime_error:mismatched_provider:UnexpectedOutputCount"
        ]
        == 1
    )


def test_auto_candidate_rejects_large_hsd_advisory_drop():
    candidates = [
        AutoCandidate(name="balanced", text="Muslims should leave.", source="unit"),
        AutoCandidate(
            name="style_scrubbed",
            text="[STYLE]",
            source="unit",
            metadata={
                "hsd_advisory": {
                    "score_drop": 0.8,
                    "abs_drift": 0.8,
                    "decision_changed": True,
                    "large_drop": True,
                    "large_abs_drift": True,
                }
            },
        ),
    ]

    chosen, scored, reason = choose_auto_candidate(
        "Muslims should leave.",
        candidates,
        baseline_metrics={
            "direct_identifier_count_after": 0,
            "quasi_identifier_count_after": 0,
        },
    )

    assert chosen.name == "balanced"
    assert reason == "selected_least_destructive_candidate"
    assert "hsd_advisory_large_drop" in scored[1]["hard_reject_reasons"]
    assert "hsd_advisory_decision_drift" in scored[1]["hard_reject_reasons"]


def test_auto_direct_residual_cleanup_avoids_ambiguous_name_place_overmasking():
    cleaned, transformations = cleanup_direct_residuals(
        "Email alex@example.test call +1 202 555 0100 visit "
        "https://example.test/post @alex 192.0.2.44 case#ABC123 "
        "alex [at] example dot test near london library and Alex."
    )

    assert "alex@example.test" not in cleaned
    assert "+1 202 555 0100" not in cleaned
    assert "https://example.test/post" not in cleaned
    assert "@alex" not in cleaned
    assert "192.0.2.44" not in cleaned
    assert "case#ABC123" not in cleaned
    assert "alex [at] example dot test" not in cleaned
    assert "london library" in cleaned
    assert "Alex" in cleaned
    assert [item["entity_type"] for item in transformations] == [
        "EMAIL",
        "PHONE",
        "URL",
        "USER",
        "IP_ADDRESS",
        "IDENTIFIER",
        "EMAIL",
    ]


def test_auto_strict_residual_cleanup_adds_contextual_rung_without_blind_overmasking():
    cleaned, transformations = cleanup_strict_residuals(
        "Email alex@example.test near london library and Alex."
    )

    assert "alex@example.test" not in cleaned
    assert "[EMAIL]" in cleaned
    assert "london library" not in cleaned
    assert "[LOCATION]" in cleaned
    assert "Alex" in cleaned
    assert [item["entity_type"] for item in transformations] == [
        "EMAIL",
        "LOCATION",
    ]

    ambiguous, ambiguous_transformations = cleanup_strict_residuals(
        "london library and Alex were mentioned."
    )
    assert ambiguous == "london library and Alex were mentioned."
    assert ambiguous_transformations == []

    placeholder_adjacent, placeholder_transformations = cleanup_strict_residuals(
        "The [LOCATION] Library posted a statement."
    )
    assert placeholder_adjacent == "The [LOCATION] Library posted a statement."
    assert placeholder_transformations == []

    generic_place, generic_transformations = cleanup_strict_residuals(
        "[PERSON] put people in [LOCATION] in PRISON for years."
    )
    assert generic_place == "[PERSON] put people in [LOCATION] in PRISON for years."
    assert generic_transformations == []


def test_auto_privacy_ladder_selects_strict_pii_candidate_when_baseline_leaves_direct_residual():
    original = "Email alex@example.test and Muslims should leave."
    baseline = AutoCandidate(
        name="balanced",
        text=original,
        source="unit",
    )
    strict_text, transformations = cleanup_strict_residuals(baseline.text)
    strict = AutoCandidate(
        name="balanced_strict_pii",
        text=strict_text,
        source="unit+strict_residual_cleanup",
        metadata={
            "strict_residual_cleanup": {
                "cleanup_count": len(transformations),
                "counts_by_entity_type": {"EMAIL": len(transformations)},
            }
        },
    )

    chosen, scored, reason = choose_auto_candidate(
        original,
        [baseline, strict],
        baseline_metrics={
            "direct_identifier_count_after": 1,
            "quasi_identifier_count_after": 0,
        },
    )

    assert chosen.name == "balanced_strict_pii"
    assert reason == "selected_least_destructive_candidate"
    assert scored[1]["accepted"] is True
    assert scored[1]["metrics"]["residual_direct_identifier_count"] == 0
    assert scored[1]["metrics"]["target_cue_retention"] == 1.0
    assert scored[1]["metrics"]["strict_residual_cleanup"] == {
        "cleanup_count": 1,
        "counts_by_entity_type": {"EMAIL": 1},
    }


def test_auto_hard_privacy_cleanup_records_hsd_drift_without_rejecting_direct_pii():
    original = "Email alex@example.test and Muslims should leave."
    candidates = [
        AutoCandidate(
            name="balanced",
            text=original,
            source="unit",
        ),
        AutoCandidate(
            name="balanced_strict_pii",
            text="Email [EMAIL] and Muslims should leave.",
            source="unit+strict_residual_cleanup",
            metadata={
                "strict_residual_cleanup": {
                    "cleanup_count": 1,
                    "counts_by_entity_type": {"EMAIL": 1},
                },
                "hsd_advisory": {
                    "score_drop": 0.8,
                    "abs_drift": 0.8,
                    "decision_changed": True,
                    "large_drop": True,
                    "large_abs_drift": True,
                },
            },
        ),
    ]

    chosen, scored, _reason = choose_auto_candidate(
        original,
        candidates,
        baseline_metrics={
            "direct_identifier_count_after": 1,
            "quasi_identifier_count_after": 0,
        },
    )

    assert chosen.name == "balanced_strict_pii"
    assert scored[1]["accepted"] is True
    assert scored[1]["hard_reject_reasons"] == []
    assert scored[1]["metrics"]["hard_privacy_cleanup"] is True
    assert scored[1]["metrics"]["hsd_advisory"]["large_drop"] is True


def test_auto_hsd_advisory_scores_candidates_in_one_batch():
    loads = []
    hsd_batches = []

    def hsd_factory(_context):
        loads.append("load")
        return CountingHsdAdvisory(hsd_batches)

    context = AutoPipelineContext.create(
        AutoPipelineConfig(
            max_model_batch_size=8,
            disabled_providers=frozenset({"presidio", "scrubadub", "gliner"}),
            disabled_models=frozenset({"token_policy_ensemble", "semantic"}),
        ),
        model_factories={"hsd_advisory": hsd_factory},
    )
    rows = [
        {"id": "1", "text": "Muslims should leave lol!!! #watchlist"},
        {"id": "2", "text": "No one should attack black people lol!!! #watchlist"},
    ]

    result = AutoPipelineEngine(context).process_rows(
        rows,
        ["id", "text"],
        text_col="text",
        id_col="id",
        replace_text=False,
        output_col="privatized_text",
    )

    assert loads == ["load"]
    assert context.model_load_counts["hsd_advisory"] == 1
    assert hsd_batches == [{"count": 6, "batch_size": 8}]
    assert result.summary["models"]["items"]["hsd_advisory"]["status"] == "ready"
    verification = result.summary["stages"]["verification"]
    assert verification["hsd_advisory_status"] == "ok"
    assert verification["hsd_advisory"]["candidate_comparisons"] == 4
    assert verification["hsd_advisory"]["rejection_counts"] == {
        "hsd_advisory_decision_drift": 2,
        "hsd_advisory_large_drop": 2,
    }
    assert all(row["privatized_text"] == row["text"] for row in result.rows)
    for row in result.audit_rows:
        assert any(
            "hsd_advisory_large_drop" in score["hard_reject_reasons"]
            for score in row["scores"]
        )


def test_auto_hsd_advisory_scores_single_candidate_rows():
    hsd_batches = []

    context = AutoPipelineContext.create(
        AutoPipelineConfig(
            max_model_batch_size=8,
            disabled_providers=frozenset({"presidio", "scrubadub", "gliner"}),
            disabled_models=frozenset({"token_policy_ensemble", "semantic"}),
        ),
        model_factories={"hsd_advisory": lambda _context: CountingHsdAdvisory(hsd_batches)},
    )
    rows = [
        {"id": "1", "text": "Muslims should leave."},
    ]

    result = AutoPipelineEngine(context).process_rows(
        rows,
        ["id", "text"],
        text_col="text",
        id_col="id",
        replace_text=True,
    )

    assert hsd_batches == [{"count": 2, "batch_size": 8}]
    assert result.summary["stages"]["verification"]["hsd_advisory_status"] == "ok"
    assert result.summary["stages"]["verification"]["hsd_advisory"]["candidate_comparisons"] == 1
    hsd = result.audit_rows[0]["scores"][0]["metrics"]["hsd_advisory"]
    assert hsd["candidate_score"] == 0.9
    assert hsd["original_score"] == 0.9


def test_testing_dataset_fast_submission_path_is_practical(tmp_path):
    source = Path("data/external_unseen/tweet_eval_hate_offensive_test.csv")
    if not source.exists():
        return
    output = tmp_path / "tweet_eval_fast.csv"

    manifest = create_submission(
        source,
        output,
        text_cols=["text"],
        id_col="id",
        replace_text=True,
        mode="balanced",
        metric_depth="fast",
    )

    assert manifest["validation"]["valid"] is True
    assert manifest["metrics"]["row_count"] == 3830
    assert manifest["metrics"]["metric_depth_counts"] == {"fast": 3830}


def test_create_submission_auto_records_configured_gliner_model(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "contextsafe_hsd.auto.model_registry.module_available",
        lambda name: name == "gliner",
    )
    source = tmp_path / "four_col.csv"
    output = tmp_path / "four_col.out.csv"
    model_dir = tmp_path / "local-gliner"
    model_dir.mkdir()
    write_four_col(source)

    manifest = create_submission(
        source,
        output,
        text_cols=["text"],
        replace_text=True,
        mode="auto",
        disabled_providers=["presidio", "scrubadub"],
        disabled_models=["token_policy_ensemble", "semantic", "hsd_advisory"],
        gliner_model=str(model_dir),
        gliner_profile="pii",
    )

    assert manifest["providers"]["gliner"]["status"] == "available"
    assert manifest["providers"]["gliner"]["model"] == str(model_dir)
    assert manifest["providers"]["gliner"]["profile"] == "pii"
    assert manifest["stages"]["privacy_detection"]["pii_assist"]["components"][
        "gliner"
    ] == "available"
    assert manifest["load_counts"]["providers"].get("gliner") is None
