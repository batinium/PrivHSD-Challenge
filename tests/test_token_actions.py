import builtins
import csv
import importlib.util

import pytest

from contextsafe_hsd.cli import build_parser
from contextsafe_hsd.token_actions import (
    ACTION_GENERALIZE,
    ACTION_MASK,
    ACTION_NORMALIZE,
    ACTION_PROTECT_HSD,
    ACTION_PROTECT_TARGET,
    TokenActionError,
    load_sklearn,
    train_token_action_tagger,
    weak_label_text,
)


HAS_SKLEARN = importlib.util.find_spec("sklearn") is not None


def write_rows(path):
    rows = [
        ("1", "Email alex@example.test because immigrants should leave!!!! #tag"),
        ("2", "I am from Boston and my name is Alex Stone."),
        ("3", "No identifiers here lol lol."),
        ("4", "Women should not be attacked."),
        ("5", "Call me River aka riv3r."),
        ("6", "The school meeting is today."),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text"])
        writer.writerows(rows)


def test_train_token_action_tagger_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "train-token-action-tagger",
            "--input",
            "input.csv",
            "--text-col",
            "text",
        ]
    )

    assert args.command == "train-token-action-tagger"
    assert str(args.model).endswith("privhsd_token_action_tagger.pkl")


def test_weak_label_text_marks_mask_protect_and_style_actions():
    labels = {
        example.token.lower(): example.action
        for example in weak_label_text(
            "Email alex@example.test because immigrants should leave!!!! #tag"
        )
    }

    assert labels["alex@example.test"] == ACTION_MASK
    assert labels["immigrants"] == ACTION_PROTECT_TARGET
    assert labels["should"] == ACTION_PROTECT_HSD
    assert labels["#tag"] == ACTION_NORMALIZE


def test_weak_label_text_marks_context_generalization():
    labels = {
        example.token.lower(): example.action
        for example in weak_label_text("I am from Boston.")
    }

    assert labels["boston"] == ACTION_GENERALIZE


def test_token_action_dependency_hint_mentions_optional_extra(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("sklearn"):
            raise ModuleNotFoundError("No module named 'sklearn'", name="sklearn")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(TokenActionError, match=r"\.\[token-actions\]"):
        load_sklearn()


@pytest.mark.skipif(not HAS_SKLEARN, reason="requires optional token-actions extra")
def test_train_token_action_tagger_writes_report_and_model(tmp_path):
    source = tmp_path / "tokens.csv"
    model = tmp_path / "tagger.pkl"
    report = tmp_path / "tagger.json"
    write_rows(source)

    result = train_token_action_tagger(
        source,
        text_col="text",
        id_col="id",
        model_path=model,
        output_path=report,
        sample_size=0,
        test_size=0.35,
        random_state=3,
    )

    assert model.exists()
    assert report.exists()
    assert result["training_type"] == "weak_token_action_tagger"
    assert result["model"]["saved"] is True
    assert result["split"]["token_count"] > 0
    assert set(result["split"]["label_counts"]) >= {
        ACTION_MASK,
        ACTION_PROTECT_TARGET,
        ACTION_PROTECT_HSD,
    }
    assert "macro_f1" in result["metrics"]
