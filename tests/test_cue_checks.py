import csv
import json

import pytest

from privhsd.cli import build_parser
from privhsd.cue_checks import CueCheckError, run_cue_checks


def write_rows(path):
    rows = [
        (
            "1",
            "Immigrants should leave now.",
            "Immigrants should leave now.",
        ),
        (
            "2",
            "Refugees do not belong here.",
            "People are here.",
        ),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "privatized_text"])
        writer.writerows(rows)


def test_check_hsd_cues_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "check-hsd-cues",
            "--input",
            "input.csv",
            "--text-col",
            "text",
        ]
    )

    assert args.command == "check-hsd-cues"
    assert args.privatized_col == "privatized_text"


def test_cue_checks_report_rows_with_loss(tmp_path):
    source = tmp_path / "cues.csv"
    output = tmp_path / "cues.json"
    write_rows(source)

    result = run_cue_checks(
        source,
        text_col="text",
        privatized_col="privatized_text",
        id_col="id",
        output_path=output,
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result == written
    assert result["aggregate"]["row_count"] == 2
    assert result["aggregate"]["rows_with_loss"] == 1
    assert result["rows_with_loss"][0]["row_id"] == "2"
    assert "target_terms" in result["rows_with_loss"][0]["loss_groups"]
    assert "utility_cues" in result["rows_with_loss"][0]["loss_groups"]
    assert "text" not in result["rows_with_loss"][0]


def test_cue_checks_track_historical_victim_group_terms(tmp_path):
    source = tmp_path / "historical_groups.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "privatized_text"])
        writer.writerow(
            [
                "1",
                "Holocaust survivors should be attacked.",
                "Survivors should be attacked.",
            ]
        )

    result = run_cue_checks(
        source,
        text_col="text",
        privatized_col="privatized_text",
        id_col="id",
    )

    row = result["rows"][0]
    assert "target_terms" in result["rows_with_loss"][0]["loss_groups"]
    assert row["groups"]["target_terms"]["lost_terms"] == ["holocaust survivors"]


def test_cue_checks_validate_threshold(tmp_path):
    source = tmp_path / "cues.csv"
    write_rows(source)

    with pytest.raises(CueCheckError, match="retention-threshold"):
        run_cue_checks(
            source,
            text_col="text",
            privatized_col="privatized_text",
            retention_threshold=1.5,
        )
