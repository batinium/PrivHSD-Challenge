import csv
import json

import pytest

from contextsafe_hsd.evidence_postprocess import (
    EvidencePostprocessError,
    run_classifier_evidence_after_baseline,
)


def write_rows(path, rows, fieldnames=("ID", "author", "text", "hs")):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_importance(path):
    fieldnames = [
        "row_index",
        "row_id",
        "token_index",
        "token",
        "start",
        "end",
        "baseline_hate_score",
        "masked_hate_score",
        "delta_hate_score",
        "abs_delta_hate_score",
        "predicted_hate",
        "protect_hsd_token",
    ]
    rows = [
        {
            "row_index": "1",
            "row_id": "A",
            "token_index": "0",
            "token": "alpha",
            "start": "0",
            "end": "5",
            "baseline_hate_score": "0.95",
            "masked_hate_score": "0.94",
            "delta_hate_score": "0.01",
            "abs_delta_hate_score": "0.01",
            "predicted_hate": "1",
            "protect_hsd_token": "0",
        },
        {
            "row_index": "1",
            "row_id": "A",
            "token_index": "1",
            "token": "slur",
            "start": "6",
            "end": "10",
            "baseline_hate_score": "0.95",
            "masked_hate_score": "0.05",
            "delta_hate_score": "0.90",
            "abs_delta_hate_score": "0.90",
            "predicted_hate": "1",
            "protect_hsd_token": "1",
        },
        {
            "row_index": "1",
            "row_id": "A",
            "token_index": "2",
            "token": "beta",
            "start": "11",
            "end": "15",
            "baseline_hate_score": "0.95",
            "masked_hate_score": "0.93",
            "delta_hate_score": "0.02",
            "abs_delta_hate_score": "0.02",
            "predicted_hate": "1",
            "protect_hsd_token": "0",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class FakeClassifierRow:
    def __init__(self, *, hate, score):
        self.hate = hate
        self.score = score


class FakeClassifierResult:
    def __init__(self, rows):
        self.rows = tuple(rows)
        self.device = "cpu"


class FakeClassifier:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = 0

    def classify_texts(self, rows, *, batch_size):
        self.calls += 1
        if self.calls == 1:
            assert [row["text"] for row in rows] == [
                "baseline positive",
                "baseline negative",
            ]
            return FakeClassifierResult(
                [
                    FakeClassifierRow(hate=True, score=0.95),
                    FakeClassifierRow(hate=False, score=0.10),
                ]
            )
        assert [row["text"] for row in rows] == [
            "alpha slur beta.",
            "Context removed.",
        ]
        return FakeClassifierResult(
            [
                FakeClassifierRow(hate=True, score=0.93),
                FakeClassifierRow(hate=False, score=0.03),
            ]
        )


class FakeBaselineNegativeClassifier:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = 0

    def classify_texts(self, rows, *, batch_size):
        self.calls += 1
        if self.calls == 1:
            assert [row["text"] for row in rows] == [
                "baseline positive",
                "baseline negative",
            ]
            return FakeClassifierResult(
                [
                    FakeClassifierRow(hate=True, score=0.95),
                    FakeClassifierRow(hate=False, score=0.10),
                ]
            )
        assert [row["text"] for row in rows] == [
            "alpha slur beta.",
            "baseline negative",
        ]
        return FakeClassifierResult(
            [
                FakeClassifierRow(hate=True, score=0.93),
                FakeClassifierRow(hate=False, score=0.10),
            ]
        )


def test_classifier_evidence_after_baseline_writes_phrase_and_sidecars(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "source.csv"
    baseline = tmp_path / "baseline.csv"
    importance = tmp_path / "importance.csv"
    output = tmp_path / "evidence.csv"
    manifest = tmp_path / "manifest.json"
    validation = tmp_path / "validation.json"
    hf_summary = tmp_path / "hf_summary.json"
    trace = tmp_path / "trace.json"
    write_rows(
        source,
        [
            {"ID": "A", "author": "u1", "text": "alpha slur beta", "hs": "1"},
            {"ID": "B", "author": "u2", "text": "raw negative", "hs": "0"},
        ],
    )
    write_rows(
        baseline,
        [
            {"ID": "A", "author": "u1", "text": "baseline positive", "hs": "1"},
            {"ID": "B", "author": "u2", "text": "baseline negative", "hs": "0"},
        ],
    )
    write_importance(importance)
    monkeypatch.setattr(
        "contextsafe_hsd.evidence_postprocess.HfHsdClassifierRuntime",
        FakeClassifier,
    )

    result = run_classifier_evidence_after_baseline(
        source_path=source,
        baseline_path=baseline,
        importance_path=importance,
        output_path=output,
        id_col="ID",
        label_col="hs",
        manifest_path=manifest,
        validation_path=validation,
        hf_summary_path=hf_summary,
        trace_path=trace,
        max_anchors=1,
        context_radius=1,
    )

    output_rows = read_rows(output)
    assert output_rows[0]["text"] == "alpha slur beta."
    assert output_rows[1]["text"] == "Context removed."
    assert result["validation"]["valid"] is True
    assert result["positive_pred_rows"] == 1
    assert result["trace"]["selected_token_count_distribution"] == {"3": 1}
    assert manifest.exists()
    assert validation.exists()
    assert hf_summary.exists()
    assert trace.exists()
    assert json.loads(hf_summary.read_text(encoding="utf-8"))["final_vs_gold"][
        "accuracy"
    ] == 1.0


def test_classifier_evidence_after_baseline_can_preserve_negative_baseline_context(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "source.csv"
    baseline = tmp_path / "baseline.csv"
    importance = tmp_path / "importance.csv"
    output = tmp_path / "evidence.csv"
    write_rows(
        source,
        [
            {"ID": "A", "author": "u1", "text": "alpha slur beta", "hs": "1"},
            {"ID": "B", "author": "u2", "text": "raw negative", "hs": "0"},
        ],
    )
    write_rows(
        baseline,
        [
            {"ID": "A", "author": "u1", "text": "baseline positive", "hs": "1"},
            {"ID": "B", "author": "u2", "text": "baseline negative", "hs": "0"},
        ],
    )
    write_importance(importance)
    monkeypatch.setattr(
        "contextsafe_hsd.evidence_postprocess.HfHsdClassifierRuntime",
        FakeBaselineNegativeClassifier,
    )

    result = run_classifier_evidence_after_baseline(
        source_path=source,
        baseline_path=baseline,
        importance_path=importance,
        output_path=output,
        id_col="ID",
        label_col="hs",
        max_anchors=1,
        context_radius=1,
        negative_strategy="baseline",
    )

    output_rows = read_rows(output)
    assert output_rows[0]["text"] == "alpha slur beta."
    assert output_rows[1]["text"] == "baseline negative"
    assert result["changed_text_cells_vs_locked_baseline"] == 1
    assert result["negative_strategy"] == "baseline"
    assert result["trace"]["negative_strategy"] == "baseline"
    assert result["trace"]["word_count_distribution"] == {"2": 1, "3": 1}
    assert result["hf_summary"]["final_vs_gold"]["accuracy"] == 1.0


def test_classifier_evidence_after_baseline_refuses_to_overwrite_baseline(tmp_path):
    source = tmp_path / "source.csv"
    baseline = tmp_path / "baseline.csv"
    importance = tmp_path / "importance.csv"
    rows = [{"ID": "A", "author": "u1", "text": "raw positive", "hs": "1"}]
    write_rows(source, rows)
    write_rows(baseline, rows)
    write_importance(importance)

    with pytest.raises(EvidencePostprocessError, match="refusing to overwrite"):
        run_classifier_evidence_after_baseline(
            source_path=source,
            baseline_path=baseline,
            importance_path=importance,
            output_path=baseline,
            id_col="ID",
        )
