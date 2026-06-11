import csv
import json

import pytest

from privhsd.cli import build_parser
from privhsd.dpmlm_spike import DpmlmSpikeError, run_dpmlm_spike


def write_dpmlm_rows(path):
    rows = [
        (
            "1",
            "Immigrants should leave now!!!!",
            "immigrants should leave now!",
            "hate",
        ),
        (
            "2",
            "Everyone deserves respect.",
            "everyone deserves respect.",
            "nothate",
        ),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "privatized_text", "label"])
        writer.writerows(rows)


def test_dpmlm_spike_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "dpmlm-spike",
            "--input",
            "input.csv",
            "--text-col",
            "text",
            "--epsilon",
            "25",
            "--epsilon",
            "50",
        ]
    )

    assert args.command == "dpmlm-spike"
    assert args.epsilons == [25.0, 50.0]


def test_dpmlm_spike_writes_structured_blocker_report(monkeypatch, tmp_path):
    source = tmp_path / "dpmlm.csv"
    output = tmp_path / "dpmlm.json"
    write_dpmlm_rows(source)
    monkeypatch.setattr(
        "privhsd.dpmlm_spike.detect_backends",
        lambda: {"dpmlm": False, "private_transformers": False, "opendp": False},
    )

    result = run_dpmlm_spike(
        source,
        text_col="text",
        id_col="id",
        privatized_col="privatized_text",
        output_path=output,
        sample_size=1,
        epsilons=[25.0, 50.0],
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result == written
    assert result["status"] == "skipped"
    assert result["sample"]["sample_size"] == 1
    assert [item["epsilon"] for item in result["epsilon_results"]] == [25.0, 50.0]
    assert all(item["status"] == "skipped" for item in result["epsilon_results"])
    assert result["protected_cues"]["protected_token_count"] > 0
    assert "immigrants" in result["protected_cues"]["protected_tokens"]
    assert result["existing_privatized_baseline"]["metrics"][
        "utility_cue_retention_mean"
    ] == 1.0
    assert "text" not in result["sample"]["rows"][0]


def test_dpmlm_spike_reports_detected_backend_without_adapter(monkeypatch, tmp_path):
    source = tmp_path / "dpmlm.csv"
    write_dpmlm_rows(source)
    monkeypatch.setattr(
        "privhsd.dpmlm_spike.detect_backends",
        lambda: {
            "dpmlm": {"installed": True, "importable": True, "error": None},
            "private_transformers": False,
            "opendp": False,
        },
    )

    result = run_dpmlm_spike(
        source,
        text_col="text",
        id_col="id",
        privatized_col="privatized_text",
        sample_size=1,
        epsilons=[25.0],
    )

    assert result["backend"]["selected"] == "dpmlm"
    assert result["backend"]["detected"]["dpmlm"] is True
    assert result["backend"]["details"]["dpmlm"]["installed"] is True
    assert result["epsilon_results"][0]["skip_reason"] == "adapter_not_implemented"


def test_dpmlm_spike_rejects_invalid_epsilon(tmp_path):
    source = tmp_path / "dpmlm.csv"
    write_dpmlm_rows(source)

    with pytest.raises(DpmlmSpikeError, match="epsilon"):
        run_dpmlm_spike(
            source,
            text_col="text",
            epsilons=[0.0],
        )
