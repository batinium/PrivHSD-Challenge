import csv
import importlib.util
import json

import pytest

from contextsafe_hsd.author_risk import run_author_risk_evaluation
from contextsafe_hsd.cli import build_parser


HAS_SKLEARN = importlib.util.find_spec("sklearn") is not None


def write_no_author_rows(path):
    rows = [
        ("1", "Immigrants should leave now", "Immigrants should leave now", "hate"),
        ("2", "Everyone deserves respect", "Everyone deserves respect", "nothate"),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "privatized_text", "label"])
        writer.writerows(rows)


def write_author_style_rows(path):
    base_rows = [
        ("Immigrants should leave now", "hate"),
        ("Refugees do not belong here", "hate"),
        ("I hate those people", "hate"),
        ("People should be deported", "hate"),
        ("Everyone deserves respect", "nothate"),
        ("Please join the public meeting", "nothate"),
    ]
    authors = [
        ("author_a", "flarnix flarnix !!!"),
        ("author_b", "zorbito zorbito ???"),
        ("author_c", "quendle quendle ***"),
    ]
    rows = []
    row_id = 1
    for author, marker in authors:
        for text, label in base_rows:
            rows.append(
                (
                    str(row_id),
                    f"{text} {marker}",
                    text,
                    label,
                    author,
                )
            )
            row_id += 1
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "privatized_text", "label", "author"])
        writer.writerows(rows)


def test_author_risk_command_is_registered_without_optional_dependency():
    parser = build_parser()

    args = parser.parse_args(
        [
            "evaluate-author-risk",
            "--input",
            "input.csv",
            "--text-col",
            "text",
        ]
    )

    assert args.command == "evaluate-author-risk"
    assert args.privatized_col == "privatized_text"
    assert args.author_col == "author"


def test_author_risk_skips_cleanly_without_author_column(tmp_path):
    source = tmp_path / "no_author.csv"
    output = tmp_path / "author_risk.json"
    write_no_author_rows(source)

    result = run_author_risk_evaluation(
        source,
        text_col="text",
        privatized_col="privatized_text",
        author_col="author",
        id_col="id",
        label_col="label",
        output_path=output,
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result == written
    assert result["status"] == "skipped"
    assert result["skip_reason"] == "missing_author_column"
    assert result["row_count"] == 2


@pytest.mark.skipif(not HAS_SKLEARN, reason="requires optional author-risk extra")
def test_author_risk_reports_drop_on_synthetic_style_fixture(tmp_path):
    source = tmp_path / "author_style.csv"
    output = tmp_path / "author_risk.json"
    write_author_style_rows(source)

    result = run_author_risk_evaluation(
        source,
        text_col="text",
        privatized_col="privatized_text",
        author_col="author",
        id_col="id",
        label_col="label",
        output_path=output,
        test_size=0.5,
        random_state=3,
    )

    assert output.exists()
    assert result["status"] == "ok"
    assert result["split"]["author_counts"] == {
        "author_a": 6,
        "author_b": 6,
        "author_c": 6,
    }
    assert result["original"]["macro_f1"] > result["privatized"]["macro_f1"]
    assert result["comparison"]["privacy_gain_macro_f1"] > 0
    assert result["hsd_proxy"]["metrics"]["utility_cue_retention_mean"] == 1.0
    assert "residual_high_risk_rows" in result["comparison"]
