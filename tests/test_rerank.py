import csv
from dataclasses import dataclass
import json

from contextsafe_hsd.cli import build_parser
from contextsafe_hsd.rerank import generate_candidates, run_candidate_reranking


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rerank_rows(path):
    rows = [
        {
            "id": "1",
            "text": (
                "REFUGEES dooo NOOOT belong here!!!! frfr #MyCatchphrase "
                "\U0001f602\U0001f602"
            ),
            "label": "hate",
            "manual_candidate": "refugees do not belong here",
        },
        {
            "id": "2",
            "text": "Email alex@example.test about immigrants should leave.",
            "label": "hate",
            "manual_candidate": "",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "text", "label", "manual_candidate"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return rows


@dataclass(frozen=True)
class FakePresidioResult:
    start: int
    end: int
    entity_type: str
    score: float = 0.85


class FakePresidioAnalyzer:
    def analyze(self, *, text, language):
        if "Amy" not in text:
            return []
        start = text.index("Amy")
        return [FakePresidioResult(start, start + len("Amy"), "PERSON")]


def test_rerank_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "rerank-candidates",
            "--input",
            "input.csv",
            "--output",
            "output.csv",
            "--text-col",
            "text",
            "--presidio-augment",
            "--candidate-col",
            "manual_candidate",
        ]
    )

    assert args.command == "rerank-candidates"
    assert args.output_col == "privatized_text"
    assert args.candidate_cols == ["manual_candidate"]
    assert args.presidio_augment is True


def test_generate_candidates_includes_deterministic_and_rewrite_options():
    candidates = generate_candidates(
        "Immigrants should leave!!!!",
        rewrite_candidates={"manual_candidate": "immigrants should leave"},
    )

    assert [candidate.name for candidate in candidates] == [
        "balanced",
        "style_scrubbed",
        "privacy",
        "target_generalized",
        "rewrite:manual_candidate",
    ]


def test_generate_candidates_rejects_external_rewrite_with_cue_loss():
    candidates = generate_candidates(
        "Muslims should leave.",
        rewrite_candidates={"manual_candidate": "People are annoying."},
    )

    assert [candidate.name for candidate in candidates] == [
        "balanced",
        "style_scrubbed",
        "privacy",
        "target_generalized",
    ]


def test_generate_candidates_can_include_filtered_presidio_candidate():
    candidates = generate_candidates(
        "i'm going to kill Amy",
        presidio_analyzer=FakePresidioAnalyzer(),
    )

    presidio = [candidate for candidate in candidates if candidate.name == "presidio_augmented"]
    assert len(presidio) == 1
    assert presidio[0].text == "i'm going to kill [PERSON]"
    assert presidio[0].metadata["accepted_span_count"] == 1


def test_candidate_reranking_preserves_rows_and_writes_audit(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    audit = tmp_path / "audit.json"
    original_rows = write_rerank_rows(source)

    summary = run_candidate_reranking(
        source,
        output,
        text_col="text",
        id_col="id",
        candidate_cols=["manual_candidate"],
        audit_path=audit,
    )

    rows = read_rows(output)
    audit_data = json.loads(audit.read_text(encoding="utf-8"))
    assert summary["row_count"] == 2
    assert [row["id"] for row in rows] == [row["id"] for row in original_rows]
    assert [row["label"] for row in rows] == [row["label"] for row in original_rows]
    assert rows[0]["privatized_text"].startswith("refugees do not belong here!")
    assert rows[0]["privatized_text"].endswith("[STYLE] [TAG] [EMOJI]")
    assert "[EMAIL]" in rows[1]["privatized_text"]
    assert audit_data["rows"][0]["chosen"] == "style_scrubbed"
    assert any(
        score["name"] == "rewrite:manual_candidate"
        for score in audit_data["rows"][0]["scores"]
    )
    assert audit_data["summary"]["rewrite_candidate_validation"]["rejected_count"] == 0
    assert "text" not in audit_data["rows"][0]
    assert summary["metrics"]["target_cue_retention_mean"] == 1.0


def test_candidate_reranking_audits_rejected_rewrite_candidates(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    audit = tmp_path / "audit.json"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "text", "label", "manual_candidate"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "text": "Muslims should leave.",
                "label": "hate",
                "manual_candidate": "People are annoying.",
            }
        )

    summary = run_candidate_reranking(
        source,
        output,
        text_col="text",
        id_col="id",
        candidate_cols=["manual_candidate"],
        audit_path=audit,
    )

    audit_data = json.loads(audit.read_text(encoding="utf-8"))
    row_audit = audit_data["rows"][0]
    rejected = row_audit["rejected_rewrite_candidates"][0]
    reasons = rejected["validation"]["reasons"]
    assert row_audit["candidate_count"] == 4
    assert not any(
        score["name"] == "rewrite:manual_candidate"
        for score in row_audit["scores"]
    )
    assert rejected["column"] == "manual_candidate"
    assert "target_cue_loss" in reasons
    assert "utility_cue_loss" in reasons
    assert summary["rewrite_candidate_validation"]["rejected_count"] == 1
    assert summary["rewrite_candidate_validation"]["rejected_counts_by_reason"][
        "target_cue_loss"
    ] == 1


def test_candidate_reranking_can_replace_text_in_place(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    original_rows = write_rerank_rows(source)

    run_candidate_reranking(
        source,
        output,
        text_col="text",
        id_col="id",
        replace_text=True,
    )

    rows = read_rows(output)
    assert "privatized_text" not in rows[0]
    assert rows[0]["text"] != original_rows[0]["text"]
    assert [row["id"] for row in rows] == [row["id"] for row in original_rows]


def test_candidate_reranking_can_choose_presidio_augmented_candidate(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    audit = tmp_path / "audit.json"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "text", "label"])
        writer.writeheader()
        writer.writerow({"id": "1", "text": "i'm going to kill Amy", "label": "nothate"})
    monkeypatch.setattr(
        "contextsafe_hsd.rerank.load_presidio_analyzer",
        lambda: FakePresidioAnalyzer(),
    )

    summary = run_candidate_reranking(
        source,
        output,
        text_col="text",
        id_col="id",
        audit_path=audit,
        presidio_augment=True,
    )

    rows = read_rows(output)
    audit_data = json.loads(audit.read_text(encoding="utf-8"))
    assert rows[0]["privatized_text"] == "i'm going to kill [PERSON]"
    assert audit_data["rows"][0]["chosen"] == "presidio_augmented"
    assert summary["chosen_counts"] == {"presidio_augmented": 1}
