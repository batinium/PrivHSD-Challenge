import csv
import json

from privhsd.cli import build_parser
from privhsd.contribution_bounding import bound_contributions


def write_rows(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "author_id", "text", "label", "source"],
        )
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_bound_contributions_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "bound-contributions",
            "--input",
            "input.csv",
            "--output",
            "bounded.csv",
            "--author-col",
            "author_id",
            "--max-records-per-author",
            "2",
            "--stratify-col",
            "label",
        ]
    )

    assert args.command == "bound-contributions"
    assert args.author_col == "author_id"
    assert args.max_records_per_author == 2
    assert args.stratify_cols == ["label"]


def test_bound_contributions_caps_authors_and_preserves_schema_order(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "bounded.csv"
    report = tmp_path / "report.json"
    write_rows(
        source,
        [
            {
                "id": "1",
                "author_id": "a",
                "text": "hate one",
                "label": "hate",
                "source": "x",
            },
            {
                "id": "2",
                "author_id": "a",
                "text": "hate two",
                "label": "hate",
                "source": "x",
            },
            {
                "id": "3",
                "author_id": "a",
                "text": "calm one",
                "label": "nothate",
                "source": "x",
            },
            {
                "id": "4",
                "author_id": "a",
                "text": "hate three",
                "label": "hate",
                "source": "y",
            },
            {
                "id": "5",
                "author_id": "b",
                "text": "other one",
                "label": "hate",
                "source": "x",
            },
            {
                "id": "6",
                "author_id": "b",
                "text": "other two",
                "label": "nothate",
                "source": "x",
            },
            {
                "id": "7",
                "author_id": "",
                "text": "unknown",
                "label": "hate",
                "source": "z",
            },
        ],
    )

    result = bound_contributions(
        source,
        output,
        author_col="author_id",
        max_records_per_author=2,
        id_col="id",
        text_col="text",
        report_path=report,
        strategy="stratified",
        stratify_cols=["label"],
        random_state=4,
    )

    rows = read_rows(output)
    ids = [row["id"] for row in rows]
    assert ids == sorted(ids, key=int)
    assert len(rows) == 5
    assert sum(1 for row in rows if row["author_id"] == "a") == 2
    assert sum(1 for row in rows if row["author_id"] == "b") == 2
    assert any(row["author_id"] == "" for row in rows)
    assert {row["label"] for row in rows if row["author_id"] == "a"} == {
        "hate",
        "nothate",
    }
    assert list(rows[0].keys()) == ["id", "author_id", "text", "label", "source"]

    written = json.loads(report.read_text(encoding="utf-8"))
    assert result == written
    assert result["row_counts"]["before"] == 7
    assert result["row_counts"]["after"] == 5
    assert result["row_counts"]["dropped"] == 2
    assert result["row_counts"]["unbounded_missing_author_rows"] == 1
    assert result["author_groups"]["after"]["max_rows_per_author_after"] == 2


def test_bound_contributions_can_drop_missing_author_rows(tmp_path):
    source = tmp_path / "input.csv"
    output = tmp_path / "bounded.csv"
    write_rows(
        source,
        [
            {
                "id": "1",
                "author_id": "",
                "text": "unknown",
                "label": "hate",
                "source": "z",
            },
            {
                "id": "2",
                "author_id": "a",
                "text": "known",
                "label": "hate",
                "source": "z",
            },
        ],
    )

    result = bound_contributions(
        source,
        output,
        author_col="author_id",
        max_records_per_author=1,
        drop_missing_author=True,
    )

    rows = read_rows(output)
    assert [row["id"] for row in rows] == ["2"]
    assert result["row_counts"]["dropped_missing_author"] == 1
    assert result["row_counts"]["unbounded_missing_author_rows"] == 0
