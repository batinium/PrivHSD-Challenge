import csv
import json

import pytest

from privhsd.cli import build_parser
from privhsd.dpmlm_candidates import (
    DpmlmCandidateError,
    is_protected_token,
    protected_tokens,
    run_dpmlm_candidates,
)


def write_rows(path):
    rows = [
        ("1", "Immigrants should leave #MyTag!!!!", "hate"),
        ("2", "Everyone deserves respect.", "nothate"),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "label"])
        writer.writerows(rows)


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class FakeDetokenizer:
    def detokenize(self, tokens):
        return (
            " ".join(tokens)
            .replace(" !", "!")
            .replace(" ?", "?")
            .replace(" .", ".")
        )


class FakeDpmlmModel:
    detokenizer = FakeDetokenizer()

    def __init__(self, predictions):
        self.predictions = predictions
        self.calls = []

    def privatize_batch(self, tokens, indices, epsilon, CONCAT=True, batch_size=16):
        self.calls.append(
            {
                "tokens": tokens,
                "indices": indices,
                "epsilon": epsilon,
                "CONCAT": CONCAT,
                "batch_size": batch_size,
            }
        )
        return {
            f"{tokens[index]}_{index}": self.predictions.get(tokens[index], tokens[index])
            for index in indices
        }


def fake_tokenize(text):
    return (
        text.replace("!!!!", " ! ! ! !")
        .replace(".", " .")
        .split()
    )


def test_generate_dpmlm_candidates_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "generate-dpmlm-candidates",
            "--input",
            "input.csv",
            "--output",
            "output.csv",
            "--text-col",
            "text",
            "--model",
            "distilroberta-base",
        ]
    )

    assert args.command == "generate-dpmlm-candidates"
    assert args.candidate_col == "dpmlm_candidate"
    assert args.model == "distilroberta-base"
    assert args.min_eligible_score == 5


def test_dpmlm_candidate_generation_freezes_hsd_cues(monkeypatch, tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "candidates.csv"
    report = tmp_path / "report.json"
    write_rows(source)
    model = FakeDpmlmModel({"#MyTag": "plainly"})
    monkeypatch.setattr("privhsd.dpmlm_candidates.load_dpmlm_model", lambda model_name: model)
    monkeypatch.setattr("privhsd.dpmlm_candidates.tokenize_text", fake_tokenize)

    result = run_dpmlm_candidates(
        source,
        output,
        text_col="text",
        id_col="id",
        report_path=report,
        sample_size=1,
        model_name="fake-roberta",
        epsilon=25.0,
        max_rewrite_tokens=4,
    )

    rows = read_rows(output)
    written = json.loads(report.read_text(encoding="utf-8"))
    rewritten_indices = model.calls[0]["indices"]
    rewritten_tokens = [model.calls[0]["tokens"][index] for index in rewritten_indices]
    assert result == written
    assert result["status"] == "ok"
    assert result["accepted_count"] == 1
    assert result["status_counts"] == {"accepted": 1}
    assert "Immigrants" not in rewritten_tokens
    assert "should" not in rewritten_tokens
    assert "leave" not in rewritten_tokens
    assert rows[0]["dpmlm_candidate"] == "Immigrants should leave plainly!!!!"
    assert rows[1]["dpmlm_candidate"] == ""
    assert result["rows"][0]["rewrite"]["changed_token_count"] == 1
    assert "text" not in result["rows"][0]


def test_dpmlm_candidate_generation_rejects_unchanged_predictions(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.csv"
    output = tmp_path / "candidates.csv"
    write_rows(source)
    model = FakeDpmlmModel({"#MyTag": "should"})
    monkeypatch.setattr("privhsd.dpmlm_candidates.load_dpmlm_model", lambda model_name: model)
    monkeypatch.setattr("privhsd.dpmlm_candidates.tokenize_text", fake_tokenize)

    result = run_dpmlm_candidates(
        source,
        output,
        text_col="text",
        id_col="id",
        sample_size=1,
    )

    rows = read_rows(output)
    assert result["status"] == "skipped"
    assert result["skip_reason"] == "no_accepted_candidates"
    assert result["status_counts"] == {"rejected_by_checks": 1}
    assert result["reject_reasons"] == {"no_token_change": 1, "unchanged": 1}
    assert rows[0]["dpmlm_candidate"] == ""


def test_dpmlm_candidate_generation_rejects_invalid_epsilon(tmp_path):
    source = tmp_path / "input.csv"
    write_rows(source)

    with pytest.raises(DpmlmCandidateError, match="epsilon"):
        run_dpmlm_candidates(
            source,
            tmp_path / "out.csv",
            text_col="text",
            epsilon=0.0,
        )


def test_dpmlm_protected_tokens_include_target_and_action_cues():
    protected = protected_tokens()

    assert is_protected_token("Immigrants", protected)
    assert is_protected_token("should", protected)
    assert is_protected_token("leave", protected)
    assert is_protected_token("[PERSON]", protected)
    assert is_protected_token("reeetaaaardss", protected)
    assert is_protected_token("freeeaaaks", protected)
    assert is_protected_token("sooo", protected)
    assert is_protected_token("looooudly", protected)
    assert not is_protected_token("#MyTag", protected)
