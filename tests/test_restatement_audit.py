import csv
import json

from contextsafe_hsd.restatement_audit import run_restatement_deviation_audit


def test_restatement_deviation_audit_flags_lost_context(tmp_path):
    source = tmp_path / "restated.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ID", "source_text", "hs", "backend_restatement_final"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ID": "REDDIT_307",
                "source_text": (
                    "The post attacks Jews and Asians and says critics are accused of "
                    "anti-semitism while warning about genocide."
                ),
                "hs": "1",
                "backend_restatement_final": (
                    "The comment criticizes a named public figure."
                ),
            }
        )
    output = tmp_path / "audit.csv"
    summary_path = tmp_path / "summary.json"

    summary = run_restatement_deviation_audit(
        source,
        output,
        summary_path=summary_path,
        text_col="source_text",
        restatement_col="backend_restatement_final",
        id_col="ID",
    )

    rows = list(csv.DictReader(output.open(encoding="utf-8", newline="")))
    assert rows[0]["deviation_risk"] in {"medium", "high"}
    assert "context_term_loss" in rows[0]["deviation_reasons"]
    assert summary["high_or_medium_ids"] == ["REDDIT_307"]
    assert json.loads(summary_path.read_text(encoding="utf-8"))["rows"] == 1
