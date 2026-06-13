import csv
from dataclasses import dataclass
from pathlib import Path

from privhsd.auto import AutoPipelineConfig, AutoPipelineContext, AutoPipelineEngine
from privhsd.span_providers.base import (
    PRIVACY_CLASS_DIRECT,
    UTILITY_CLASS_NONE,
    SpanCandidate,
    SpanProviderOutput,
)
from privhsd.submission import create_submission


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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


def test_auto_mode_degrades_to_deterministic_when_optional_dependencies_missing(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("privhsd.auto.context.has_module", lambda _name: False)
    monkeypatch.setattr("privhsd.auto.model_registry.module_available", lambda _name: False)
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
    assert manifest["providers"]["gliner"]["status"] == "missing_dependency"
    assert manifest["models"]["token_policy_ensemble"]["status"] == "missing_dependency"
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
