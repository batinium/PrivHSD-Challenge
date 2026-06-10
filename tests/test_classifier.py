import builtins
import csv

import pytest

from privhsd.classifier import (
    ClassifierError,
    evaluate_classifier,
    load_sklearn,
    predict_classifier,
    train_classifier,
)
from privhsd.cli import build_parser


try:
    import sklearn  # noqa: F401
except ModuleNotFoundError:
    HAS_SKLEARN = False
else:
    HAS_SKLEARN = True


def write_classifier_rows(path):
    rows = [
        ("1", "Immigrants should leave now", "hate", "synthetic", "alpha"),
        ("2", "Refugees do not belong here", "hate", "synthetic", "beta"),
        ("3", "I hate those people", "hate", "synthetic", "gamma"),
        ("4", "They should be deported", "hate", "synthetic", "delta"),
        ("5", "Welcome to the neighborhood", "nothate", "synthetic", "epsilon"),
        ("6", "The weather is calm today", "nothate", "synthetic", "zeta"),
        ("7", "Please join the public meeting", "nothate", "synthetic", "eta"),
        ("8", "Everyone deserves respect", "nothate", "synthetic", "theta"),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "label", "source", "meta"])
        writer.writerows(rows)
    return rows


def read_csv_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_classifier_commands_are_registered_without_optional_dependency():
    parser = build_parser()

    args = parser.parse_args(
        [
            "predict-classifier",
            "--input",
            "input.csv",
            "--text-col",
            "text",
        ]
    )

    assert args.command == "predict-classifier"
    assert str(args.output).endswith("privhsd_classifier.predictions.csv")


def test_classifier_dependency_hint_mentions_optional_extra(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("sklearn"):
            raise ModuleNotFoundError("No module named 'sklearn'", name="sklearn")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ClassifierError, match=r"\.\[classifier\]"):
        load_sklearn()


@pytest.mark.skipif(not HAS_SKLEARN, reason="requires optional classifier extra")
def test_classifier_train_evaluate_predict_round_trip_preserves_rows(tmp_path):
    source = tmp_path / "classifier.csv"
    model_path = tmp_path / "model.pkl"
    train_report = tmp_path / "train.json"
    eval_report = tmp_path / "evaluate.json"
    predictions_path = tmp_path / "predictions.csv"
    original_rows = write_classifier_rows(source)

    train_result = train_classifier(
        source,
        text_col="text",
        label_col="label",
        id_col="id",
        model_path=model_path,
        output_path=train_report,
        test_size=0.25,
        random_state=7,
    )

    assert model_path.exists()
    assert train_report.exists()
    assert train_result["warning"].startswith("This is a lightweight")
    assert train_result["split"]["row_count"] == len(original_rows)
    assert train_result["split"]["label_counts"] == {"hate": 4, "nothate": 4}
    assert train_result["metrics"]["row_count"] == 2
    assert set(train_result["metrics"]["per_label"]) == {"hate", "nothate"}
    assert "confusion_counts" in train_result["metrics"]

    eval_result = evaluate_classifier(
        source,
        model_path=model_path,
        text_col="text",
        label_col="label",
        id_col="id",
        output_path=eval_report,
    )

    assert eval_report.exists()
    assert eval_result["metrics"]["row_count"] == len(original_rows)
    assert eval_result["metrics"]["label_counts"] == {"hate": 4, "nothate": 4}
    assert set(eval_result["metrics"]["prediction_counts"])

    predict_result = predict_classifier(
        source,
        model_path=model_path,
        text_col="text",
        id_col="id",
        label_col="label",
        output_path=predictions_path,
    )

    prediction_rows = read_csv_rows(predictions_path)
    assert predict_result["row_count"] == len(original_rows)
    assert predict_result["metrics"]["row_count"] == len(original_rows)
    assert [row["id"] for row in prediction_rows] == [
        row[0] for row in original_rows
    ]
    assert [row["label"] for row in prediction_rows] == [
        row[2] for row in original_rows
    ]
    assert [row["source"] for row in prediction_rows] == [
        row[3] for row in original_rows
    ]
    assert [row["meta"] for row in prediction_rows] == [
        row[4] for row in original_rows
    ]
    assert all(row["predicted_label"] for row in prediction_rows)
    assert all(row["predicted_confidence"] for row in prediction_rows)
