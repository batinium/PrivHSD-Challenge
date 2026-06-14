import builtins
import csv
import json

import pytest

from contextsafe_hsd.cli import build_parser
from contextsafe_hsd.hf_utility import (
    APPROVED_MODELS,
    HfUtilityError,
    load_hf_stack,
    run_hf_utility_evaluation,
    write_model_registry,
)


def write_hf_rows(path):
    rows = [
        (
            "1",
            "drop original hate threat",
            "drop privatized neutral",
            "hate",
        ),
        (
            "2",
            "stable original hate",
            "stable privatized hate",
            "hate",
        ),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "privatized_text", "label"])
        writer.writerows(rows)


class FakeConfig:
    _commit_hash = "fake-revision"


class FakeModel:
    config = FakeConfig()


class FakeClassifier:
    model = FakeModel()

    def __call__(self, texts, batch_size=8, truncation=True):
        _ = truncation
        outputs = []
        for text in texts:
            if "drop original" in text:
                hate_score = 0.95
            elif "drop privatized" in text:
                hate_score = 0.35
            elif "hate" in text:
                hate_score = 0.9
            else:
                hate_score = 0.1
            outputs.append(
                [
                    {"label": "not_hate", "score": 1.0 - hate_score},
                    {"label": "hate", "score": hate_score},
                ]
            )
        return outputs


def fake_pipeline(*_args, **_kwargs):
    return FakeClassifier()


def failing_pipeline(*_args, **_kwargs):
    raise RuntimeError("model unavailable")


def test_hf_utility_commands_are_registered():
    parser = build_parser()

    registry_args = parser.parse_args(["hf-model-registry"])
    eval_args = parser.parse_args(
        [
            "evaluate-hf-utility",
            "--input",
            "input.csv",
            "--text-col",
            "text",
            "--model",
            "facebook/roberta-hate-speech-dynabench-r4-target",
        ]
    )

    assert registry_args.command == "hf-model-registry"
    assert eval_args.command == "evaluate-hf-utility"
    assert eval_args.models == ["facebook/roberta-hate-speech-dynabench-r4-target"]


def test_hf_model_registry_writes_manifest(tmp_path):
    output = tmp_path / "registry.json"

    result = write_model_registry(output)
    written = json.loads(output.read_text(encoding="utf-8"))

    assert result == written
    assert result["registry_type"] == "hf_utility_models"
    assert len(result["models"]) == len(APPROVED_MODELS)
    assert all(model["approved_use"] for model in result["models"])


def test_hf_utility_dependency_hint_mentions_optional_extra(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("transformers"):
            raise ModuleNotFoundError(
                "No module named 'transformers'",
                name="transformers",
            )
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(HfUtilityError, match=r"\.\[hf-utility\]"):
        load_hf_stack()


def test_hf_utility_skips_cleanly_without_transformers(monkeypatch, tmp_path):
    source = tmp_path / "hf.csv"
    output = tmp_path / "hf.json"
    write_hf_rows(source)

    def fake_load():
        raise HfUtilityError("Install optional Hugging Face evaluator dependencies")

    monkeypatch.setattr("contextsafe_hsd.hf_utility.load_hf_stack", fake_load)

    result = run_hf_utility_evaluation(
        source,
        text_col="text",
        privatized_col="privatized_text",
        id_col="id",
        label_col="label",
        output_path=output,
        model_ids=["facebook/roberta-hate-speech-dynabench-r4-target"],
        sample_size=2,
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result == written
    assert result["status"] == "skipped"
    assert result["skip_reason"] == "missing_optional_dependency"
    assert result["models"][0]["status"] == "skipped"


def test_hf_utility_reports_score_drift_with_fake_pipeline(monkeypatch, tmp_path):
    source = tmp_path / "hf.csv"
    write_hf_rows(source)
    monkeypatch.setattr(
        "contextsafe_hsd.hf_utility.load_hf_stack",
        lambda: {"pipeline": fake_pipeline},
    )

    result = run_hf_utility_evaluation(
        source,
        text_col="text",
        privatized_col="privatized_text",
        id_col="id",
        label_col="label",
        model_ids=["facebook/roberta-hate-speech-dynabench-r4-target"],
        sample_size=2,
        drop_threshold=0.25,
    )

    model_result = result["models"][0]
    assert result["status"] == "ok"
    assert model_result["status"] == "ok"
    assert model_result["revision"] == "fake-revision"
    assert model_result["sample_size"] == 2
    assert model_result["agreement"] == 0.5
    assert model_result["score_drift"]["mean_delta"] < 0
    assert model_result["label_alignment"]["original"]["accuracy"] == 1.0
    assert model_result["label_alignment"]["privatized"]["accuracy"] == 0.5
    assert model_result["label_alignment"]["utility_label_drop_rows"][0]["row_id"] == "1"
    assert model_result["large_utility_drop_rows"][0]["row_id"] == "1"
    assert "original_text" not in model_result["large_utility_drop_rows"][0]


def test_hf_utility_model_load_failure_is_per_model_skip(monkeypatch, tmp_path):
    source = tmp_path / "hf.csv"
    write_hf_rows(source)
    monkeypatch.setattr(
        "contextsafe_hsd.hf_utility.load_hf_stack",
        lambda: {"pipeline": failing_pipeline},
    )

    result = run_hf_utility_evaluation(
        source,
        text_col="text",
        privatized_col="privatized_text",
        id_col="id",
        model_ids=["facebook/roberta-hate-speech-dynabench-r4-target"],
        sample_size=1,
    )

    assert result["status"] == "ok"
    assert result["models"][0]["status"] == "skipped"
    assert result["models"][0]["skip_reason"] == "model_load_failed"


def test_hf_utility_skips_custom_loader_models_before_pipeline(monkeypatch, tmp_path):
    source = tmp_path / "hf.csv"
    write_hf_rows(source)

    def fail_if_called():
        raise AssertionError("generic HF stack should not load")

    monkeypatch.setattr("contextsafe_hsd.hf_utility.load_hf_stack", fail_if_called)

    result = run_hf_utility_evaluation(
        source,
        text_col="text",
        privatized_col="privatized_text",
        id_col="id",
        model_ids=["Hate-speech-CNERG/bert-base-uncased-hatexplain-rationale-two"],
        sample_size=1,
    )

    assert result["status"] == "ok"
    assert result["models"][0]["status"] == "skipped"
    assert result["models"][0]["skip_reason"] == "custom_loader_required"
